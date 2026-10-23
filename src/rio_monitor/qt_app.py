"""Qt Quick single-window shell. Existing telemetry/render/output are kept separate."""
import sys,time,json,threading,queue,argparse,statistics
from collections import deque
from pathlib import Path
from dataclasses import replace
from functools import lru_cache
from PIL import Image,ImageDraw
from PySide6.QtCore import QObject,Signal,Slot,Property,QTimer,QUrl,Qt,QMetaObject
from PySide6.QtGui import QIcon,QImage,QAction,QFont,QCursor
from PySide6.QtWidgets import QApplication,QSystemTrayIcon,QMenu,QFileDialog
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQuick import QQuickImageProvider
from . import __version__
from .settings import Settings,load,save,set_autostart,config_path
from .weather_source import WeatherWorker,cities,coordinates,fetch_json
from .telemetry import Collector
from .render_cache import Renderer
from .temperature_component import TemperatureComponent
from .storage import DisplaySession,StorageJob
from .music.controller import Music
from .music.renderer import MusicRenderer
from .music.state import AutomaticMusicView
from .view_transition import ViewTransition

@lru_cache(maxsize=2)
def preview_mask(size):
 # Only the settings preview is transparent; USB output stays RGB565.
 mask=Image.new('L',(size*4,size*4));ImageDraw.Draw(mask).ellipse((0,0,size*4-1,size*4-1),fill=255)
 return mask.resize((size,size),Image.Resampling.LANCZOS)

def preview_bytes(frame):
 image=frame.convert('RGBA');image.putalpha(preview_mask(frame.width));return image.tobytes()

class Frames(QQuickImageProvider):
 def __init__(self):super().__init__(QQuickImageProvider.Image);self.image=QImage(480,480,QImage.Format_RGBA8888);self.image.fill(Qt.transparent)
 def requestImage(self,id,size,requestedSize):return self.image

class Bridge(QObject):
 changed=Signal();frameChanged=Signal();noticeChanged=Signal();defaultConfirmationChanged=Signal()
 def __init__(self,app,settings,weather,provider,capture=False,monitor=None,storage=None,music=None,updater=None):
  super().__init__();self.app=app;self.s=settings;self.weather=weather;self.frames=provider;self.capture=capture;self.win=None;self.tray=None;self._frame=0;self._notice='';self._saved=False;self._results=[];self._status='';self._busy=False;self._city='';self.loc=None;self.mode=settings.weather_mode;self.city=settings.city;self.mail=queue.Queue();self.generation=0;self.visible=True;self.quitting=False;self.shutdown=None
  self._dirty=False;self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(250);self.save_timer.timeout.connect(self.flushSettings)
  self.monitor=monitor or TemperatureComponent(Path(),settings.temperature_monitor,start=False);self.monitor_snapshot=None
  self.storage=storage or StorageJob(DisplaySession(settings.display_mode),Path());self.storage_snapshot=None
  self.music=music or Music(Path(),start=False);self.music_signature=None
  self.updater=updater;self.update_snapshot=updater.snapshot() if updater else dict(state='idle',connection='unknown',progress=0)
  self._reset_requested=False
  if settings.weather_mode=='manual':
   try:self._city=json.loads(settings.city)['label'].split(',')[0]
   except (ValueError,KeyError):pass
 def getLanguage(self):return self.s.language
 language=Property(str,getLanguage,notify=changed)
 rotation=Property(int,lambda self:self.s.rotation,notify=changed)
 autostart=Property(bool,lambda self:self.s.autostart,notify=changed)
 cityLabel=Property(str,lambda self:self._city or (('Automatic network location' if self.s.language=='en' else '自动网络定位') if self.mode=='auto' else ''),notify=changed)
 cityResults=Property('QVariantList',lambda self:self._results,notify=changed)
 searchStatus=Property(str,lambda self:self._status,notify=changed)
 searchBusy=Property(bool,lambda self:self._busy,notify=changed)
 saved=Property(bool,lambda self:self._saved,notify=changed)
 notice=Property(str,lambda self:self._notice,notify=noticeChanged)
 frameId=Property(int,lambda self:self._frame,notify=frameChanged)
 version=Property(str,lambda self:__version__,constant=True)
 updateState=Property(str,lambda self:self.update_snapshot['state'],notify=changed)
 updateConnection=Property(str,lambda self:self.update_snapshot['connection'],notify=changed)
 @Slot()
 def checkUpdates(self):
  if self.updater:self.updater.check();self.consume()
 def getFooterStatus(self):
  monitor=self.monitor.snapshot();storage=self.storage.snapshot();zh=self.s.language=='zh'
  if monitor['busy']:
   return ('正在卸载驱动…' if zh else 'Removing driver…') if monitor['state']=='uninstalling' else ('正在安装驱动…' if zh else 'Installing driver…')
  if storage['busy']:
   labels={'prepare':('Preparing media…','正在转换媒体…'),'connecting':('Connecting…','正在连接屏幕…'),'erase':('Preparing storage…','正在准备存储…'),'write':('Writing media…','正在写入媒体…')}
   return labels.get(storage['phase'],labels['prepare'])[1 if zh else 0]
  labels={'checking':('Checking…','正在检测更新…'),'downloading':('Downloading…','正在下载更新'),'latest':('Up to date','已是最新版本'),'ready':('Exit to apply update','退出后完成更新'),'error':('Update failed','更新失败 · 请重试')}
  return labels.get(self.updateState,('',''))[1 if zh else 0]
 footerStatus=Property(str,getFooterStatus,notify=changed)
 footerBusy=Property(bool,lambda self:self.monitorBusy or self.storageBusy or self.updateState in ('checking','downloading'),notify=changed)
 def getFooterProgress(self):
  if self.monitorBusy:return -1.
  storage=self.storage.snapshot()
  if storage['busy']:return storage['progress'] if storage['phase'] in ('erase','write') else -1.
  return self.update_snapshot['progress']/100 if self.updateState=='downloading' else -1.
 footerProgress=Property(float,getFooterProgress,notify=changed)
 monitorChecked=Property(bool,lambda self:self.monitor.snapshot()['checked'],notify=changed)
 monitorBusy=Property(bool,lambda self:self.monitor.snapshot()['busy'],notify=changed)
 monitorExternal=Property(bool,lambda self:self.monitor.snapshot().get('external',False),notify=changed)
 storageBusy=Property(bool,lambda self:self.storage.snapshot()['busy'],notify=changed)
 storageWriting=Property(bool,lambda self:self.storage.snapshot()['writing'],notify=changed)
 storageReady=Property(bool,lambda self:self.storage.snapshot()['ready'],notify=changed)
 storageStored=Property(bool,lambda self:self.storage.snapshot()['mode']=='stored',notify=changed)
 storageProgress=Property(float,lambda self:self.storage.snapshot()['progress'],notify=changed)
 storageName=Property(str,lambda self:self.storage.snapshot()['name'],notify=changed)
 storageError=Property(bool,lambda self:bool(self.storage.snapshot()['error']),notify=changed)
 defaultAvailable=Property(bool,lambda self:(self.storage.assets/'default-screen.gif').is_file(),notify=changed)
 defaultConfirmation=Property(bool,lambda self:self._reset_requested,notify=defaultConfirmationChanged)
 storageDetail=Property(str,lambda self:self.storage.snapshot()['detail'],notify=changed)
 storagePreview=Property(str,lambda self:QUrl.fromLocalFile(self.storage.snapshot()['preview']).toString() if self.storage.snapshot()['preview'] else '',notify=changed)
 musicEnabled=Property(bool,lambda self:self.s.music_enabled,notify=changed)
 musicOnline=Property(bool,lambda self:self.s.music_online_lyrics,notify=changed)
 musicSources=Property('QVariantList',lambda self:[dict(id='',label='自动' if self.s.language=='zh' else 'Auto')]+self.music.snapshot()['sources'],notify=changed)
 musicSource=Property(str,lambda self:self.s.music_source,notify=changed)
 def getMusicStatus(self):
  state=self.music.snapshot();zh=self.s.language=='zh'
  labels={'off':('Off','关闭'),'ready':('Ready','就绪'),'starting':('Starting','启动中'),'no_session':('No player session','未发现播放器会话'),'media_unavailable':('Media interface unavailable','媒体接口不可用'),'audio_unavailable':('Audio unavailable','音频不可用'),'dependency_missing':('Audio dependency missing','缺少音频组件'),'windows_only':('Windows required','仅支持 Windows'),'loading':('Loading','加载中'),'local':('Local LRC','本地歌词'),'online_off':('Online lyrics off','在线歌词关闭'),'not_found':('No matching lyrics','暂无匹配歌词'),'network_error':('Lyrics connection failed','歌词连接失败'),'no_timed_lyrics':('No timed lyrics','暂无同步歌词'),'insufficient_metadata':('Incomplete song metadata','歌曲信息不完整'),'instrumental':('Instrumental','纯音乐')}
  labels.update(provider_error=labels['network_error'],lyrics_error=labels['network_error'])
  return ' / '.join(labels.get(value,(value,value))[1 if zh else 0] for value in (state['status'],state['audio'].status,state['lyric_status']))
 musicStatus=Property(str,getMusicStatus,notify=changed)
 @Slot(bool)
 def setMusicEnabled(self,value):
  self.applySettings(music_enabled=value)
  self.music.configure(value,self.s.music_online_lyrics,self.s.music_source)
 @Slot(bool)
 def setMusicOnline(self,value):
  self.applySettings(music_online_lyrics=value,music_lyrics_consent=2 if value else 0)
  self.music.configure(self.s.music_enabled,value,self.s.music_source)
 @Slot(str)
 def setMusicSource(self,value):
  self.applySettings(music_source=value)
  self.music.configure(self.s.music_enabled,self.s.music_online_lyrics,value)
 @Slot()
 def importMusicLyrics(self):
  name,_=QFileDialog.getOpenFileName(None,'Import LRC / 导入歌词','','Lyrics (*.lrc)')
  if name:
   try:self.music.import_lrc(name)
   except Exception as exc:self.tell(str(exc))
 def toggleMusic(self):self.setMusicEnabled(not self.s.music_enabled)
 def getStorageStatus(self):
  labels={'idle':('Video, animated or still image · Up to 3.4 MB','视频、动态图或静态图 · 不超过 3.4 MB'),'prepare':('Preparing preview…','正在转换并生成预览…'),'ready':('Ready · Click Write to replace stored content','已准备好 · 点击写入后替换屏内内容'),'connecting':('Connecting to screen…','正在连接屏幕…'),'erase':('Preparing screen storage… Keep power connected','正在准备屏幕存储… 请保持供电'),'write':('Writing… Keep power connected','正在写入… 请保持供电'),'stored':('Stored · Real-time monitoring paused','写入完成 · 实时监控已暂停'),'live':('Real-time monitoring resumed','已恢复实时监控')}
  snapshot=self.storage.snapshot()
  if snapshot['error']:return snapshot['error']
  return labels.get(snapshot['phase'],labels['idle'])[1 if self.s.language=='zh' else 0]
 storageStatus=Property(str,getStorageStatus,notify=changed)
 @Slot()
 def prepareStoragePreview(self):
  self.storage.open_preview();self.changed.emit()
 @Slot()
 def chooseStorageFile(self):
  if self.storage.snapshot()['busy']:return
  cn=self.s.language=='zh'
  name,_=QFileDialog.getOpenFileName(None,'选择屏幕内容' if cn else 'Choose screen content','',
   'Media (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.apng *.mp4 *.m4v *.mov *.avi *.mkv *.webm *.wmv *.mpg *.mpeg *.ts *.flv);;All files (*)')
  if name:self.storage.prepare(name);self.changed.emit()
 @Slot()
 def writeStorage(self):
  if self.capture:return
  self.storage.write();self.changed.emit()
 @Slot()
 def resumeMonitor(self):
  if self.capture:return
  self.storage.resume();self.changed.emit()
 @Slot()
 def requestRestoreDefault(self):
  if not self.defaultAvailable or self.storage.snapshot()['busy']:return
  self._reset_requested=True;self.defaultConfirmationChanged.emit()
 @Slot(bool)
 def confirmRestoreDefault(self,accepted):
  if not self._reset_requested:return
  self._reset_requested=False;self.defaultConfirmationChanged.emit()
  if accepted and not self.capture:
   self.storage.prepare(self.storage.assets/'default-screen.gif',write_after=True);self.changed.emit()
 def getMonitorStatus(self):
  labels={'detecting':('Checking existing sensors…','正在检测现有传感器…'),'missing':('Enable to install · Administrator approval once','首次开启时安装 · 需管理员确认'),'installing':('Installing temperature component…','正在安装温度监控组件…'),'existing':('Using existing sensor interface','使用现有传感器接口'),'ready':('Installed · Running','已安装 · 运行正常'),'starting':('Starting temperature monitoring…','正在启用温度监控…'),'off':('Monitoring off','温度监控已关闭'),'unsupported':('Installed · CPU sensor unavailable','已安装 · 暂无可用 CPU 温度'),'error':('Component unavailable · Re-enable to repair','组件异常 · 重新开启可修复'),'cancelled':('Installation cancelled','已取消安装'),'reboot':('Installed · Windows restart required','已安装 · 需重启 Windows')}
  snapshot=self.monitor.snapshot();state=snapshot['state']
  labels.update({'existing':('Existing sensor interface · No installation needed','已检测到现有接口 · 无需安装'),'uninstalling':('Removing our temperature component…','正在卸载我们安装的组件…'),'removed':('Our component removed','我们安装的组件已卸载'),'uninstall_reboot':('Removed · Windows restart required','已卸载 · 重启后完成驱动移除')})
  if state=='off':labels['off']=('Installed · Monitoring off','已安装 · 温度监控已关闭') if snapshot['installed'] else ('Enable to detect sensors or install','开启时检测，缺少时安装')
  return labels.get(state,labels['missing'])[1 if self.s.language=='zh' else 0]
 monitorStatus=Property(str,getMonitorStatus,notify=changed)
 @Slot(bool)
 def setMonitorEnabled(self,value):
  self.monitor.request(value);self.applySettings(temperature_monitor=self.monitor.enabled);self.changed.emit()
 def tell(self,text):self._notice=text;self.noticeChanged.emit()
 def applySettings(self,**values):
  value=replace(self.s,**values)
  if value==self.s:return
  self.s=value;self._dirty=True;self._saved=False;self.save_timer.start();self.changed.emit();self.updateMenu()
 def flushSettings(self):
  self.save_timer.stop()
  if not self._dirty:return True
  try:
   if not self.capture:save(self.s)
  except OSError as ex:self.tell('Could not save settings / 无法保存设置: '+str(ex));return False
  self._dirty=False;self._saved=True;self.changed.emit();return True
 @Slot(str)
 def setLanguage(self,value):
  if value in ('en','zh'):self.applySettings(language=value)
 @Slot(int)
 def setRotation(self,value):
  if 0<=value<=359:self.applySettings(rotation=value)
 @Slot(bool)
 def setAutostart(self,value):
  if value==self.s.autostart:return
  try:
   if not self.capture:set_autostart(value)
  except Exception as ex:self.changed.emit();self.tell(str(ex));return
  self.applySettings(autostart=value)
 @Slot()
 def saveAndHide(self):
  if self.flushSettings():self.hideWindow()
 def applyWeather(self):
  self.applySettings(weather_mode=self.mode,city=self.city)
  self.weather.configure(self.s,self.loc)
 @Slot(bool)
 def setPreviewVisible(self,value):self.visible=value
 @Slot()
 def hideWindow(self):
  if not self.flushSettings():return
  if self.tray and self.tray.isVisible():self.win.hide()
  elif self.capture:self.win.hide()
  else:self.tell('System tray unavailable. / 系统托盘不可用。')
 def show(self):self.win.show();self.win.raise_();self.win.requestActivate()
 def exit(self):
  if self.quitting:return
  if self.storage.snapshot()['writing']:
   self.show();self.tell('Writing screen content. Please wait. / 正在写入屏幕内容，请稍候。');return
  if self.monitor.snapshot()['busy']:
   self.show();self.tell('Temperature component is being updated. Please wait. / 温度监控组件正在处理，请稍候。');return
  if not self.flushSettings():self.show();return
  self.quitting=True
  if self.shutdown and not self.shutdown():self.quitting=False;QTimer.singleShot(500,self.exit);return
  if self.tray:self.tray.hide()
  self.app.quit()
 def toggleAuto(self):
  self.setAutostart(not self.s.autostart)
 def trayActivated(self,reason):
  if reason==QSystemTrayIcon.Context:
   menu=getattr(self,'menu',None)
   if menu:menu.popup(QCursor.pos());menu.activateWindow()
  elif reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):self.show()
 def updateMenu(self):
  if not self.tray:return
  cn=self.s.language=='zh';menu=QMenu();menu.setStyleSheet('QMenu{background:#1a2024;color:#e5ecef;border:1px solid #354047;padding:6px;}QMenu::item{padding:8px 26px;border-radius:4px;}QMenu::item:selected{background:#354331;}')
  entries=[('退出' if cn else 'Exit',self.exit),('设置' if cn else 'Settings',self.show),('登录后启动' if cn else 'Start at login',self.toggleAuto)]
  for text,fn in entries:
   action=menu.addAction(text);action.triggered.connect(fn)
   if fn==self.toggleAuto:action.setCheckable(True);action.setChecked(self.s.autostart)
   if fn==self.toggleMusic:action.setCheckable(True);action.setChecked(self.s.music_enabled)
  # One explicit right-click path avoids depending on the platform's popup handling.
  old=getattr(self,'menu',None);self.menu=menu;self.tray.setContextMenu(None)
  if old:old.deleteLater()
 @Slot(str)
 def searchCities(self,name):
  name=name.strip()
  if not name:return
  self.generation+=1;gen=self.generation;self._busy=True;self._results=[];self._status='Searching…' if self.s.language=='en' else '查询中…';self.changed.emit()
  def run():
   try:self.mail.put(('search',gen,cities(name),None))
   except Exception as ex:self.mail.put(('search',gen,[],str(ex)))
  threading.Thread(target=run,daemon=True).start()
 @Slot(int)
 def selectCity(self,index):
  if not 0<=index<len(self._results):return
  self.generation+=1
  row=self._results[index];self.loc=(row['latitude'],row['longitude'],row['label']);self.city=json.dumps({'latitude':row['latitude'],'longitude':row['longitude'],'label':row['label']},ensure_ascii=False);self.mode='manual';self._city=row['name'];self.changed.emit()
  self.applyWeather()
 @Slot()
 def locateCity(self):
  self.generation+=1;gen=self.generation;self._city='Locating…' if self.s.language=='en' else '定位中…';self.changed.emit()
  def run():
   try:
    data=fetch_json('https://ipwho.is/?fields=success,city,region,country,latitude,longitude')
    if data.get('success') is not True:raise ValueError('Location unavailable')
    self.mail.put(('locate',gen,data,None))
   except Exception as ex:self.mail.put(('locate',gen,None,str(ex)))
  threading.Thread(target=run,daemon=True).start()
 def consume(self):
  if self.updater:
   update_snapshot=self.updater.snapshot()
   if update_snapshot!=self.update_snapshot:self.update_snapshot=update_snapshot;self.changed.emit()
  state=self.music.snapshot();signature=(state['status'],state['audio'].status,state['lyric_status'],repr(state['sources']))
  if signature!=self.music_signature:self.music_signature=signature;self.changed.emit()
  storage_snapshot=self.storage.snapshot()
  if storage_snapshot!=self.storage_snapshot:
   self.storage_snapshot=storage_snapshot;self.applySettings(display_mode=storage_snapshot['mode']);self.changed.emit()
  snapshot=self.monitor.snapshot()
  if snapshot!=self.monitor_snapshot:
   self.monitor_snapshot=snapshot;self.applySettings(temperature_monitor=snapshot['enabled']);self.changed.emit()
  if self.mode=='auto' and not self._city and self.weather.location:
   self._city=self.weather.location[2].split(',')[0];self.changed.emit()
  while not self.mail.empty():
   typ,gen,data,error=self.mail.get()
   if gen!=self.generation:continue
   self._busy=False
   if error:self._status='Search failed. Please retry.' if self.s.language=='en' else '查询失败，请重试。';self.tell(self._status)
   elif typ=='search':
    self._results=[]
    for row in data:
     try:lat,lon=coordinates(row)
     except (ValueError,KeyError,TypeError):continue
     detail=', '.join(str(row.get(k,'')) for k in ('admin1','country') if row.get(k));name=str(row['name']);self._results.append(dict(name=name,detail=detail,label=name+', '+detail,latitude=lat,longitude=lon))
    self._status=('No matching city' if self.s.language=='en' else '未找到城市') if not self._results else ''
   else:
    lat,lon=coordinates(data);label=', '.join(str(data.get(k,'')) for k in ('city','region','country') if data.get(k));self.loc=(lat,lon,label);self.mode='auto';self._city=str(data.get('city',''))
    self.city='';self.applyWeather()
   self.changed.emit()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--version',action='version',version='RIO System Monitor '+__version__);parser.add_argument('--ui-capture',type=Path);parser.add_argument('--snapshot',type=Path);parser.add_argument('--demo',action='store_true');parser.add_argument('--self-test',action='store_true');parser.add_argument('--show-settings',action='store_true');parser.add_argument('--show-content',action='store_true');parser.add_argument('--performance-report',type=Path);args=parser.parse_args()
 if args.snapshot:
  from .model import Sample
  renderer=Renderer();collector=Collector();now=time.monotonic()
  samples=({k:Sample(v,now,'demo') for k,v in {'cpu':32,'gpu':68,'temperature':58,'ram_used':12.4,'ram_total':32,'download':24.8,'upload':1.2}.items()} if args.demo else collector.collect())
  for i in range(120):frame=renderer.render(samples,now=now+i/60)
  frame.save(args.snapshot);collector.gpu.close();return
 QQuickStyle.setStyle('Basic')
 app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);app.setApplicationName('RIO System Monitor');app.setApplicationVersion(__version__);app.setFont(QFont('Segoe UI',10))
 assets=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'assets';app.setWindowIcon(QIcon(str(assets/'rio-icon.ico')))
 from .updater import AutoUpdater
 updater=AutoUpdater(config_path().parent/'updates') if getattr(sys,'frozen',False) and not args.ui_capture and not args.self_test else None
 settings=Settings(weather_mode='off') if args.ui_capture else load();weather=WeatherWorker(settings);provider=Frames();monitor=TemperatureComponent(assets,settings.temperature_monitor,start=not args.ui_capture);session=DisplaySession(settings.display_mode);storage=StorageJob(session,assets,cache_dir=None if args.ui_capture else config_path().parent/'screen-content');music=Music(config_path().parent/'lyrics',settings.music_enabled,settings.music_online_lyrics,settings.music_source,start=not args.ui_capture);bridge=Bridge(app,settings,weather,provider,bool(args.ui_capture),monitor=monitor,storage=storage,music=music,updater=updater);engine=QQmlApplicationEngine();engine.addImageProvider('monitor',provider);engine.rootContext().setContextProperty('bridge',bridge);engine.load(QUrl.fromLocalFile(str(assets/'ui/Main.qml')))
 if not engine.rootObjects():raise RuntimeError('Qt Quick main window failed to load')
 bridge.win=engine.rootObjects()[0];bridge.tray=QSystemTrayIcon(app.windowIcon(),app);bridge.tray.setToolTip('RIO System Monitor '+__version__);bridge.updateMenu();bridge.tray.activated.connect(bridge.trayActivated)
 if not args.ui_capture:bridge.tray.show()
 if not args.ui_capture and not (args.show_settings or args.show_content):QTimer.singleShot(0,bridge.hideWindow)
 if args.show_content:
  def show_content():
   storage.prepare(assets/'default-screen.gif');bridge.win.findChild(QObject,'storagePopup').setProperty('visible',True)
  QTimer.singleShot(150,show_content)
 frames=queue.Queue(maxsize=1);stop=threading.Event();reported_error=[None];render_times=deque(maxlen=300);render_count=[0];run_started=time.monotonic();latest_samples=[{}];sensor_errors=queue.Queue();active_view=['monitor']
 def collect_loop():
  collector=None
  try:
   collector=Collector(temperature=monitor)
   while not stop.is_set():
    started=time.monotonic();latest_samples[0]=collector.collect();stop.wait(max(0,1-(time.monotonic()-started)))
  except Exception as ex:sensor_errors.put(str(ex))
  finally:
   if collector:collector.gpu.close()
 collector_worker=threading.Thread(target=collect_loop,daemon=True);collector_worker.start()
 def render_loop():
  renderer=Renderer();music_renderer=MusicRenderer(assets);music_view=AutomaticMusicView();transition=ViewTransition()
  while not stop.is_set():
   started=time.monotonic()
   if bridge.visible or session.needs_frame:
    music_state=music.snapshot()
    show_music=music_view.select(music_state,started);active_view[0]='music' if show_music else 'monitor'
    frame=music_renderer.render(music_state,language=bridge.s.language) if show_music else renderer.render(latest_samples[0],weather=weather.reading)
    frame=transition.render(active_view[0],frame,started)
    render_times.append(time.monotonic()-started);render_count[0]+=1
    session.submit(frame.rotate(-bridge.s.rotation) if bridge.s.rotation else frame)
    if bridge.visible:
     try:frames.get_nowait()
     except queue.Empty:pass
     frames.put_nowait(preview_bytes(frame))
   stop.wait(max(0,1/bridge.s.fps-(time.monotonic()-started)))
 worker=threading.Thread(target=render_loop,daemon=True);worker.start()
 def tick():
  bridge.consume()
  if not sensor_errors.empty():bridge.tell('Sensors: '+sensor_errors.get())
  usb=session.snapshot()
  if usb['mode']=='monitor' and usb['usb_error'] and usb['usb_error']!=reported_error[0]:
   reported_error[0]=usb['usb_error'];bridge.tell('USB: '+usb['usb_error'])
  try:data=frames.get_nowait();provider.image=QImage(data,480,480,480*4,QImage.Format_RGBA8888).copy();bridge._frame+=1;bridge.frameChanged.emit()
  except queue.Empty:pass
 timer=QTimer();timer.timeout.connect(tick);timer.setTimerType(Qt.PreciseTimer);timer.start(33)
 def performance_report():
  if not args.performance_report:return
  durations=list(render_times);elapsed=time.monotonic()-run_started
  music_state=music.snapshot();track=music_state['track'];audio=music_state['audio'].current(time.monotonic())
  report=dict(seconds=round(elapsed,3),target_render_fps=bridge.s.fps,rendered_frames=render_count[0],render_mean_ms=round(statistics.mean(durations)*1000,3) if durations else None,**session.snapshot(),temperature=monitor.snapshot(),storage=storage.snapshot(),view=active_view[0],music=dict(enabled=music_state['enabled'],status=music_state['status'],playing=track.playing,has_title=bool(track.title),has_cover=bool(track.cover),cover_bytes=len(track.cover),lyric_status=music_state['lyric_status'],lyric_rows=len(music_state['rows']),session_count=len(music_state['sources']),audio_status=audio.status,audio_level=round(audio.level,3)))
  try:args.performance_report.write_text(json.dumps(report,indent=2),encoding='utf-8')
  except OSError:pass
 report_timer=QTimer();report_timer.timeout.connect(performance_report)
 if args.performance_report:report_timer.start(1000)
 def shutdown():
  if not storage.close():return False
  stop.set();weather.close();monitor.close()
  if not music.close():return False
  if not session.close():return False
  worker.join(2);collector_worker.join(2);return not worker.is_alive() and not collector_worker.is_alive()
 bridge.shutdown=shutdown
 if updater:
  update_timer=QTimer(app);update_timer.setInterval(6*60*60*1000);update_timer.timeout.connect(updater.check);update_timer.start()
  QTimer.singleShot(10000,updater.check);app.aboutToQuit.connect(updater.install_on_exit)
 if not args.ui_capture:QTimer.singleShot(500,session.start)
 if args.ui_capture:
  args.ui_capture.mkdir(parents=True,exist_ok=True)
  def capture_main():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-main.png'));slider=bridge.win.findChild(QObject,'rotationSlider');slider.setProperty('value',39);QMetaObject.invokeMethod(slider,'moved');QTimer.singleShot(400,capture_rotation)
  def capture_rotation():
   shot=bridge.win.grabWindow();shot.save(str(args.ui_capture/'qt-rotation39.png'));scale=shot.width()/bridge.win.width()
   # Sample where the rotated square used to escape the preview box.
   pixels=[shot.pixelColor(round(x*scale),round(y*scale)).name() for x,y in ((32,185),(206,185),(119,98),(119,272))]
   bridge.rotation_clip_proof=all(color=='#111416' for color in pixels)
   bridge.live_rotation_proof=bridge.s.rotation==39 and not bridge._dirty
   corners=[provider.image.pixelColor(x,y).alpha() for x,y in ((0,0),(479,0),(0,479),(479,479))]
   bridge.transparent_preview_proof=all(alpha==0 for alpha in corners) and provider.image.pixelColor(240,240).alpha()==255
   slider=bridge.win.findChild(QObject,'rotationSlider');slider.setProperty('value',0);QMetaObject.invokeMethod(slider,'moved');popup=bridge.win.findChild(QObject,'cityPopup');popup.setProperty('visible',True);QTimer.singleShot(350,capture_city)
  def capture_city():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-city.png'))
   bridge.win.findChild(QObject,'cityPopup').setProperty('visible',False)
   QMetaObject.invokeMethod(bridge.win.findChild(QObject,'storageButton'),'clicked');QTimer.singleShot(150,capture_current_storage)
  def capture_current_storage():
   bridge.unknown_preview_proof=not storage.snapshot()['preview'] and not storage.snapshot()['name'] and not storage.snapshot()['ready']
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-storage-current.png'))
   # Simulate choosing a file; capture mode never connects to or writes USB.
   storage.prepare(assets/'default-screen.gif');QTimer.singleShot(600,capture_storage)
  def capture_storage():
   if storage.snapshot()['busy']:QTimer.singleShot(200,capture_storage);return
   bridge.consume();bridge.win.grabWindow().save(str(args.ui_capture/'qt-storage.png'))
   if args.self_test:
    proof={'single_main_window':len(engine.rootObjects())==1,'content_width':420,'outer_width':bridge.win.width(),'frameless':bool(bridge.win.flags() & Qt.FramelessWindowHint),'rotated_preview_contained':bridge.rotation_clip_proof,'live_rotation_autosaved':bridge.live_rotation_proof,'transparent_preview_corners':bridge.transparent_preview_proof,'no_start_minimized_control':bridge.win.findChild(QObject,'hiddenSwitch') is None,'temperature_switch_present':bridge.win.findChild(QObject,'monitorSwitch') is not None}
    proof['storage_button_present']=bridge.win.findChild(QObject,'storageButton') is not None
    proof['local_media_preview_ready']=storage.snapshot()['ready'] and bridge.storagePreview.startswith('file:')
    proof['private_default_available']=bridge.defaultAvailable
    proof['unknown_stored_preview_not_replaced_by_default']=bridge.unknown_preview_proof
    proof['selected_file_preview_loaded']=storage.snapshot()['name']=='default-screen.gif' and storage.snapshot()['ready']
    media_popup=bridge.win.findChild(QObject,'storagePopup');city_popup=bridge.win.findChild(QObject,'cityPopup')
    proof['shared_dialog_dimensions']=media_popup.property('width')==city_popup.property('width')==280 and media_popup.property('height')==city_popup.property('height')==356
    proof['restore_icon_present']=bridge.win.findChild(QObject,'restoreDefaultButton') is not None
    QMetaObject.invokeMethod(bridge.win.findChild(QObject,'restoreDefaultButton'),'clicked')
    proof['reset_requires_confirmation']=bridge.defaultConfirmation and not storage.snapshot()['writing'] and storage.session.mode=='monitor'
    bridge.confirmRestoreDefault(False);proof['reset_cancel_preserves_content']=not bridge.defaultConfirmation and not storage.snapshot()['writing']
    proof['capture_performs_no_resource_write']=session.output is None and not session.resource_active and session.mode=='monitor'
    bridge.monitor.external=True;bridge.changed.emit()
    proof['existing_sensor_toggle_disabled']=not bridge.win.findChild(QObject,'monitorSwitch').property('enabled')
    bridge.monitor.external=False;bridge.changed.emit()
    bridge.win.findChild(QObject,'storagePopup').setProperty('visible',False)
    bridge.tray.show();bridge.setLanguage('zh');proof['chinese_menu']=[a.text() for a in bridge.menu.actions()]==['退出','设置','登录后启动']
    bridge.tray.activated.emit(QSystemTrayIcon.Context);QApplication.processEvents();proof['tray_right_click_popup_visible']=bridge.menu.isVisible()
    bridge.menu.grab().save(str(args.ui_capture/'qt-tray-menu-zh.png'));bridge.menu.hide()
    bridge.toggleAuto();proof['autostart_sync']=bridge.s.autostart and any(a.isCheckable() and a.isChecked() for a in bridge.menu.actions())
    bridge.win.findChild(QObject,'cityPopup').setProperty('visible',False);QMetaObject.invokeMethod(bridge.win.findChild(QObject,'saveButton'),'clicked');proof['save_hides_to_tray']=not bridge.win.isVisible() and bridge.tray.isVisible();bridge.show();proof['restore']=bridge.win.isVisible()
    bridge.setLanguage('en');proof['english_menu']=[a.text() for a in bridge.menu.actions()]==['Exit','Settings','Start at login']
    assert all(v for k,v in proof.items() if k not in ('content_width','outer_width')),proof
    (args.ui_capture/'qt-proof.json').write_text(json.dumps(proof,indent=2))
   bridge.requestRestoreDefault();QTimer.singleShot(150,capture_reset)
  def capture_reset():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-reset-confirmation.png'))
   cancel=bridge.win.findChild(QObject,'cancelDefaultButton');ok=bridge.win.findChild(QObject,'confirmDefaultButton')
   bridge.confirmation_button_proof=cancel.property('text')=='Cancel' and ok.property('text')=='OK' and abs(cancel.property('width')-ok.property('width'))<1
   bridge.confirmation_button_size=(cancel.property('width'),cancel.property('height'))
   QMetaObject.invokeMethod(ok,'clicked');QTimer.singleShot(100,capture_after_reset)
  def capture_after_reset():
   bridge.direct_reset_proof=not bridge.defaultConfirmation and not bridge.win.findChild(QObject,'storagePopup').property('visible')
   QMetaObject.invokeMethod(bridge.win.findChild(QObject,'weatherRefreshButton'),'clicked');QTimer.singleShot(150,capture_consent)
  def capture_consent():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-weather-confirmation.png'))
   cancel=bridge.win.findChild(QObject,'cancelLocateButton');ok=bridge.win.findChild(QObject,'confirmLocateButton')
   buttons_match=bridge.confirmation_button_proof and cancel.property('text')=='Cancel' and ok.property('text')=='OK' and abs(cancel.property('width')-ok.property('width'))<1 and (ok.property('width'),ok.property('height'))==bridge.confirmation_button_size
   QMetaObject.invokeMethod(cancel,'clicked')
   if args.self_test:
    proof=json.loads((args.ui_capture/'qt-proof.json').read_text());proof.update(confirmation_buttons_shared_and_equal=buttons_match,restore_ok_does_not_open_content_window=bridge.direct_reset_proof)
    assert buttons_match and bridge.direct_reset_proof,proof
    (args.ui_capture/'qt-proof.json').write_text(json.dumps(proof,indent=2))
   bridge.exit()
  QTimer.singleShot(1800,capture_main)
 result=app.exec();shutdown();return result
if __name__=='__main__':main()


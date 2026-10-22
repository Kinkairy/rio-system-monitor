"""Qt Quick single-window shell. Existing telemetry/render/output are kept separate."""
import sys,time,json,threading,queue,argparse
from pathlib import Path
from dataclasses import replace
from PySide6.QtCore import QObject,Signal,Slot,Property,QTimer,QUrl,Qt
from PySide6.QtGui import QIcon,QImage,QAction,QFont
from PySide6.QtWidgets import QApplication,QSystemTrayIcon,QMenu
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQuick import QQuickImageProvider
from .settings import Settings,load,save,set_autostart
from .weather_source import WeatherWorker,cities,coordinates,fetch_json
from .telemetry import Collector
from .render import Renderer

class Frames(QQuickImageProvider):
 def __init__(self):super().__init__(QQuickImageProvider.Image);self.image=QImage(480,480,QImage.Format_RGB888);self.image.fill(Qt.black)
 def requestImage(self,id,size,requestedSize):return self.image

class Bridge(QObject):
 changed=Signal();frameChanged=Signal();noticeChanged=Signal()
 def __init__(self,app,settings,weather,provider,capture=False):
  super().__init__();self.app=app;self.s=settings;self.weather=weather;self.frames=provider;self.capture=capture;self.win=None;self.tray=None;self._frame=0;self._notice='';self._saved=False;self._results=[];self._status='';self._busy=False;self._city='';self.loc=None;self.mode=settings.weather_mode;self.city=settings.city;self.mail=queue.Queue();self.generation=0;self.visible=True;self.quitting=False;self.shutdown=None
  if settings.weather_mode=='manual':
   try:self._city=json.loads(settings.city)['label'].split(',')[0]
   except (ValueError,KeyError):pass
 def getLanguage(self):return self.s.language
 language=Property(str,getLanguage,notify=changed)
 rotation=Property(int,lambda self:self.s.rotation,notify=changed)
 autostart=Property(bool,lambda self:self.s.autostart,notify=changed)
 startHidden=Property(bool,lambda self:self.s.start_hidden,notify=changed)
 cityLabel=Property(str,lambda self:self._city,notify=changed)
 cityResults=Property('QVariantList',lambda self:self._results,notify=changed)
 searchStatus=Property(str,lambda self:self._status,notify=changed)
 searchBusy=Property(bool,lambda self:self._busy,notify=changed)
 saved=Property(bool,lambda self:self._saved,notify=changed)
 notice=Property(str,lambda self:self._notice,notify=noticeChanged)
 frameId=Property(int,lambda self:self._frame,notify=frameChanged)
 def tell(self,text):self._notice=text;self.noticeChanged.emit()
 @Slot(str)
 def setLanguage(self,value):
  self.s.language=value
  if not self.capture:
   try:save(self.s)
   except OSError as ex:self.tell(str(ex))
  self.changed.emit();self.updateMenu()
 @Slot(int,bool,bool)
 def saveSettings(self,rotation,auto,hidden):
  value=replace(self.s,rotation=rotation,autostart=auto,start_hidden=hidden,weather_mode=self.mode,city=self.city)
  try:
   if not self.capture:
    if auto!=self.s.autostart:set_autostart(auto)
    save(value)
  except Exception as ex:self.tell(str(ex));return
  self.s=value;self.weather.configure(value,self.loc);self._saved=True;self.changed.emit();self.updateMenu();QTimer.singleShot(1800,self.clearSaved)
 def clearSaved(self):self._saved=False;self.changed.emit()
 @Slot(bool)
 def setPreviewVisible(self,value):self.visible=value
 @Slot()
 def hideWindow(self):
  if self.tray and self.tray.isVisible():self.win.hide()
  elif self.capture:self.win.hide()
  else:self.tell('System tray unavailable. / 系统托盘不可用。')
 def show(self):self.win.show();self.win.raise_();self.win.requestActivate()
 def exit(self):
  if self.quitting:return
  self.quitting=True
  if self.shutdown and not self.shutdown():self.quitting=False;QTimer.singleShot(500,self.exit);return
  if self.tray:self.tray.hide()
  self.app.quit()
 def toggleAuto(self):
  try:
   if not self.capture:set_autostart(not self.s.autostart)
   self.s.autostart=not self.s.autostart
   if not self.capture:save(self.s)
   self.changed.emit();self.updateMenu()
  except Exception as ex:self.show();self.tell(str(ex))
 def updateMenu(self):
  if not self.tray:return
  cn=self.s.language=='zh';menu=QMenu();menu.setStyleSheet('QMenu{background:#1a2024;color:#e5ecef;border:1px solid #354047;padding:6px;}QMenu::item{padding:8px 26px;border-radius:4px;}QMenu::item:selected{background:#354331;}')
  for text,fn in [('设置' if cn else 'Settings',self.show),('最小化' if cn else 'Minimize',self.hideWindow),('登录后自动启动' if cn else 'Start at login',self.toggleAuto),('退出' if cn else 'Exit',self.exit)]:
   action=menu.addAction(text);action.triggered.connect(fn)
   if fn==self.toggleAuto:action.setCheckable(True);action.setChecked(self.s.autostart)
  old=getattr(self,'menu',None);self.menu=menu;self.tray.setContextMenu(menu)
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
   self.changed.emit()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--ui-capture',type=Path);parser.add_argument('--snapshot',type=Path);parser.add_argument('--demo',action='store_true');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
 if args.snapshot:
  from .model import Sample
  renderer=Renderer();collector=Collector();now=time.monotonic()
  samples=({k:Sample(v,now,'demo') for k,v in {'cpu':32,'gpu':68,'temperature':58,'ram_used':12.4,'ram_total':32,'download':24.8,'upload':1.2}.items()} if args.demo else collector.collect())
  for i in range(120):frame=renderer.render(samples,now=now+i/60)
  frame.save(args.snapshot);collector.gpu.close();return
 QQuickStyle.setStyle('Basic')
 app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);app.setApplicationName('RIO System Monitor');app.setFont(QFont('Segoe UI',10))
 assets=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'assets';app.setWindowIcon(QIcon(str(assets/'rio-icon.ico')))
 settings=Settings() if args.ui_capture else load();weather=WeatherWorker(settings);provider=Frames();bridge=Bridge(app,settings,weather,provider,bool(args.ui_capture));engine=QQmlApplicationEngine();engine.addImageProvider('monitor',provider);engine.rootContext().setContextProperty('bridge',bridge);engine.load(QUrl.fromLocalFile(str(assets/'ui/Main.qml')))
 if not engine.rootObjects():raise RuntimeError('Qt Quick main window failed to load')
 bridge.win=engine.rootObjects()[0];bridge.tray=QSystemTrayIcon(app.windowIcon(),app);bridge.tray.setToolTip('RIO System Monitor');bridge.updateMenu();bridge.tray.activated.connect(lambda reason:bridge.show() if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick) else None)
 if not args.ui_capture:bridge.tray.show()
 if settings.start_hidden and not args.ui_capture:bridge.hideWindow()
 frames=queue.Queue(maxsize=1);stop=threading.Event();output=[None]
 def render_loop():
  renderer=Renderer();collector=Collector();samples={};next_sample=0
  try:
   while not stop.is_set():
    started=time.monotonic()
    if started>=next_sample:samples=collector.collect();next_sample=started+1
    if bridge.visible or output[0]:
     frame=renderer.render(samples,weather=weather.reading)
     if output[0] and not output[0].error:output[0].submit(frame.rotate(-bridge.s.rotation) if bridge.s.rotation else frame)
     if bridge.visible:
      try:frames.get_nowait()
      except queue.Empty:pass
      frames.put_nowait(frame.tobytes())
    stop.wait(max(.005,1/bridge.s.fps-(time.monotonic()-started)))
  finally:collector.gpu.close()
 worker=threading.Thread(target=render_loop,daemon=True);worker.start()
 def tick():
  bridge.consume()
  try:data=frames.get_nowait();provider.image=QImage(data,480,480,480*3,QImage.Format_RGB888).copy();bridge._frame+=1;bridge.frameChanged.emit()
  except queue.Empty:pass
 timer=QTimer();timer.timeout.connect(tick);timer.start(67)
 def shutdown():
  stop.set();weather.close()
  if output[0] and not output[0].close():return False
  worker.join(2);return not worker.is_alive()
 bridge.shutdown=shutdown
 def connect():
  try:
   from .winusb import enumerate_paths
   from .output import ScreenOutput
   paths=enumerate_paths()
   if len(paths)==1:output[0]=ScreenOutput(paths[0])
  except Exception:pass
 if not args.ui_capture:QTimer.singleShot(500,connect)
 if args.ui_capture:
  args.ui_capture.mkdir(parents=True,exist_ok=True)
  def capture_main():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-main.png'));popup=bridge.win.findChild(QObject,'cityPopup');popup.setProperty('visible',True);QTimer.singleShot(350,capture_city)
  def capture_city():
   bridge.win.grabWindow().save(str(args.ui_capture/'qt-city.png'))
   if args.self_test:
    proof={'single_main_window':len(engine.rootObjects())==1,'content_width':420,'outer_width':bridge.win.width(),'frameless':bool(bridge.win.flags() & Qt.FramelessWindowHint)}
    bridge.tray.show();bridge.setLanguage('zh');proof['chinese_menu']=[a.text() for a in bridge.menu.actions()]==['设置','最小化','登录后自动启动','退出']
    bridge.toggleAuto();proof['autostart_sync']=bridge.s.autostart and bridge.menu.actions()[2].isChecked()
    bridge.hideWindow();proof['hide_to_tray']=not bridge.win.isVisible() and bridge.tray.isVisible();bridge.show();proof['restore']=bridge.win.isVisible()
    bridge.setLanguage('en');proof['english_menu']=[a.text() for a in bridge.menu.actions()]==['Settings','Minimize','Start at login','Exit']
    assert all(v for k,v in proof.items() if k not in ('content_width','outer_width')),proof
    (args.ui_capture/'qt-proof.json').write_text(json.dumps(proof,indent=2))
   bridge.exit()
  QTimer.singleShot(1800,capture_main)
 result=app.exec();shutdown();return result
if __name__=='__main__':main()

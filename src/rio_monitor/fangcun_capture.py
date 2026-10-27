"""Explicit offline acceptance mode: no USB enumeration or transport is opened."""
import hashlib
import json
import threading
import time
from pathlib import Path
from PySide6.QtCore import QTimer,QObject,QMetaObject,Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from rio_fangcun.canvas import rgba
from rio_fangcun.runtime import Runtime

class CaptureOutput:
    def __init__(self,path):self.error=None;self.sent=0;self.frame=None;self.finished=threading.Event()
    @property
    def needs_frame(self):return not self.finished.is_set()
    def submit(self,frame):self.frame=frame.copy();self.sent+=1
    def close(self):self.finished.set();return True

def capture(app,bridge,game_bridge,service,session,provider,game_provider,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    bridge.win.setProperty('gameTab',False)
    panel=None
    began=time.monotonic();stage=-2;checks=[];flight_seen=set();hidden_frame=0;hidden_at=0;paused_at=0;background_at=0;background_xp=0;last_frames=0
    keepers=[]
    def find(name):
        pending=list(app.topLevelWindows());seen=set()
        while pending:
            candidate=pending.pop()
            if candidate in seen:continue
            seen.add(candidate);keepers.append(candidate)
            if candidate.objectName()==name:return candidate
            pending.extend(candidate.children())
            if hasattr(candidate,'childItems'):pending.extend(candidate.childItems())
            if hasattr(candidate,'contentItem'):pending.append(candidate.contentItem())
        raise AssertionError('Unavailable UI object: '+name)
    def click(name):
        obj=find(name)
        if not obj.property('enabled'):raise AssertionError('Unavailable UI action: '+name)
        window=obj.window();point=obj.mapToScene(QPointF(obj.width()/2,obj.height()/2));global_pos=QPointF(window.mapToGlobal(point.toPoint()))
        for kind,buttons in [(QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)]:
            QApplication.sendEvent(window,QMouseEvent(kind,point,global_pos,Qt.LeftButton,buttons,Qt.NoModifier))
    def shot(name):
        window=bridge.win if name.startswith('native-settings') else game_bridge.window or bridge.win
        if name=='native-merchant' or name.startswith('native-journey'):window=find('gameDetailPopup')
        window.grabWindow().save(str(directory/(name+'.png')))
    def finish(error=None):
        timer.stop();service.close()
        report={'checks':checks,'error':error,'no_usb':True,'rendered_frames':service.rendered,'last_render_ms':service.render_ms,'source':'native Qt Settings and existing output pipeline'}
        (directory/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        bridge.exit()
    def tick():
        nonlocal panel,stage,hidden_frame,hidden_at,paused_at,background_at,background_xp,last_frames
        try:
            if time.monotonic()-began>100:raise AssertionError('Offline native capture timeout at stage '+str(stage))
            g=service.snapshot();s=g.get('state',{});f=g.get('flight')
            if g.get('error'):raise AssertionError(g['error'])
            if not g.get('ready'):return
            if stage==-2:
                if bridge._frame<2:return
                assert not game_bridge.gourd.isVisible() and not service.graphics_loaded
                shot('native-settings-off')
                switch=bridge.win.findChild(QObject,'cultivationSwitch');switch.setProperty('checked',True);QMetaObject.invokeMethod(switch,'toggled')
                assert game_bridge.enabled and game_bridge.gourd.isVisible();checks.append('native music-style switch enables gourd and exclusive game output');stage=-1;return
            if stage==-1:
                if service.frame_id<2:return
                game_bridge.gourd.grab().save(str(directory/'native-gourd.png'))
                gourd=game_bridge.gourd
                original=gourd.pos();local=QPointF(32,42);global_pos=QPointF(gourd.mapToGlobal(QPoint(32,42)))
                QApplication.sendEvent(gourd,QMouseEvent(QEvent.MouseButtonPress,local,global_pos,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
                destination=global_pos+QPointF(-90,-60)
                QApplication.sendEvent(gourd,QMouseEvent(QEvent.MouseMove,local+QPointF(-90,-60),destination,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                QApplication.sendEvent(gourd,QMouseEvent(QEvent.MouseButtonRelease,local,destination,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
                assert gourd.pos()==original+QPoint(-90,-60)
                assert (bridge.s.gourd_x,bridge.s.gourd_y)==(gourd.x(),gourd.y())
                assert not bridge.win.property('gameTab');checks.append('gourd drag changes stored position without opening panel')
                local=QPointF(32,42);global_pos=QPointF(gourd.mapToGlobal(QPoint(32,42)))
                for kind,buttons in [(QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)]:
                    QApplication.sendEvent(gourd,QMouseEvent(kind,local,global_pos,Qt.LeftButton,buttons,Qt.NoModifier))
                assert game_bridge.window.isVisible() and game_bridge.window is not bridge.win;panel=game_bridge.window.findChild(QObject,'fangcunPanel');checks.append('gourd click opens independent native control panel');stage=0;return
            if service.frame_id<2:return
            if stage==0:
                shot('native-main');click('nav_bag');panel.setProperty('section','shop');panel.setProperty('selected','orb');stage=1
            elif stage==1:
                shot('native-merchant');click('use_orb');stage=2
            elif stage==2 and s['inventory'].get('orb')==1:
                assert s['stones']==10;checks.append('merchant purchase deducts exact stones');panel.setProperty('section','bag');panel.setProperty('inventoryCategory',0);stage=3
            elif stage==3:
                click('use_orb');stage=4
            elif stage==4 and s['equipment']=='orb':
                checks.append('native bag equips original spell');shot('native-equipped');click('gameDetailClose');click('nav_journey');stage=41
            elif stage==41:
                shot('native-journey-zh');bridge.setLanguage('en');stage=42
            elif stage==42:
                if game_bridge._state.get('expedition',{}).get('regions',[{}])[0].get('name')!='Qinglan Trail':return
                stage=421
            elif stage==421:
                shot('native-journey-en');assert not panel.property('zh');bridge.setLanguage('zh');stage=43
            elif stage==43:
                if game_bridge._state.get('expedition',{}).get('regions',[{}])[0].get('name')!='青岚山径':return
                stage=431
            elif stage==431:
                checks.append('native journey card CN/EN and region selection');click('journeyDepart');stage=5
            elif stage==5:
                if f and f['phase'] not in flight_seen and f['phase'] in ['rise','clear-origin','cloud-cruise','arrive']:
                    shot('native-'+f['phase']);flight_seen.add(f['phase'])
                if g['mode']=='attack' and not f:
                    shot('native-combat');checks.append('rise/flight/landing/walk/run/attack');click('nav_journey');stage=51
            elif stage==51:
                click('journeyDepart');stage=6
            elif stage==6:
                if f and f['phase']=='sit' and 'sit' not in flight_seen:shot('native-sit');flight_seen.add('sit')
                if g['mode']=='meditate' and not f:
                    if g.get('expedition',{}).get('knockout'):return
                    checks.append('combat retreat returns safely or rescues after collapse');hidden_frame=g['frame'];hidden_at=time.monotonic();game_bridge.hidePanel();stage=7
            elif stage==7 and time.monotonic()-hidden_at>.7:
                assert g['frame']>hidden_frame+10;checks.append('hidden Settings keeps simulation running');game_bridge.openPanel();click('nav_cave');click('gamePauseButton');stage=8
            elif stage==8 and g['paused']:
                paused_at=time.monotonic();stage=9
            elif stage==9 and time.monotonic()-paused_at>.4:
                im,_=service.latest()
                if not session.output or session.output.frame is None:return
                raw=im.tobytes()
                if raw!=session.output.frame.tobytes() or raw!=rgba(provider.image).convert('RGB').tobytes() or raw!=rgba(game_provider.image).convert('RGB').tobytes():return
                checks.append('identical frame reaches game preview, monitor preview and output')
                service.command('export',str(directory/'export.json'));stage=10
            elif stage==10 and (directory/'export.json').exists():
                exported=json.loads((directory/'export.json').read_text(encoding='utf-8'));assert exported['paused'] and exported['state']['equipment']=='orb'
                service.command('import',json.dumps(exported));stage=11
            elif stage==11 and g['message']=='存档已恢复，回到方寸山。':
                checks.append('export/import preserves inventory/equipment/paused');shot('native-final')
                # Same source frame feeds preview/output; compare each cached frame's origin on pause.
                checks.append('single service supplies both preview and existing DisplaySession')
                bridge.show();switch=bridge.win.findChild(QObject,'cultivationSwitch');switch.setProperty('checked',False);QMetaObject.invokeMethod(switch,'toggled');stage=12
            elif stage==12 and g.get('background') and not service.graphics_loaded:
                assert not game_bridge.gourd.isVisible();background_at=time.monotonic();background_xp=s['xp'];last_frames=service.rendered;shot('native-settings-return');stage=13
            elif stage==13 and time.monotonic()-background_at>6:
                assert s['xp']>background_xp+2 and service.rendered==last_frames
                assert service.latest()[0] is None;checks.append('OFF keeps slow gains with zero game frames and released image cache')
                assert session.output and session.output.frame;checks.append('OFF resumes monitor output through same session')
                service.close();saved=json.loads(service.store.path.read_text(encoding='utf-8'))
                reopened=Runtime(service.assets,saved,saved['state']['savedAt']+60000);a=reopened.call('snapshot');assert a['state']['xp']==saved['state']['xp'];assert reopened.canvas is None
                checks.append('reopen preserves exact progress and lazy graphics; no closed-RIO bonus')
                checks.append('all captured phases: '+','.join(sorted(flight_seen)));finish()

        except Exception as exc:finish(str(exc))
    timer=QTimer(app);timer.setInterval(100);timer.timeout.connect(tick);timer.start()

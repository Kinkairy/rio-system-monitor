import unittest,tempfile,time,math,io
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from rio_monitor.music.state import Track,Audio,Spectrum,select_session
from rio_monitor.music.lyrics import parse_lrc,current_lines,lookup
from rio_monitor.music.controller import Music
from rio_monitor.music.renderer import MusicRenderer

class MusicTests(unittest.TestCase):
 def test_timeline_and_stale(self):
  t=Track(title='Song',duration=10,position=2,playing=True,observed=100)
  self.assertEqual(t.position_at(102),4);self.assertIsNone(t.position_at(104))
  self.assertIsNone(Track().position_at(10))
 def test_session_choice_is_stable_and_explicit(self):
  rows=[('browser',True,1),('qqmusic',True,2)]
  self.assertEqual(select_session(rows,previous='qqmusic')[0],'qqmusic')
  self.assertIsNone(select_session(rows,preferred='missing'))
 def test_lrc_multiple_timestamps_offset_and_seek(self):
  rows=parse_lrc('[offset:100]\n[00:01.20][00:05.300]first\n[00:03]next')
  self.assertEqual([round(r.time,2) for r in rows],[1.3,3.1,5.4])
  self.assertEqual(current_lines(rows,4),('next','first'))
  self.assertEqual(current_lines(rows,.2),('','first'))
  self.assertEqual(current_lines(rows,None),('',''))
 def test_audio_stale_decays_to_zero(self):
  a=Audio((1,)*12,1,10,'ready');self.assertEqual(a.current(11).level,0)
 def test_spectrum_silence_tone_and_antiphase(self):
  import numpy as np
  analyzer=Spectrum(48000);x=np.sin(np.arange(2048)*2*np.pi*1000/48000)*.4
  a=analyzer.analyze(np.column_stack([x,-x]).ravel(),2,10)
  self.assertGreater(a.level,.5);self.assertEqual(len(a.bands),12)
  self.assertGreater(max(a.bands),.5)
  self.assertEqual(analyzer.analyze(np.zeros(4096),2,10).level,0)
 def test_disabled_does_not_publish_or_query(self):
  with tempfile.TemporaryDirectory() as tmp:
   music=Music(tmp,start=False);music.media_update(Track(title='ignored'),[],'ready');self.assertFalse(music.snapshot()['track'].title)
   music.configure(True,False,'');music.media_update(Track(title='A'),[],'ready');self.assertEqual(music.snapshot()['track'].title,'A')
   music.configure(False,False,'');self.assertFalse(music.snapshot()['track'].title);self.assertEqual(music.snapshot()['audio'].level,0)
 def test_local_import_associates_with_current_track(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Music(tmp,enabled=True,start=False);m.media_update(Track(title='A',artist='B'),[],'ready')
   p=Path(tmp)/'input.lrc';p.write_text('[00:01]line',encoding='utf-8');m.import_lrc(p)
   self.assertEqual(m.snapshot()['rows'][0].text,'line')
   m.media_update(Track(title='Other',artist='B'),[],'ready');self.assertEqual(m.snapshot()['rows'],())
 def test_lookup_is_metadata_only_and_rejects_wrong_version(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{"duration":100,"trackName":"different","artistName":"Artist","syncedLyrics":"[00:01]line"}'
  with patch('urllib.request.urlopen',return_value=Response()) as request:
   rows,status=lookup(Track(title='Song',artist='Artist',duration=100))
   self.assertEqual(status,'not_found');self.assertFalse(rows)
   self.assertTrue(request.call_args.args[0].full_url.startswith('https://lrclib.net/api/get?'))
 def test_render_empty_pause_and_transition_without_private_assets(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=MusicRenderer(tmp)
   snapshot=dict(track=Track(),audio=Audio(),rows=(),lyric_status='off')
   self.assertEqual(r.render(snapshot,0).size,(480,480))
   snapshot['track']=Track(title='FIRST',artist='Artist',playing=True,position=1,duration=100,observed=1)
   r.render(snapshot,1);angle=r.angle
   snapshot['track']=Track(title='FIRST',artist='Artist',playing=False,position=1,duration=100,observed=1.1)
   r.render(snapshot,1.1);self.assertEqual(r.angle,angle)
   snapshot['track']=Track(title='SECOND',playing=True,observed=1.2)
   for t in (1.2,1.3,1.5,1.6,2):self.assertEqual(r.render(snapshot,t).mode,'RGB')

class MusicUI(unittest.TestCase):
 def test_qml_loads_with_music_controls(self):
  import os
  os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
  try:
   from PySide6.QtWidgets import QApplication
   from PySide6.QtQml import QQmlApplicationEngine
   from PySide6.QtCore import QUrl,QObject
   from rio_monitor.qt_app import Bridge,Frames
   from rio_monitor.settings import Settings
   from unittest.mock import Mock
  except ImportError:self.skipTest('Qt not installed')
  app=QApplication.instance() or QApplication([]);weather=Mock();weather.location=None
  bridge=Bridge(app,Settings(),weather,Frames(),capture=True)
  engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('bridge',bridge);engine.addImageProvider('monitor',bridge.frames)
  engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'assets/ui/Main.qml')))
  self.assertTrue(engine.rootObjects());window=engine.rootObjects()[0];bridge.win=window
  self.assertIsNotNone(window.findChild(QObject,'musicPopup'));self.assertIsNotNone(window.findChild(QObject,'musicSwitch'))
  bridge.setMusicEnabled(True);self.assertTrue(bridge.s.music_enabled)
  bridge.setMusicEnabled(False);self.assertFalse(bridge.music.enabled)
  bridge.save_timer.stop();bridge.storage.close();
  from shiboken6 import delete
  delete(engine)

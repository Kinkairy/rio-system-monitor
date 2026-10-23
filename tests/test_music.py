import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,AsyncMock
from PIL import Image
from rio_monitor.music.state import Track,Audio,Spectrum,select_session,AutomaticMusicView
from rio_monitor.music.lyrics import Lyric,parse_lrc,current_lines,lookup
from rio_monitor.music.controller import Music
from rio_monitor.music.renderer import MusicRenderer,marquee_offset
from rio_monitor.music.windows import CoverCache

class CoverTests(unittest.IsolatedAsyncioTestCase):
 async def test_delayed_thumbnail_retries_after_empty_and_failed_reads(self):
  cache=CoverCache();reader=AsyncMock(side_effect=[b'',OSError('not ready'),b'cover'])
  with patch('rio_monitor.music.windows.read_cover',reader):
   self.assertEqual(await cache.get('song',None,100),b'')
   self.assertEqual(await cache.get('song','thumbnail',101.9),b'')
   self.assertEqual(reader.await_count,1)
   self.assertEqual(await cache.get('song','thumbnail',102),b'')
   self.assertEqual(await cache.get('song','thumbnail',104),b'cover')
   self.assertEqual(await cache.get('song',None,110),b'cover')
   self.assertEqual(reader.await_count,3)
 async def test_track_change_drops_previous_cover_before_retry(self):
  cache=CoverCache()
  with patch('rio_monitor.music.windows.read_cover',AsyncMock(side_effect=[b'first',b'',b'second'])):
   self.assertEqual(await cache.get('one','thumbnail',100),b'first')
   self.assertEqual(await cache.get('two',None,100.5),b'')
   self.assertEqual(await cache.get('two','thumbnail',102.5),b'second')

class MusicTests(unittest.TestCase):
 def test_long_lyrics_keep_all_words_and_scroll_horizontally_with_original_fonts(self):
  from dataclasses import replace
  with tempfile.TemporaryDirectory() as tmp:
   renderer=MusicRenderer(tmp);text='A LONG LYRIC LINE WITH ENOUGH WORDS TO REQUIRE SEVERAL PAGES AND SHOW EVERY WORD'
   wrapped=renderer.wrap_text(text,19);self.assertGreater(len(wrapped),2)
   font=renderer.font(renderer.chinese,19)
   self.assertTrue(all(font.getlength(line)<=125 for line in wrapped));self.assertEqual(''.join(wrapped),text)
   state=dict(track=Track(title='Song',duration=30,position=0,observed=100),rows=(Lyric(0,text),Lyric(10,'NEXT LINE')),lyric_status='ready')
   offsets=[]
   for position in (0,2,2.01,5,9.9):
    state['track']=replace(state['track'],position=position)
    parts,following,offset=renderer.lyric_lines(state,100,False)
    self.assertEqual(''.join(parts),text);offsets.append(offset)
    self.assertEqual(parts[0],wrapped[0])
    self.assertGreater(renderer.lyric_strip(parts[1],23,'#f0e351').width,125)
   self.assertEqual(offsets[0],0);self.assertGreater(offsets[-1],0)
   self.assertTrue(all(a<=b for a,b in zip(offsets,offsets[1:])))
   self.assertGreater(offsets[2],offsets[1]);self.assertLess(offsets[2]-offsets[1],1)
   state['track']=replace(state['track'],position=10)
   self.assertEqual(renderer.lyric_lines(state,100,False)[0],('NEXT LINE',''))
 def test_paused_lyric_scroll_is_stable_and_seeking_back_restores_start(self):
  from dataclasses import replace
  with tempfile.TemporaryDirectory() as tmp:
   renderer=MusicRenderer(tmp);text=' '.join(['LONG LYRIC']*14)
   state=dict(track=Track(title='Song',duration=40,position=8,observed=100),rows=(Lyric(0,text),Lyric(10,'NEXT')),lyric_status='ready')
   paused=renderer.lyric_lines(state,100,False)
   self.assertEqual(renderer.lyric_lines(state,102,False),paused)
   state['track']=replace(state['track'],position=0)
   self.assertEqual(renderer.lyric_lines(state,100,False)[2],0)
 def test_title_scrolls_both_directions_with_pauses_and_short_titles_stay_still(self):
  # 64 extra pixels at 32 pixels/second: hold, travel, hold, return, repeat.
  expected={0:0,.5:0,1:0,2:32,3:64,3.5:64,4:64,5:32,6:0,6.5:0}
  for elapsed,offset in expected.items():self.assertAlmostEqual(marquee_offset(374,310,elapsed),offset)
  for elapsed in (0,1,100):self.assertEqual(marquee_offset(200,310,elapsed),0)
 def test_title_render_is_clipped_and_returns_to_first_position(self):
  with tempfile.TemporaryDirectory() as tmp:
   renderer=MusicRenderer(tmp);title='A LONG SONG TITLE THAT MUST SCROLL TO SHOW THE END'
   def draw(now):
    frame=Image.new('RGB',(480,480),'black');renderer.draw_title(frame,title,now);return frame
   first=draw(100);moving=draw(102)
   width=renderer.title_strip(title,renderer.pixel).width
   returned=draw(100+2*(max(0,width-310)/32+1))
   self.assertNotEqual(first.tobytes(),moving.tobytes());self.assertEqual(first.tobytes(),returned.tobytes())
   self.assertIsNone(moving.crop((0,0,85,480)).getbbox());self.assertIsNone(moving.crop((395,0,480,480)).getbbox())
 def test_automatic_view_waits_30_seconds_after_pause_or_stop(self):
  from dataclasses import replace
  view=AutomaticMusicView()
  state=dict(enabled=True,status='ready',track=Track(playing=True,observed=100))
  paused=dict(state,track=replace(state['track'],playing=False))
  self.assertFalse(view.select(paused,100))
  self.assertTrue(view.select(state,101));self.assertTrue(view.select(paused,102))
  self.assertTrue(view.select(paused,131.99));self.assertFalse(view.select(paused,132))
  playing=dict(state,track=replace(state['track'],observed=140))
  self.assertTrue(view.select(playing,140));self.assertTrue(view.select(dict(state,status='no_session'),141))
  self.assertFalse(view.select(dict(state,status='no_session'),171))
 def test_playback_resumes_cancel_timeout_and_disabling_returns_immediately(self):
  view=AutomaticMusicView()
  def state(playing,observed,enabled=True):return dict(enabled=enabled,status='ready',track=Track(playing=playing,observed=observed))
  self.assertTrue(view.select(state(True,100),100));self.assertTrue(view.select(state(False,101),101))
  self.assertTrue(view.select(state(True,125),125));self.assertIsNone(view.idle_since)
  self.assertTrue(view.select(state(False,126),126));self.assertTrue(view.select(state(False,155),155))
  self.assertFalse(view.select(state(False,156),156))
  self.assertTrue(view.select(state(True,160),160));self.assertFalse(view.select(state(True,161,False),161))
  self.assertFalse(view.select(state(False,162),162))
 def test_stale_or_unavailable_player_does_not_keep_auto_view_forever(self):
  view=AutomaticMusicView();state=dict(enabled=True,status='ready',track=Track(playing=True,observed=100))
  self.assertTrue(view.select(state,100));self.assertTrue(view.select(state,104))
  self.assertTrue(view.select(state,133.99));self.assertFalse(view.select(state,134))
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
  self.assertTrue(window.findChild(QObject,'musicSwitch').isVisible())
  bridge.setMusicEnabled(True);self.assertTrue(bridge.s.music_enabled)
  bridge.setMusicEnabled(False);self.assertFalse(bridge.music.enabled)
  bridge.save_timer.stop();bridge.storage.close();
  from shiboken6 import delete
  delete(engine)

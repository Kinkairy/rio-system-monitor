import unittest,tempfile,os
from unittest.mock import patch
from pathlib import Path
from rio_monitor.settings import Settings,save,load,config_path
class SettingTests(unittest.TestCase):
 def test_online_lyrics_default_on_but_music_requires_enabled_switch(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   self.assertTrue(load().music_online_lyrics);self.assertEqual(load().music_lyrics_consent,2)
   self.assertFalse(load().music_enabled)
   save(Settings(music_online_lyrics=False,music_lyrics_consent=0))
   self.assertFalse(load().music_online_lyrics)
 def test_roundtrip(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   s=Settings(20,90,'auto','',True,False);save(s);self.assertEqual(s,load())
   config_path().write_text('{bad');self.assertEqual(load(),Settings())
 def test_unknown_and_invalid(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   config_path().parent.mkdir(parents=True);config_path().write_text('{"fps":999}');self.assertEqual(load(),Settings())
 def test_old_start_minimized_setting_migrates_to_default_tray_behavior(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   config_path().parent.mkdir(parents=True);config_path().write_text('{"rotation":39,"start_hidden":false}')
   self.assertTrue(load().start_hidden);self.assertEqual(load().rotation,39)
 def test_every_launch_resumes_monitor_even_after_stored_content_mode(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   save(Settings(rotation=39,display_mode='stored'))
   self.assertEqual(load().display_mode,'monitor');self.assertEqual(load().rotation,39)

import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
from rio_monitor.music.state import Track
from rio_monitor.music.platforms import identify_player,Candidate,match_candidate,lookup_platform
from rio_monitor.music.lyrics import lookup,parse_lrc
from rio_monitor import settings

class PlatformLyricsTests(unittest.TestCase):
 def track(self,source='QQMusic.exe'):
  return Track(source=source,title='Song',artist='Artist',album='Album',duration=100)
 def test_identity_conservative(self):
  for value in ('QQMusic.exe','C:\\Apps\\QQMusic.exe','Tencent.QQMusic_ab12!App'):self.assertEqual(identify_player(value),'qq')
  for value in ('cloudmusic.exe','NetEase.CloudMusic_ab12!App'):self.assertEqual(identify_player(value),'netease')
  for value in ('chrome.exe','LX Music','notqqmusic.exe','QQMusicHelper.exe','unknown'):self.assertIsNone(identify_player(value))
 def test_matching_rejects_wrong_version_artist_album_and_ambiguity(self):
  good=Candidate('1','Song',('Artist',),'Album',100)
  self.assertEqual(match_candidate(self.track(),[good]),good)
  for c in (Candidate('2','Song (Live)',('Artist',),'Album',100),Candidate('2','Song',('Other',),'Album',100),Candidate('2','Song',('Artist',),'Other',100),Candidate('2','Song',('Artist',),'Album',104)):
   self.assertIsNone(match_candidate(self.track(),[c]))
  self.assertIsNone(match_candidate(self.track(),[good,Candidate('2','Song',('Artist',),'Album',100)]))
 def test_qq_success(self):
  search={'code':0,'data':{'song':{'list':[{'songmid':'abc123','songname':'Song','singer':[{'name':'Artist'}],'albumname':'Album','interval':100}]}}}
  with patch('rio_monitor.music.platforms.request_json',side_effect=[search,{'code':0,'lyric':'[00:01]test'}]) as request:
   rows,status=lookup_platform(self.track());self.assertEqual(status,'ready');self.assertEqual(rows[0].time,1);self.assertEqual(request.call_count,2)
 def test_netease_success(self):
  search={'code':200,'result':{'songs':[{'id':1,'name':'Song','ar':[{'name':'Artist'}],'al':{'name':'Album'},'dt':100000}]}}
  with patch('rio_monitor.music.platforms.request_json',side_effect=[search,{'code':200,'lrc':{'lyric':'[00:01]test'}}]) as request:
   rows,status=lookup_platform(self.track('cloudmusic.exe'));self.assertEqual(status,'ready');self.assertTrue(rows);self.assertEqual(request.call_count,2)
 def test_encrypted_or_changed_schema_fails_closed(self):
  with patch('rio_monitor.music.platforms.request_json',return_value={'code':200,'result':'encrypted'}):
   self.assertEqual(lookup_platform(self.track('cloudmusic.exe')),((),'provider_error'))
 def test_unknown_does_not_query_platform(self):
  with patch('rio_monitor.music.platforms.request_json') as request:
   self.assertEqual(lookup_platform(self.track('chrome.exe')),((),'unsupported_source'));request.assert_not_called()
 def test_platform_failure_falls_back_and_success_does_not(self):
  with patch('rio_monitor.music.platforms.lookup_platform',return_value=((),'provider_error')),patch('rio_monitor.music.lyrics.lookup_lrclib',return_value=((),'not_found')) as fallback:
   self.assertEqual(lookup(self.track()),((),'not_found'));fallback.assert_called_once()
  rows=parse_lrc('[00:01]test')
  with patch('rio_monitor.music.platforms.lookup_platform',return_value=(rows,'ready')),patch('rio_monitor.music.lyrics.lookup_lrclib') as fallback:
   self.assertEqual(lookup(self.track()),(rows,'ready'));fallback.assert_not_called()
 def test_network_error_does_not_escape(self):
  with patch('rio_monitor.music.platforms.request_json',side_effect=TimeoutError):self.assertEqual(lookup_platform(self.track()),((),'provider_error'))
 def test_old_consent_does_not_enable_new_recipients(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'settings.json'
   with patch('rio_monitor.settings.config_path',return_value=path):
    path.write_text(json.dumps({'music_online_lyrics':True,'music_enabled':True}));self.assertFalse(settings.load().music_online_lyrics)
    path.write_text(json.dumps({'music_online_lyrics':True,'music_lyrics_consent':2}));self.assertTrue(settings.load().music_online_lyrics)

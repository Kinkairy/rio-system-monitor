import unittest,json,tempfile,urllib.parse,base64,threading
from pathlib import Path
from unittest.mock import patch
from rio_monitor.music.state import Track
from rio_monitor.music.platforms import identify_player,Candidate,match_candidate,lookup_platform,request_json
from rio_monitor.music.lyrics import lookup,parse_lrc
from rio_monitor import settings

class PlatformLyricsTests(unittest.TestCase):
 def track(self,source='QQMusic.exe'):
  return Track(source=source,title='Song',artist='Artist',album='Album',duration=100)
 def test_identity_conservative(self):
  for value in ('QQMusic.exe','C:\\Apps\\QQMusic.exe','Tencent.QQMusic_ab12!App'):self.assertEqual(identify_player(value),'qq')
  for value in ('cloudmusic.exe','NetEase.CloudMusic_ab12!App'):self.assertEqual(identify_player(value),'netease')
  self.assertEqual(identify_player('KuGou.exe'),'kugou')
  for value in ('chrome.exe','LX Music','notqqmusic.exe','QQMusicHelper.exe','unknown'):self.assertIsNone(identify_player(value))
 def test_matching_rejects_wrong_version_artist_album_and_ambiguity(self):
  good=Candidate('1','Song',('Artist',),'Album',100)
  self.assertEqual(match_candidate(self.track(),[good]),good)
  for c in (Candidate('2','Song (Live)',('Artist',),'Album',100),Candidate('2','Song',('Other',),'Album',100),Candidate('2','Song',('Artist',),'Other',100),Candidate('2','Song',('Artist',),'Album',104)):
   self.assertIsNone(match_candidate(self.track(),[c]))
  self.assertIsNone(match_candidate(self.track(),[good,Candidate('2','Song',('Artist',),'Album',100)]))
 def test_qq_success(self):
  from dataclasses import replace
  search={'code':0,'data':{'song':{'itemlist':[{'mid':'wrongversion'},{'mid':'abc123'},{'mid':'abc123'}]}}}
  def detail(mid,duration):return {'code':0,'data':{'track_info':{'mid':mid,'title':'Song','singer':[{'name':'Utada','title':'Utada (宇多田光)'}],'album':{'name':'Album'},'interval':duration}}}
  details={'code':0,'wrongversion':detail('wrongversion',130),'abc123':detail('abc123',100)}
  for artist in ('Utada','Utada (宇多田光)'):
   with self.subTest(artist=artist),patch('rio_monitor.music.platforms.request_json',side_effect=[search,details,{'code':0,'lyric':'[00:01]test'}]) as request:
    rows,status=lookup_platform(replace(self.track('chrome.exe'),artist=artist),'qq');self.assertEqual(status,'ready');self.assertEqual(rows[0].time,1);self.assertEqual(request.call_count,3)
    calls=request.call_args_list;url=urllib.parse.urlsplit(calls[0].args[0]);self.assertTrue(url.path.endswith('/smartbox_new.fcg'))
    self.assertEqual(urllib.parse.parse_qs(url.query)['key'],['Song'])
    batch=calls[1].kwargs['json_body'];self.assertEqual(set(batch),{'wrongversion','abc123'});self.assertEqual(batch['abc123']['param'],{'song_mid':'abc123'})
    self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(calls[2].args[0]).query)['songmid'],['abc123'])
 def test_netease_success(self):
  search={'code':200,'result':{'songs':[{'id':1,'name':'Song','ar':[{'name':'Artist'}],'al':{'name':'Album'},'dt':100000}]}}
  with patch('rio_monitor.music.platforms.request_json',side_effect=[search,{'code':200,'lrc':{'lyric':'[00:01]test'}}]) as request:
   rows,status=lookup_platform(self.track('cloudmusic.exe'));self.assertEqual(status,'ready');self.assertTrue(rows);self.assertEqual(request.call_count,2)
 def test_kugou_uses_matching_timed_song_and_rejects_wrong_version(self):
  candidates=[dict(id='live',accesskey='public',song='Song (Live)',singer='Artist',duration=100000),dict(id='good',accesskey='public',song='Song',singer='Artist',duration=100020),dict(id='other',accesskey='public',song='Song',singer='Other',duration=100000)]
  search={'status':200,'candidates':candidates};download={'status':200,'content':base64.b64encode(b'[00:01]line').decode()}
  with patch('rio_monitor.music.platforms.request_json',side_effect=[search,download]) as request:
   rows,status=lookup_platform(self.track('KuGou.exe'));self.assertEqual(status,'ready');self.assertTrue(rows)
   self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)['id'],['good'])
  with patch('rio_monitor.music.platforms.request_json',return_value=dict(search,candidates=[candidates[0],candidates[2]])) as request:
   self.assertEqual(lookup_platform(self.track(),'kugou'),((),'not_found'));self.assertEqual(request.call_count,1)
 def test_musicu_request_sends_json_post(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{"code":0}'
  payload={'req':{'param':{'query':'Song Artist'}}}
  with patch('urllib.request.urlopen',return_value=Response()) as send:
   self.assertEqual(request_json('https://u.y.qq.com/cgi-bin/musicu.fcg',json_body=payload),{'code':0})
   request=send.call_args.args[0];self.assertEqual(request.get_method(),'POST')
   self.assertEqual(request.get_header('Content-type'),'application/json');self.assertEqual(json.loads(request.data),payload)
 def test_encrypted_or_changed_schema_fails_closed(self):
  with patch('rio_monitor.music.platforms.request_json',return_value={'code':200,'result':'encrypted'}):
   self.assertEqual(lookup_platform(self.track('cloudmusic.exe')),((),'provider_error'))
 def test_unknown_does_not_query_platform(self):
  with patch('rio_monitor.music.platforms.request_json') as request:
   self.assertEqual(lookup_platform(self.track('chrome.exe')),((),'unsupported_source'));request.assert_not_called()
 def test_platform_failure_falls_back_and_success_does_not(self):
  with patch('rio_monitor.music.platforms.lookup_platform',return_value=((),'provider_error')),patch('rio_monitor.music.lyrics.lookup_lrclib',return_value=((),'not_found')) as fallback:
   self.assertEqual(lookup(self.track()),((),'provider_error'));fallback.assert_called_once()
  rows=parse_lrc('[00:01]test')
  with patch('rio_monitor.music.platforms.lookup_platform',return_value=((),'provider_error')),patch('rio_monitor.music.lyrics.lookup_lrclib',return_value=(rows,'ready')):
   self.assertEqual(lookup(self.track()),(rows,'ready'))
  with patch('rio_monitor.music.platforms.lookup_platform',return_value=(rows,'ready')),patch('rio_monitor.music.lyrics.lookup_lrclib') as fallback:
   self.assertEqual(lookup(self.track()),(rows,'ready'));fallback.assert_not_called()
 def test_fallbacks_race_after_native_failure_and_do_not_wait_for_slow_losers(self):
  release=threading.Event();started={name:threading.Event() for name in ('netease','kugou')};finished={name:threading.Event() for name in started};order=[]
  rows=parse_lrc('[00:01]fast')
  def platform(track,player):
   order.append(player)
   if player=='qq':return (),'provider_error'
   started[player].set()
   try:release.wait(3);return (),'not_found'
   finally:finished[player].set()
  def fast(track):
   self.assertTrue(all(event.wait(2) for event in started.values()));return rows,'ready'
  with patch('rio_monitor.music.platforms.lookup_platform',side_effect=platform),patch('rio_monitor.music.lyrics.lookup_lrclib',side_effect=fast):
   try:
    self.assertEqual(lookup(self.track()),(rows,'ready'));self.assertEqual(order[0],'qq')
    self.assertFalse(release.is_set());self.assertFalse(any(event.is_set() for event in finished.values()))
   finally:
    release.set()
    for event in finished.values():self.assertTrue(event.wait(2))
 def test_network_error_does_not_escape(self):
  with patch('rio_monitor.music.platforms.request_json',side_effect=TimeoutError):self.assertEqual(lookup_platform(self.track()),((),'provider_error'))
 def test_old_consent_does_not_enable_new_recipients(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'settings.json'
   with patch('rio_monitor.settings.config_path',return_value=path):
    path.write_text(json.dumps({'music_online_lyrics':True,'music_enabled':True}));self.assertFalse(settings.load().music_online_lyrics)
    path.write_text(json.dumps({'music_online_lyrics':True,'music_lyrics_consent':2}));self.assertTrue(settings.load().music_online_lyrics)

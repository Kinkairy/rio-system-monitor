import hashlib,io,json,os,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from rio_monitor.updater import ASSET_NAME,AutoUpdater,download_asset,latest_asset,launch_install


class UpdateTests(unittest.TestCase):
 def asset(self,content=b'new program'):
  return dict(name=ASSET_NAME,state='uploaded',version='rc0.1.2',size=len(content),
              digest='sha256:'+hashlib.sha256(content).hexdigest(),
              browser_download_url='https://github.com/Kinkairy/rio-system-monitor/releases/download/rc0.1.2/'+ASSET_NAME)
 def test_public_release_selection_only_returns_a_new_complete_program(self):
  asset=self.asset();release=dict(tag_name='rc0.1.2',draft=False,prerelease=False,assets=[asset])
  for current,expected in (('rc0.1',True),('rc0.1.1',True),('rc0.1.2',False),('rc0.2',False)):
   with self.subTest(current=current),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(release).encode())) as request:
    self.assertEqual(latest_asset(current) is not None,expected)
    self.assertFalse(request.call_args.args[0].has_header('Authorization'))
  release['assets'][0]['digest']=None
  with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(release).encode())):self.assertIsNone(latest_asset('rc0.1'))
 def test_download_stages_only_complete_updates_and_preserves_running_file_on_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);target=root/'RIO.exe';target.write_bytes(b'old program')
   asset=self.asset()
   with patch('urllib.request.urlopen',return_value=io.BytesIO(b'new program')):
    staged=download_asset(asset,root/'updates')
   self.assertEqual(staged.read_bytes(),b'new program');self.assertEqual(target.read_bytes(),b'old program')
   asset['version']='rc0.1.3'
   with patch('urllib.request.urlopen',return_value=io.BytesIO(b'truncated')):
    with self.assertRaises(ValueError):download_asset(asset,root/'updates')
   self.assertFalse((root/'updates/rc0.1.3.exe').exists());self.assertFalse((root/'updates/rc0.1.3.part').exists())
   self.assertEqual(target.read_bytes(),b'old program')
   updater=AutoUpdater(root/'updates');updater.pending=(staged,'rc0.1.2')
   with patch('rio_monitor.updater.launch_install') as install:
    updater.install_on_exit();self.assertTrue(updater.stop.is_set());install.assert_called_once()
 def test_progress_tracks_received_bytes_and_a_verified_cached_download(self):
  content=b'x'*(2*1024*1024+17);asset=self.asset(content);progress=[]
  with tempfile.TemporaryDirectory() as tmp:
   with patch('urllib.request.urlopen',return_value=io.BytesIO(content)):
    download_asset(asset,tmp,progress=lambda done,total:progress.append((done,total)))
   self.assertEqual(progress,[(n,len(content)) for n in (0,1024*1024,2*1024*1024,len(content))])
   progress.clear()
   with patch('urllib.request.urlopen') as request:
    download_asset(asset,tmp,progress=lambda done,total:progress.append((done,total)));request.assert_not_called()
   self.assertEqual(progress,[(len(content),len(content))])
 def test_manual_check_reports_progress_without_starting_duplicate_downloads(self):
  entered=threading.Event();finish=threading.Event()
  def download(asset,directory,stop,progress):
   progress(42,100);entered.set();finish.wait(3);return Path(directory)/'new.exe'
  with tempfile.TemporaryDirectory() as tmp:
   updater=AutoUpdater(tmp)
   with patch('rio_monitor.updater.latest_asset',return_value=self.asset()) as latest,patch('rio_monitor.updater.download_asset',side_effect=download) as fetch:
    try:
     updater.check();self.assertTrue(entered.wait(2))
     self.assertEqual(updater.snapshot(),dict(state='downloading',connection='connected',progress=42))
     updater.check();latest.assert_called_once();fetch.assert_called_once()
    finally:finish.set();updater.worker.join(3)
    self.assertEqual(updater.snapshot(),dict(state='ready',connection='connected',progress=100))
    updater.check();fetch.assert_called_once()
 def test_latest_connection_failure_and_download_failure_remain_distinct(self):
  with tempfile.TemporaryDirectory() as tmp:
   for result,error,state,connection in ((None,None,'latest','connected'),(None,URLError('Offline'),'error','failed'),(self.asset(),None,'error','connected')):
    updater=AutoUpdater(tmp)
    with self.subTest(state=state,connection=connection),patch('rio_monitor.updater.latest_asset',return_value=result,side_effect=error),patch('rio_monitor.updater.download_asset',side_effect=ValueError('Incomplete')):
     updater.check();updater.worker.join(3)
     self.assertFalse(updater.worker.is_alive());self.assertEqual(updater.snapshot()['state'],state)
     self.assertEqual(updater.snapshot()['connection'],connection);self.assertIsNone(updater.pending)
 @unittest.skipUnless(os.name=='nt','Windows update handoff')
 def test_windows_handoff_waits_for_exit_then_replaces_and_restarts_the_program(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'更新 test';root.mkdir();target=root/'RIO.exe';target.write_bytes(b'old program')
   staged=root/'new.exe';source=root/'restart.cs'
   source.write_text('using System; using System.IO; class Restart { static void Main(string[] args) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"restarted.txt"),string.Join(" ",args)+"|"+Environment.GetEnvironmentVariable("PYINSTALLER_RESET_ENVIRONMENT")); } }',encoding='utf-8')
   compiler=Path(os.environ['SYSTEMROOT'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
   subprocess.run([str(compiler),'/nologo','/target:winexe','/out:'+str(staged),str(source)],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
   content=staged.read_bytes()
   powershell=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
   child=subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-Command','Start-Sleep -Milliseconds 1200'],creationflags=subprocess.CREATE_NO_WINDOW)
   helper=None
   try:
    helper=launch_install(staged,target,root/'updates','rc0.1.2',[child.pid])
    self.assertEqual(target.read_bytes(),b'old program');child.wait(5);self.assertEqual(helper.wait(10),0)
    self.assertEqual(target.read_bytes(),content);self.assertFalse(staged.exists())
    self.assertEqual(json.loads((root/'updates/status.json').read_text(encoding='utf-8-sig'))['status'],'installed')
    receipt=root/'restarted.txt';deadline=time.monotonic()+5
    while not receipt.exists() and time.monotonic()<deadline:time.sleep(.05)
    self.assertEqual(receipt.read_text(),'--show-settings|1')
   finally:
    if child.poll() is None:child.terminate();child.wait(5)
    if helper and helper.poll() is None:helper.terminate();helper.wait(5)

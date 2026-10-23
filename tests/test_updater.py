import hashlib,io,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
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
 @unittest.skipUnless(os.name=='nt','Windows update handoff')
 def test_windows_handoff_waits_for_exit_then_replaces_only_the_program(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'更新 test';root.mkdir();target=root/'RIO.exe';target.write_bytes(b'old program')
   staged=root/'new.exe';staged.write_bytes(b'new program')
   powershell=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
   child=subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-Command','Start-Sleep -Milliseconds 1200'],creationflags=subprocess.CREATE_NO_WINDOW)
   helper=None
   try:
    helper=launch_install(staged,target,root/'updates','rc0.1.2',[child.pid])
    self.assertEqual(target.read_bytes(),b'old program');child.wait(5);self.assertEqual(helper.wait(10),0)
    self.assertEqual(target.read_bytes(),b'new program');self.assertFalse(staged.exists())
    self.assertEqual(json.loads((root/'updates/status.json').read_text(encoding='utf-8-sig'))['status'],'installed')
   finally:
    if child.poll() is None:child.terminate();child.wait(5)
    if helper and helper.poll() is None:helper.terminate();helper.wait(5)

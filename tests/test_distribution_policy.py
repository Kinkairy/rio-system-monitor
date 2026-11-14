"""Distribution-only download restrictions preserve the default host behavior."""
import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import Mock,patch
from rio_monitor.extensions import ModuleStore,Extension

class DistributionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest=dict(version='rc0.1.20',api=2,modules=['fangcun','blackshark'],disabled_downloads=['fangcun'])
    def store(self,name='fangcun',manifest=None):
        return ModuleStore(name,self.root,self.manifest if manifest is None else manifest,self.root)
    def ext(self,store):
        return Extension(store,is_on=lambda:True,load=Mock(),set_on=Mock(),open_window=Mock())
    def test_packaging_default_unchanged_and_local_flag_is_explicit(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from package_modules import package
        with tempfile.TemporaryDirectory() as d:
            original=package(d,'rc0.1.20')
            self.assertNotIn('disabled_downloads',original)
            restricted=package(d,'rc0.1.20',disable_fangcun_download=True)
            self.assertEqual(restricted.pop('disabled_downloads'),['fangcun'])
            self.assertEqual(restricted,original)
    def test_backend_refuses_even_explicit_entry_without_network_or_disk(self):
        store=self.store()
        with patch('rio_monitor.extensions.download_asset') as download:
            with self.assertRaises(PermissionError):store.install(entry={'sha256':'a'*64})
            with self.assertRaises(PermissionError):store._install({},None,None)
            download.assert_not_called()
        self.assertFalse(store.root.exists())
    def test_start_toggle_direct_download_offer_and_upgrade_never_download(self):
        store=self.store();ext=self.ext(store)
        with patch.object(store,'refresh') as refresh,patch.object(store,'install') as install,patch('rio_monitor.extensions.download_asset') as download:
            ext.start();ext.setEnabled(True);ext.download();ext.offer({'schema':1,'modules':{}})
            store.listed=[dict(sha256='a'*64,version='rc0.2')];ext._update='available';ext.upgrade()
            self.assertIsNone(ext.worker);self.assertIsNone(ext.checker)
            self.assertFalse(ext.allow_download);self.assertFalse(ext.updatable)
            refresh.assert_not_called();install.assert_not_called();download.assert_not_called()
    def test_public_default_and_blackshark_still_download(self):
        public={k:v for k,v in self.manifest.items() if k!='disabled_downloads'}
        for store in [self.store(manifest=public),self.store('blackshark')]:
            ext=self.ext(store)
            with patch.object(store,'refresh'),patch.object(store,'install') as install:
                ext.start();ext.worker.join(2)
                self.assertTrue(ext.allow_download);install.assert_called_once()
    def test_already_installed_fangcun_loads_without_update_or_data_change(self):
        store=self.store();entry=dict(version='rc0.4.3.12',sha256='b'*64,api=2)
        folder=store.root/('b'*16)/store.package;folder.mkdir(parents=True)
        (folder/'__init__.py').write_text('')
        state=store.root/'active.json';state.write_text(json.dumps(dict(active=entry)))
        before=state.read_bytes();ext=self.ext(store)
        with patch.object(store,'install') as install:
            ext.start();ext.load.assert_called_once();install.assert_not_called()
            self.assertEqual(ext.state,'ready');self.assertFalse(ext.updatable)
        self.assertEqual(state.read_bytes(),before)

if __name__=='__main__':unittest.main()

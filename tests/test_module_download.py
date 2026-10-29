"""Module packages: reproducible packing, a host-only EXE, verified install from the index and the card state machine."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
import hashlib, io, json, sys, tempfile, threading, time, unittest, zipfile
from PySide6.QtWidgets import QApplication
from rio_monitor import extensions
from rio_monitor.extensions import Extension, ModuleStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import package_modules

# Module sources live only in the private repository; the public tree tests the host side alone.
MODULE_SOURCES = all((ROOT/'src'/spec['package']).is_dir() for spec in package_modules.MODULES.values())


def runtime(folder):
    folder = Path(folder)/'runtime-assets'
    (folder/'fangcun').mkdir(parents=True); (folder/'fangcun/runtime.mjs').write_text('export {}')
    (folder/'fangcun-ui').mkdir(); (folder/'fangcun-ui/inventory-v1.png').write_bytes(b'png')
    (folder/'fangcun-ui/inventory.provenance.json').write_text('{}')
    for name in ('fangcun-gourd.png','fangcun-gourd-v2.png','fangcun-gourd-v4.png'): (folder/name).write_bytes(name.encode())
    (folder/'fangcun-gourd-v4.provenance.json').write_text('{}'); (folder/'rio-icon.ico').write_bytes(b'ico')
    rows = [{'path': p.relative_to(folder).as_posix()} for p in folder.rglob('*') if p.is_file()]
    (folder/'private-manifest.json').write_text(json.dumps({'files': rows}))
    return folder


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); self.tmp = Path(folder.name)

    def release(self):
        """Both modules released to a simulated 'modules' prerelease; returns the index and the EXE's manifest."""
        index = None
        for name in package_modules.MODULES:
            data = package_modules.release(ROOT/'src', runtime(self.tmp/name), self.tmp/'dist', name, package_modules.module_version(ROOT/'src', name), index=index)
            index = self.tmp/'dist/RIO-Modules.json'
        url = patch.object(extensions, 'RELEASE_URL', (self.tmp/'dist').as_uri() + '/{asset}'); url.start(); self.addCleanup(url.stop)
        return data, {'version': 'rc9.9.9', 'api': extensions.MODULE_API, 'modules': list(package_modules.MODULES)}


@unittest.skipUnless(MODULE_SOURCES, 'Module sources are private')
class PackageTests(TemporaryTest):
    def test_packages_are_reproducible_and_carry_only_merged_runtime_resources(self):
        folder = runtime(self.tmp)
        raw = package_modules.build(ROOT/'src', folder, 'fangcun', 'rc0.1')
        self.assertEqual(raw, package_modules.build(ROOT/'src', runtime(self.tmp/'again'), 'fangcun', 'rc0.1'))
        self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(raw)).read('module.json')), dict(name='fangcun', package='rio_fangcun', version='rc0.1', api=extensions.MODULE_API))
        names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
        self.assertTrue({'module.json','rio_fangcun/module.py','rio_fangcun/ui/FangcunWindow.qml'} <= set(names))
        self.assertTrue({'assets/fangcun/runtime.mjs','assets/fangcun-ui/inventory-v1.png','assets/fangcun-gourd-v4.png'} <= set(names))
        self.assertFalse([n for n in names if n.endswith('.provenance.json') or 'fangcun-gourd.png' in n or '-v2.png' in n or '__pycache__' in n])
        shark = zipfile.ZipFile(io.BytesIO(package_modules.build(ROOT/'src', folder, 'blackshark', 'rc0.1'))).namelist()
        self.assertIn('rio_blackshark/ui/BlackSharkWindow.qml', shark); self.assertFalse([n for n in shark if n.startswith('assets/')])

    def test_the_exe_keeps_host_resources_and_lists_its_modules_without_packages(self):
        folder = runtime(self.tmp)
        manifest = package_modules.package(folder, 'rc9.9.9')
        self.assertEqual(manifest, {'version': 'rc9.9.9', 'api': extensions.MODULE_API, 'modules': ['fangcun', 'blackshark']})
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['modules.json','private-manifest.json','rio-icon.ico'])
        self.assertEqual(json.loads((folder/'private-manifest.json').read_text())['files'], [{'path':'rio-icon.ico'}])
        self.assertEqual(json.loads((folder/'modules.json').read_text()), manifest)
        self.assertFalse((self.tmp/'dist').exists())  # No module package is built with the program.

    def test_install_verifies_extracts_and_replaces_older_versions(self):
        index, manifest = self.release()
        store = ModuleStore('fangcun', self.tmp/'modules', manifest, self.tmp/'host')
        self.assertIsNone(store.location())
        entry = store.refresh(index)
        old = self.tmp/'modules/fangcun/0000000000000000'; old.mkdir(parents=True)
        seen = []
        store.install(progress=lambda done,total: seen.append((done,total)))
        target = self.tmp/'modules/fangcun'/entry['sha256'][:16]
        self.addCleanup(lambda: str(target) in sys.path and sys.path.remove(str(target)))
        self.assertEqual(store.location(), target/'assets'); self.assertIn(str(target), sys.path)
        self.assertTrue((target/'assets/fangcun/runtime.mjs').is_file()); self.assertFalse(old.exists())
        self.assertEqual(seen[-1], (entry['size'],)*2)
        self.assertFalse(list((self.tmp/'modules/fangcun/downloads').iterdir()))

    def test_damaged_packages_are_never_installed(self):
        index, manifest = self.release()
        store = ModuleStore('blackshark', self.tmp/'modules', manifest, self.tmp/'host')
        entry = store.refresh(index)
        (self.tmp/'dist'/entry['asset']).write_bytes(b'x'*entry['size'])
        with self.assertRaisesRegex(ValueError, 'damaged'): store.install()
        self.assertIsNone(store.location())


class StoreTests(TemporaryTest):
    def test_unexpected_package_paths_are_never_extracted(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive: archive.writestr('../outside.py','')
        raw = data.getvalue(); (self.tmp/'evil.zip').write_bytes(raw)
        url = patch.object(extensions, 'RELEASE_URL', self.tmp.as_uri() + '/{asset}'); url.start(); self.addCleanup(url.stop)
        store = ModuleStore('blackshark', self.tmp/'modules', {'modules': ['blackshark']}, self.tmp/'host')
        evil = dict(asset='evil.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), version='rc0.1', api=extensions.MODULE_API, release='modules')
        with self.assertRaisesRegex(ValueError, 'Unexpected'): store.install(entry=evil)
        self.assertFalse((self.tmp/'modules/outside.py').exists())
        self.assertIsNone(store.location())
        with self.assertRaisesRegex(LookupError, 'listed'): store.install()  # Nothing listed, nothing to install.

    @unittest.skipUnless(MODULE_SOURCES, 'Module sources are private')
    def test_source_runs_use_src_modules_without_downloading(self):
        self.assertEqual(ModuleStore('fangcun', self.tmp, None, self.tmp/'host').location(), self.tmp/'host')


class Store:
    def __init__(self, packaged=True, ready=False):
        self.name, self.package, self.packaged = 'demo', 'rio_store_demo', packaged
        self.entry={'size':58_000_000}; self.ready=ready
        self.gate=threading.Event(); self.fail=False; self.installs=0; self.refreshes=0
    def location(self): return Path('module-assets') if self.ready else None
    def current(self): return None
    def refresh(self): self.refreshes+=1; return self.entry
    def reject(self): return False
    def install(self, stop, progress):
        self.installs+=1; progress(29,58)
        while not self.gate.wait(.01):
            if stop.is_set(): raise InterruptedError('cancelled')
        if self.fail: raise ValueError('Incomplete or damaged update')
        self.ready=True


def card(store, on=False, **kw):
    calls=[]; state={'on':on}
    def set_on(value): calls.append(('set_on',value)); state['on']=value
    ext=Extension(store, is_on=lambda:state['on'], load=lambda assets: calls.append(('load',assets)), set_on=set_on,
                  open_window=lambda: calls.append(('open',)), **kw)
    return ext, calls, state


def finish(ext):
    for _ in range(200):
        ext.poll()
        if ext.state!='downloading': return
        time.sleep(.01)
    raise AssertionError('download did not finish')


class ExtensionStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_switching_on_downloads_then_loads_and_enables(self):
        store=Store(); ext,calls,_=card(store)
        self.assertEqual((ext.state,ext.enabled,ext.downloadSize), ('missing',False,'58 MB'))
        ext.open(); self.assertEqual(calls, [])
        ext.setEnabled(True); ext.poll()
        self.assertEqual((ext.state,ext.enabled,ext.progress), ('downloading',True,.5))
        store.gate.set(); finish(ext)
        self.assertEqual(ext.state, 'ready'); self.assertTrue(ext.enabled)
        self.assertEqual(calls, [('load',Path('module-assets')),('set_on',True)])
        ext.open(); ext.setEnabled(False)
        self.assertEqual(calls[-2:], [('open',),('set_on',False)]); self.assertFalse(ext.enabled); self.assertEqual((store.installs, store.refreshes), (1, 1))

    def test_switching_off_cancels_and_failure_can_be_retried(self):
        store=Store(); ext,calls,_=card(store)
        ext.setEnabled(True); ext.setEnabled(False); finish(ext)
        self.assertEqual((ext.state,calls), ('missing',[]))
        store.fail=True; store.gate.set(); ext.setEnabled(True); finish(ext)
        self.assertEqual((ext.state,ext.enabled,calls), ('error',False,[]))
        store.fail=False; ext.setEnabled(True); finish(ext)
        self.assertEqual(ext.state, 'ready'); self.assertEqual(calls, [('load',Path('module-assets')),('set_on',True)])

    def test_launch_loads_installed_modules_and_fetches_enabled_missing_ones(self):
        installed,calls,_=card(Store(ready=True)); installed.start()
        self.assertEqual((installed.state,calls), ('ready',[('load',Path('module-assets'))]))
        store=Store(); store.gate.set(); upgraded,calls,_=card(store,on=True); upgraded.start()
        self.assertEqual(upgraded.state, 'downloading'); finish(upgraded)
        self.assertEqual(calls, [('load',Path('module-assets')),('set_on',True)])
        idle,_,_=card(Store()); idle.start(); self.assertEqual(idle.state, 'missing')
        small=Store(); small.entry={'size':45_291}; self.assertEqual(card(small)[0].downloadSize, '45 KB')

    def test_capture_and_source_builds_never_download(self):
        offline,_,_=card(Store(),on=True,allow_download=False); offline.start(); self.assertEqual(offline.state, 'missing')
        offline.setEnabled(True); self.assertEqual(offline.state, 'error'); self.assertIsNone(offline.worker)
        source,_,_=card(Store(packaged=False)); source.setEnabled(True); self.assertEqual(source.state, 'error')

    def test_shutdown_stops_a_running_download(self):
        store=Store(); ext,_,_=card(store); ext.setEnabled(True)
        self.assertTrue(ext.close()); self.assertIsNotNone(ext.worker); self.assertFalse(ext.worker.is_alive())


if __name__ == '__main__':
    unittest.main()

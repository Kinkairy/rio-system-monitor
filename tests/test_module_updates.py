"""Module-only updates: index checks, host compatibility, install beside the package in use, and falling back."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
import hashlib, importlib, io, json, sys, tempfile, unittest, zipfile
from PySide6.QtWidgets import QApplication
from rio_monitor import extensions
from rio_monitor.extensions import MODULE_API, Extension, ModuleStore, listed_updates, update_modules

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import package_modules

PACKAGE = 'rio_update_demo'  # A stand-in module, so the public tree tests the host side without module sources.
MODULE_SOURCES = all((ROOT/'src'/spec['package']).is_dir() for spec in package_modules.MODULES.values())
SHA = 'a'*64


def module_zip(version, marker=None, api=MODULE_API, broken=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('module.json', json.dumps(dict(name='demo', package=PACKAGE, version=version, api=api)))
        archive.writestr(PACKAGE + '/__init__.py', 'raise ImportError("broken update")' if broken else f'MARKER = {marker or version!r}')
        archive.writestr('assets/demo.txt', version)
    return data.getvalue()


def row(version, raw=b'x', **changes):
    return dict(dict(version=version, api=MODULE_API, asset=f'RIO-Module-Demo-{version}.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), **changes)


class IndexTests(unittest.TestCase):
    def test_only_well_formed_rows_for_this_host_interface_are_listed(self):
        good = row('rc9.9.9.1')
        rows = [good, row('rc9.9.9.2', api=MODULE_API + 1), row('rc9.9.9.3', sha256='A'*64), row('rc9.9.9.4', asset='../RIO-Module-Demo.zip'),
                row('rc9.9.9.5', asset='https://example.com/RIO-Module-Demo-1.zip'), row('rc9.9.9.6', size='1'), row('rc9.9.9.7', size=0),
                row('modules'), {'version': 'rc9.9.9.8'}, 'not a row', None]
        listed = listed_updates({'schema': 1, 'modules': {'demo': rows, 'other': [row('rc9.9.9.9')]}}, 'demo')
        self.assertEqual(listed, [dict(good, release='modules')])
        for index in ({'schema': 2, 'modules': {'demo': [good]}}, {'schema': 1, 'modules': {'demo': good}}, {'schema': 1, 'modules': []}, [], None):
            with self.subTest(index=index): self.assertEqual(listed_updates(index, 'demo'), [])


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); self.tmp = Path(folder.name)
        packages = patch.dict(extensions.PACKAGES, demo=PACKAGE); packages.start(); self.addCleanup(packages.stop)
        url = patch.object(extensions, 'RELEASE_URL', (self.tmp/'release').as_uri() + '/{version}/{asset}'); url.start(); self.addCleanup(url.stop)
        self.addCleanup(self.restart)
        raw = module_zip('rc9.9.9', 'pinned'); self.publish('rc9.9.9', 'RIO-Module-Demo.zip', raw)
        # What the EXE carries; it stays the same through every module-only update below.
        self.manifest = {'version': 'rc9.9.9', 'modules': {'demo': dict(asset='RIO-Module-Demo.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), api=MODULE_API)}}
        self.manifest_text = json.dumps(self.manifest)
        self.rows = []

    def publish(self, release, asset, raw):
        path = self.tmp/'release'/release/asset; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)

    def release_update(self, version, raw, listed=True, **changes):
        """Upload a module-only update to the simulated 'modules' prerelease and list it in its index."""
        entry = row(version, raw, **changes)
        self.publish('modules', entry['asset'], raw)
        if listed: self.rows.append(entry)
        self.publish('modules', 'RIO-Modules.json', json.dumps({'schema': 1, 'modules': {'demo': self.rows}}).encode())
        return entry

    def withdraw(self, version):
        self.rows = [r for r in self.rows if r['version'] != version]
        self.publish('modules', 'RIO-Modules.json', json.dumps({'schema': 1, 'modules': {'demo': self.rows}}).encode())

    def restart(self):
        """What a new process starts with: nothing imported from earlier package folders."""
        sys.path[:] = [p for p in sys.path if not p.startswith(str(self.tmp))]
        for name in [m for m in sys.modules if m == PACKAGE or m.startswith(PACKAGE + '.')]: del sys.modules[name]

    def launch(self):
        """A host start: the unchanged EXE manifest, an enabled module, loaded if installed or fetched if not."""
        self.restart(); self.assertEqual(json.dumps(self.manifest), self.manifest_text)
        self.loaded = []
        def load(assets): self.loaded.append((importlib.import_module(PACKAGE).MARKER, (assets/'demo.txt').read_text()))
        ext = Extension(ModuleStore('demo', self.tmp/'modules', self.manifest, self.tmp/'host'), is_on=lambda: True, load=load,
                        set_on=lambda value: None, open_window=lambda: None)
        ext.start()
        if ext.state == 'downloading':
            ext.worker.join(5); ext.poll()
        return ext

    def check(self, ext):
        return update_modules({'demo': ext})

    def record(self): return json.loads((self.tmp/'modules/demo/active.json').read_text())

    def folders(self): return sorted(p.name for p in (self.tmp/'modules/demo').iterdir() if p.is_dir() and p.name != 'downloads')

    def test_only_the_module_updates_and_falls_back_while_the_program_stays_the_same(self):
        ext = self.launch()
        self.assertEqual((ext.state, self.loaded), ('ready', [('pinned', 'rc9.9.9')]))
        self.assertFalse(self.check(ext))  # No index published yet: nothing changes.
        # A module-only update: listed, downloaded beside the loaded package, used after the restart.
        first = self.release_update('rc9.9.9.1', module_zip('rc9.9.9.1'))
        self.assertTrue(self.check(ext)); self.assertEqual(self.loaded, [('pinned', 'rc9.9.9')])
        self.assertEqual(self.record()['active']['version'], 'rc9.9.9.1'); self.assertEqual(len(self.folders()), 2)
        self.assertFalse(self.check(ext))  # Already installed.
        ext = self.launch(); self.assertEqual(self.loaded, [('rc9.9.9.1', 'rc9.9.9.1')])
        # A broken update is dropped at load for the package before it and never picked again.
        broken = self.release_update('rc9.9.9.2', module_zip('rc9.9.9.2', broken=True))
        self.assertTrue(self.check(ext))
        ext = self.launch()
        self.assertEqual((ext.state, self.loaded), ('ready', [('rc9.9.9.1', 'rc9.9.9.1')]))
        self.assertEqual((self.record()['active']['sha256'], self.record()['bad']), (first['sha256'], [broken['sha256']]))
        self.assertFalse(self.check(ext)); self.assertEqual(self.launch().state, 'ready'); self.assertEqual(self.loaded, [('rc9.9.9.1', 'rc9.9.9.1')])
        # Withdrawing the listed updates returns hosts to the package their EXE pins.
        self.withdraw('rc9.9.9.1'); self.withdraw('rc9.9.9.2')
        self.assertTrue(self.check(self.launch()))
        self.launch(); self.assertEqual(self.loaded, [('pinned', 'rc9.9.9')])
        self.assertEqual(self.record()['active']['sha256'], self.manifest['modules']['demo']['sha256'])

    def test_failed_or_mismatched_updates_keep_the_package_in_use(self):
        ext = self.launch(); pinned = self.record()['active']
        raw = module_zip('rc9.9.9.1')
        cases = [dict(sha256='0'*64),                                     # Damaged or replaced file.
                 dict(version='rc9.9.9.3'),                               # Package names another version.
                 dict(name='api', raw=module_zip('rc9.9.9.1', api=MODULE_API + 1))]  # Built for another host interface.
        for changes in cases:
            with self.subTest(changes=changes):
                self.rows = []
                package = changes.pop('raw', raw); changes.pop('name', None)
                entry = row(changes.pop('version', 'rc9.9.9.1'), package, **changes)
                self.publish('modules', entry['asset'], package)
                self.rows.append(entry)
                self.publish('modules', 'RIO-Modules.json', json.dumps({'schema': 1, 'modules': {'demo': self.rows}}).encode())
                self.assertFalse(self.check(ext)); self.assertEqual(self.record()['active'], pinned)
        self.rows = []; self.release_update('rc9.9.9.4', module_zip('rc9.9.9.4', api=MODULE_API + 1), api=MODULE_API + 1)
        self.release_update('rc9.9.8.9', module_zip('rc9.9.8.9'))  # Older than the program's own package.
        self.assertFalse(self.check(ext)); self.assertEqual(self.record()['active'], pinned)
        self.launch(); self.assertEqual(self.loaded, [('pinned', 'rc9.9.9')])

    def test_first_switch_on_installs_the_newest_listed_package(self):
        ext = Extension(ModuleStore('demo', self.tmp/'modules', self.manifest, self.tmp/'host'), is_on=lambda: False,
                        load=lambda assets: None, set_on=lambda value: None, open_window=lambda: None)
        raw = module_zip('rc9.9.9.1'); self.release_update('rc9.9.9.1', raw)
        self.assertFalse(self.check(ext)); self.assertEqual(ext.state, 'missing'); self.assertFalse((self.tmp/'modules').exists())
        self.assertEqual(ext.store.entry['version'], 'rc9.9.9.1')
        ext.setEnabled(True); ext.worker.join(5); ext.poll()
        self.assertEqual((ext.state, self.record()['active']['version']), ('ready', 'rc9.9.9.1'))

    def test_a_newer_program_supersedes_earlier_module_updates(self):
        self.launch(); self.release_update('rc9.9.9.1', module_zip('rc9.9.9.1')); self.check(self.launch())
        raw = module_zip('rc9.9.10', 'next program'); self.publish('rc9.9.10', 'RIO-Module-Demo.zip', raw)
        self.manifest = {'version': 'rc9.9.10', 'modules': {'demo': dict(asset='RIO-Module-Demo.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), api=MODULE_API)}}
        self.manifest_text = json.dumps(self.manifest)
        ext = self.launch()
        self.assertEqual((ext.state, self.loaded), ('ready', [('next program', 'rc9.9.10')]))
        self.assertFalse(self.check(ext))  # rc9.9.9.1 is still listed but older than this program's package.

    def test_unreachable_or_invalid_index_changes_nothing(self):
        ext = self.launch(); pinned = self.record()
        self.publish('modules', 'RIO-Modules.json', b'{not json')
        self.assertFalse(self.check(ext)); self.assertEqual(self.record(), pinned)
        with patch.object(extensions, 'fetch_index', side_effect=OSError('offline')):
            self.assertFalse(self.check(ext))
        self.assertEqual(self.record(), pinned)


@unittest.skipUnless(MODULE_SOURCES, 'Module sources are private')
class ReleaseToolTests(unittest.TestCase):
    def test_module_release_packs_one_module_and_extends_the_published_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); runtime = tmp/'runtime'; runtime.mkdir()
            published = tmp/'published.json'
            published.write_text(json.dumps({'schema': 1, 'modules': {'fangcun': [row('rc9.9.9.1')], 'blackshark': [row('rc9.9.9.1')]}}))
            index = package_modules.release(ROOT/'src', runtime, tmp/'dist', 'blackshark', 'rc9.9.9.2', index=published)
            raw = (tmp/'dist/RIO-Module-BlackShark-rc9.9.9.2.zip').read_bytes()
            self.assertEqual(index['modules']['fangcun'], [row('rc9.9.9.1')])
            self.assertEqual(index['modules']['blackshark'][-1], dict(version='rc9.9.9.2', api=MODULE_API, asset='RIO-Module-BlackShark-rc9.9.9.2.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            self.assertEqual(json.loads((tmp/'dist/RIO-Modules.json').read_text()), index)
            self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(raw)).read('module.json')), dict(name='blackshark', package='rio_blackshark', version='rc9.9.9.2', api=MODULE_API))
            self.assertEqual([e['version'] for e in listed_updates(index, 'blackshark')], ['rc9.9.9.1', 'rc9.9.9.2'])
            self.assertEqual(list(runtime.iterdir()), [])  # No EXE input is produced or changed.
            again = package_modules.release(ROOT/'src', runtime, tmp/'again', 'blackshark', 'rc9.9.9.2', index=tmp/'dist/RIO-Modules.json')
            self.assertEqual(again, index)  # Reproducible, and re-releasing a version replaces its row.
            with self.assertRaisesRegex(ValueError, 'numbered'):
                package_modules.release(ROOT/'src', runtime, tmp/'dist', 'blackshark', 'rc9.9.9')


if __name__ == '__main__':
    unittest.main()

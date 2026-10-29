"""Module packages: index checks, host compatibility, install beside the package in use, falling back, and the card's own check."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
import hashlib, importlib, io, json, sys, tempfile, time, unittest, zipfile
from PySide6.QtWidgets import QApplication
from rio_monitor import extensions
from rio_monitor.extensions import MODULE_API, Extension, ModuleStore, listed_updates, update_modules

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import package_modules

PACKAGE = 'rio_update_demo'  # A stand-in module, so the public tree tests the host side without module sources.
MODULE_SOURCES = all((ROOT/'src'/spec['package']).is_dir() for spec in package_modules.MODULES.values())


def module_zip(version, marker=None, api=MODULE_API, broken=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('module.json', json.dumps(dict(name='demo', package=PACKAGE, version=version, api=api)))
        archive.writestr(PACKAGE + '/__init__.py', 'raise ImportError("broken update")' if broken else f'MARKER = {marker or version!r}')
        archive.writestr('assets/demo.txt', version)
    return data.getvalue()


def row(version, raw=b'x', **changes):
    return dict(dict(version=version, api=MODULE_API, asset=f'RIO-Module-Demo-{version}.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), **changes)


def settle(ext):
    """Poll as the GUI does until the card's download and update workers are done."""
    for _ in range(500):
        ext.poll()
        if ext.checker is None and ext.state != 'downloading': return
        time.sleep(.01)
    raise AssertionError('module worker did not finish')


class IndexTests(unittest.TestCase):
    def test_only_well_formed_rows_for_this_host_interface_are_listed(self):
        good = row('rc0.1')
        rows = [good, row('rc0.2', api=MODULE_API - 1), row('rc0.3', api=MODULE_API + 1), row('rc0.4', sha256='A'*64),
                row('rc0.5', asset='../RIO-Module-Demo.zip'), row('rc0.6', asset='https://example.com/RIO-Module-Demo-1.zip'),
                row('rc0.7', size='1'), row('rc0.8', size=0), row('modules'), {'version': 'rc0.9'}, 'not a row', None]
        listed = listed_updates({'schema': 1, 'modules': {'demo': rows, 'other': [row('rc1.0')]}}, 'demo')
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
        # What the EXE carries: the modules it hosts, never a package; it stays the same through every module release.
        self.manifest = {'version': 'rc9.9.9', 'api': MODULE_API, 'modules': ['demo']}
        self.rows, self.restarts = [], []

    def publish(self, asset, raw):
        path = self.tmp/'release/modules'/asset; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)

    def release(self, version, raw, listed=True, **changes):
        """Upload a module package to the simulated 'modules' prerelease and list it in its index."""
        entry = row(version, raw, **changes)
        self.publish(entry['asset'], raw)
        if listed: self.rows.append(entry)
        self.publish('RIO-Modules.json', json.dumps({'schema': 1, 'modules': {'demo': self.rows}}).encode())
        return entry

    def withdraw(self, version):
        self.rows = [r for r in self.rows if r['version'] != version]
        self.publish('RIO-Modules.json', json.dumps({'schema': 1, 'modules': {'demo': self.rows}}).encode())

    def restart(self):
        """What a new process starts with: nothing imported from earlier package folders."""
        sys.path[:] = [p for p in sys.path if not p.startswith(str(self.tmp))]
        for name in [m for m in sys.modules if m == PACKAGE or m.startswith(PACKAGE + '.')]: del sys.modules[name]

    def launch(self, on=True):
        """A host start: the unchanged EXE manifest and the module, loaded if installed or fetched if enabled."""
        self.restart()
        self.loaded = []
        def load(assets): self.loaded.append((importlib.import_module(PACKAGE).MARKER, (assets/'demo.txt').read_text()))
        ext = Extension(ModuleStore('demo', self.tmp/'modules', self.manifest, self.tmp/'host'), is_on=lambda: on, load=load,
                        set_on=lambda value: None, open_window=lambda: None, installed=lambda: self.restarts.append(True))
        ext.start(); settle(ext)
        return ext

    def check(self, ext):
        return update_modules({'demo': ext})

    def record(self): return json.loads((self.tmp/'modules/demo/active.json').read_text())

    def folders(self): return sorted(p.name for p in (self.tmp/'modules/demo').iterdir() if p.is_dir() and p.name != 'downloads')

    def test_first_switch_on_installs_the_newest_listed_package(self):
        ext = self.launch(on=False)
        self.assertEqual((ext.state, ext.version, ext.downloadSize, ext.updatable), ('missing', '', '', False))
        ext.setEnabled(True); settle(ext)  # Nothing listed yet.
        self.assertEqual(ext.state, 'error'); self.assertFalse((self.tmp/'modules/demo/active.json').exists())
        self.release('rc0.1', module_zip('rc0.1')); newest = module_zip('rc0.2'); self.release('rc0.2', newest)
        self.assertFalse(self.check(ext)); self.assertEqual((ext.version, ext.downloadSize), ('rc0.2', f'{max(1, round(len(newest)/1000))} KB'))
        ext.setEnabled(True); settle(ext)
        self.assertEqual((ext.state, ext.version, ext.updatable), ('ready', 'rc0.2', True))
        self.assertEqual((self.loaded, self.record()['active']['version']), ([('rc0.2', 'rc0.2')], 'rc0.2'))

    def test_updates_install_beside_the_package_in_use_and_fall_back(self):
        self.release('rc0.1', module_zip('rc0.1'))
        ext = self.launch()
        self.assertEqual((ext.state, ext.version, self.loaded), ('ready', 'rc0.1', [('rc0.1', 'rc0.1')]))
        self.assertFalse(self.check(ext))  # Already installed.
        # An update: listed, downloaded beside the loaded package, used after the restart.
        second = self.release('rc0.2', module_zip('rc0.2'))
        self.assertTrue(self.check(ext)); self.assertEqual((self.loaded, ext.version), ([('rc0.1', 'rc0.1')], 'rc0.1'))
        settle(ext); self.assertEqual((ext.updateState, ext.newVersion), ('installed', 'rc0.2'))  # The card says a restart loads it.
        self.assertEqual(self.record()['active']['version'], 'rc0.2'); self.assertEqual(len(self.folders()), 2)
        ext = self.launch(); self.assertEqual((self.loaded, ext.version), ([('rc0.2', 'rc0.2')], 'rc0.2'))
        # A broken update is dropped at load for the package before it and never picked again.
        broken = self.release('rc0.3', module_zip('rc0.3', broken=True))
        self.assertTrue(self.check(ext))
        ext = self.launch()
        self.assertEqual((ext.state, ext.version, self.loaded), ('ready', 'rc0.2', [('rc0.2', 'rc0.2')]))
        self.assertEqual((self.record()['active']['sha256'], self.record()['bad']), (second['sha256'], [broken['sha256']]))
        self.assertFalse(self.check(ext)); self.assertEqual(self.launch().state, 'ready'); self.assertEqual(self.loaded, [('rc0.2', 'rc0.2')])
        # Withdrawing listed packages returns hosts to the newest one still listed.
        self.withdraw('rc0.2'); self.withdraw('rc0.3')
        self.assertTrue(self.check(self.launch()))
        self.launch(); self.assertEqual(self.loaded, [('rc0.1', 'rc0.1')])

    def test_a_broken_first_package_is_never_picked_again(self):
        self.release('rc0.1', module_zip('rc0.1')); self.release('rc0.2', module_zip('rc0.2', broken=True))
        ext = self.launch()
        self.assertEqual((ext.state, self.loaded), ('error', []))
        ext.setEnabled(True); settle(ext)  # Switching on again takes the newest package that never failed here.
        self.assertEqual((ext.state, ext.version, self.loaded), ('ready', 'rc0.1', [('rc0.1', 'rc0.1')]))

    def test_failed_or_mismatched_updates_keep_the_package_in_use(self):
        self.release('rc0.1', module_zip('rc0.1')); ext = self.launch(); first = self.rows[0]
        raw = module_zip('rc0.2')
        cases = [dict(sha256='0'*64),                                     # Damaged or replaced file.
                 dict(version='rc0.3'),                                   # Package names another version.
                 dict(raw=module_zip('rc0.2', api=MODULE_API + 1))]       # Built for another host interface.
        for changes in cases:
            with self.subTest(changes=changes):
                self.rows = [first]
                package = changes.pop('raw', raw)
                self.release(changes.pop('version', 'rc0.2'), package, **changes)
                self.assertFalse(self.check(ext)); self.assertEqual(self.record()['active'], dict(first, release='modules'))
        self.rows = [first]; self.release('rc0.4', module_zip('rc0.4', api=MODULE_API + 1), api=MODULE_API + 1)
        self.release('rc0.0.9', module_zip('rc0.0.9'))  # Older than the package in use, which is still listed.
        self.assertFalse(self.check(ext)); self.assertEqual(self.record()['active'], dict(first, release='modules'))
        self.launch(); self.assertEqual(self.loaded, [('rc0.1', 'rc0.1')])

    def test_packages_installed_for_the_earlier_interface_are_replaced(self):
        # An earlier program left its package, numbered after the program and built for interface 1.
        old = self.tmp/'modules/demo'/('b'*16)/PACKAGE; old.mkdir(parents=True); (old/'__init__.py').write_text('MARKER = "old"')
        (self.tmp/'modules/demo/active.json').write_text(json.dumps(dict(active=dict(row('rc0.1.17.3', b'old', api=1), sha256='b'*64), previous=None, bad=[])))
        self.release('rc0.1', module_zip('rc0.1'))
        ext = self.launch()
        self.assertEqual((ext.state, ext.version, self.loaded), ('ready', 'rc0.1', [('rc0.1', 'rc0.1')]))
        self.assertEqual((self.folders(), self.record()['previous']), ([self.rows[0]['sha256'][:16]], None))

    def test_unreachable_or_invalid_index_changes_nothing(self):
        self.release('rc0.1', module_zip('rc0.1')); ext = self.launch(); installed = self.record()
        self.publish('RIO-Modules.json', b'{not json')
        self.assertFalse(self.check(ext)); self.assertEqual(self.record(), installed)
        with patch.object(extensions, 'fetch_index', side_effect=OSError('offline')):
            self.assertFalse(self.check(ext))
        self.assertEqual(self.record(), installed)

    def test_the_card_checks_and_upgrades_its_own_module(self):
        self.release('rc0.1', module_zip('rc0.1')); ext = self.launch()
        ext.checkUpdate(); self.assertEqual(ext.updateState, 'checking'); settle(ext)
        self.assertEqual((ext.updateState, ext.newVersion), ('latest', ''))
        ext.update_at -= 10; ext.poll(); self.assertEqual(ext.updateState, '')  # The result fades back to the status line.
        self.release('rc0.2', module_zip('rc0.2'))
        ext.upgrade(); self.assertEqual(ext.updateState, '')  # Nothing is offered before a check.
        ext.checkUpdate(); settle(ext)
        self.assertEqual((ext.updateState, ext.newVersion, self.record()['active']['version']), ('available', 'rc0.2', 'rc0.1'))
        ext.upgrade(); self.assertEqual(ext.updateState, 'upgrading'); settle(ext)
        self.assertEqual((ext.updateState, ext.newVersion, ext.version, self.restarts), ('installed', 'rc0.2', 'rc0.1', [True]))
        self.assertEqual((self.record()['active']['version'], self.loaded), ('rc0.2', [('rc0.1', 'rc0.1')]))
        ext.checkUpdate(); self.assertEqual(ext.updateState, 'installed')  # Waits for the restart.
        self.assertFalse(self.check(ext))  # The updater finds it installed too.
        ext = self.launch(); self.assertEqual((ext.version, self.loaded), ('rc0.2', [('rc0.2', 'rc0.2')]))
        # A check that finds the updater's install already in place says so instead of offering it again.
        self.release('rc0.3', module_zip('rc0.3')); ext.store.update(json.loads((self.tmp/'release/modules/RIO-Modules.json').read_text()))
        ext.checkUpdate(); settle(ext); self.assertEqual((ext.updateState, ext.newVersion), ('installed', 'rc0.3'))

    def test_the_card_reports_failures_and_keeps_the_package_in_use(self):
        self.release('rc0.1', module_zip('rc0.1')); ext = self.launch(); installed = self.record()
        with patch.object(extensions, 'fetch_index', side_effect=OSError('offline')):
            ext.checkUpdate(); settle(ext)
        self.assertEqual(ext.updateState, 'failed')
        entry = self.release('rc0.2', module_zip('rc0.2'))
        ext.checkUpdate(); settle(ext); self.assertEqual(ext.updateState, 'available')
        self.publish(entry['asset'], b'x'*entry['size'])  # Damaged after listing.
        ext.upgrade(); settle(ext)
        self.assertEqual((ext.updateState, self.restarts), ('failed', [])); self.assertEqual(self.record(), installed)
        ext.update_at -= 10; ext.poll(); self.assertEqual(ext.updateState, '')

    def test_source_runs_and_capture_builds_never_update(self):
        sys.modules[PACKAGE] = type(sys)(PACKAGE); sys.modules[PACKAGE].__version__ = 'rc0.1'  # As imported from src/.
        with patch.object(extensions.importlib.util, 'find_spec', return_value=True):
            source = Extension(ModuleStore('demo', self.tmp/'modules', None, self.tmp/'host'), is_on=lambda: True, load=lambda assets: None,
                               set_on=lambda value: None, open_window=lambda: None)
        source.start(); self.assertEqual((source.state, source.version, source.updatable), ('ready', 'rc0.1', False))
        source.checkUpdate(); self.assertEqual((source.updateState, source.checker), ('', None))
        self.release('rc0.1', module_zip('rc0.1')); self.launch()
        capture = Extension(ModuleStore('demo', self.tmp/'modules', self.manifest, self.tmp/'host'), is_on=lambda: True, load=lambda assets: None,
                            set_on=lambda value: None, open_window=lambda: None, allow_download=False)
        capture.start(); self.assertEqual((capture.state, capture.updatable), ('ready', False))


@unittest.skipUnless(MODULE_SOURCES, 'Module sources are private')
class ReleaseToolTests(unittest.TestCase):
    def test_module_release_packs_one_module_at_its_own_version_and_extends_the_published_index(self):
        version = package_modules.module_version(ROOT/'src', 'blackshark')
        self.assertEqual((version, package_modules.module_version(ROOT/'src', 'fangcun')), ('rc0.1', 'rc0.1'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); runtime = tmp/'runtime'; runtime.mkdir()
            published = tmp/'published.json'
            earlier = [row('rc0.1.17.1', api=1), row('rc0.1.17.3', api=1)]  # Packages for programs before interface 2 stay listed.
            published.write_text(json.dumps({'schema': 1, 'modules': {'fangcun': [row('rc0.1')], 'blackshark': earlier}}))
            index = package_modules.release(ROOT/'src', runtime, tmp/'dist', 'blackshark', version, index=published)
            raw = (tmp/'dist/RIO-Module-BlackShark-rc0.1.zip').read_bytes()
            self.assertEqual(index['modules']['fangcun'], [row('rc0.1')])
            self.assertEqual(index['modules']['blackshark'], earlier + [dict(version='rc0.1', api=MODULE_API, asset='RIO-Module-BlackShark-rc0.1.zip', size=len(raw), sha256=hashlib.sha256(raw).hexdigest())])
            self.assertEqual(json.loads((tmp/'dist/RIO-Modules.json').read_text()), index)
            self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(raw)).read('module.json')), dict(name='blackshark', package='rio_blackshark', version='rc0.1', api=MODULE_API))
            self.assertEqual([e['version'] for e in listed_updates(index, 'blackshark')], ['rc0.1'])
            self.assertEqual(list(runtime.iterdir()), [])  # No EXE input is produced or changed.
            again = package_modules.release(ROOT/'src', runtime, tmp/'again', 'blackshark', version, index=tmp/'dist/RIO-Modules.json')
            self.assertEqual(again, index)  # Reproducible; the same package may be listed again.
            with self.assertRaisesRegex(ValueError, 'set __version__'):
                package_modules.release(ROOT/'src', runtime, tmp/'dist', 'blackshark', 'rc0.2')
            changed = dict(index); changed['modules'] = dict(index['modules'], blackshark=[dict(index['modules']['blackshark'][-1], sha256='c'*64)])
            (tmp/'changed.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'already published'):
                package_modules.release(ROOT/'src', runtime, tmp/'other', 'blackshark', version, index=tmp/'changed.json')
            self.assertFalse((tmp/'other').exists())


if __name__ == '__main__':
    unittest.main()

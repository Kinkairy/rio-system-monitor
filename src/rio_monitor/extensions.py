"""Downloadable extension modules: verified Release packages, loaded on demand and updated apart from the program."""
import importlib.util, json, re, shutil, sys, threading, urllib.request, uuid, zipfile
from pathlib import Path, PurePosixPath
from PySide6.QtCore import QObject, Signal, Property, Slot
from . import __version__
from .updater import REPOSITORY, download_asset, version_key

PACKAGES = {'fangcun': 'rio_fangcun', 'blackshark': 'rio_blackshark'}
# Version of what modules use from the host: the host adapters, shared Rio.UI components and their properties,
# libraries bundled in the EXE and the calls the host makes into a module. Raise it whenever a module could come to
# depend on a change there; a module-only update installs only on hosts with the same value.
MODULE_API = 1
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/download/{version}/{asset}'
# Module-only updates live in one prerelease, so releases/latest stays the program.
UPDATES = 'modules'
INDEX = 'RIO-Modules.json'
UPDATE_ASSET = re.compile(r'RIO-Module-[A-Za-z]+-[0-9A-Za-z.]+\.zip')


def read_manifest(assets):
    """Packaged builds carry modules.json; source runs import modules from src/ instead."""
    path = Path(assets) / 'modules.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def fetch_index():
    """The published module index; raises when it cannot be read."""
    request = urllib.request.Request(RELEASE_URL.format(version=UPDATES, asset=INDEX), headers={'User-Agent': 'RIO-System-Monitor/' + __version__})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read(1_000_000))


def listed_updates(index, name):
    """This host's usable index entries for one module; malformed or incompatible rows are skipped."""
    modules = index.get('modules') if isinstance(index, dict) and index.get('schema') == 1 else None
    rows = modules.get(name) if isinstance(modules, dict) else None
    entries = []
    for row in rows if isinstance(rows, list) else []:
        try:
            valid = (row['api'] == MODULE_API and type(row['size']) is int and row['size'] > 0
                     and re.fullmatch('[0-9a-f]{64}', row['sha256']) and UPDATE_ASSET.fullmatch(row['asset'])
                     and version_key(row['version']) > (0, 0, 0, 0))
        except (KeyError, TypeError):
            valid = False
        if valid:
            entries.append(dict(asset=row['asset'], size=row['size'], sha256=row['sha256'], version=row['version'], api=MODULE_API, release=UPDATES))
    return entries


class ModuleStore:
    """One module package: importable as source, or installed from the EXE's pinned download or a newer listed update."""
    def __init__(self, name, root, manifest, host_assets, version=__version__):
        self.name, self.package = name, PACKAGES[name]
        self.root, self.host_assets = Path(root) / name, Path(host_assets)
        pinned, version = (manifest or {}).get('modules', {}).get(name), (manifest or {}).get('version', version)
        # The EXE's own package is the baseline: always available from the program's Release and the last fallback.
        self.pinned = pinned and dict(pinned, version=version, release=version)
        self.listed = []  # Updates from the last index read; empty until a check succeeds.

    @property
    def entry(self):
        """The package to install: the newest of the pinned one and listed updates that never failed here."""
        if self.pinned is None:
            return None
        bad = self.record().get('bad', [])
        newer = [e for e in self.listed if e['sha256'] not in bad and version_key(e['version']) > version_key(self.pinned['version'])]
        return max([self.pinned] + newer, key=lambda e: version_key(e['version']))

    def record(self):
        """active.json: the package in use, the one before it and updates that failed to load here."""
        try:
            data = json.loads((self.root / 'active.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, **record):
        path = self.root / 'active.json'; temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record, indent=2), encoding='utf-8'); temp.replace(path)

    def _installed(self, entry):
        return isinstance(entry, dict) and isinstance(entry.get('sha256'), str) and (self.root / entry['sha256'][:16] / self.package / '__init__.py').is_file()

    def current(self):
        """The installed package to load: the recorded one while it suits this program, else the pinned one."""
        if self.pinned is None:
            return None
        record = self.record(); active = record.get('active')
        if self._installed(active) and active['sha256'] not in record.get('bad', []) and (
                active['sha256'] == self.pinned['sha256']
                or (active.get('api') == MODULE_API and version_key(active.get('version')) > version_key(self.pinned['version']))):
            return active
        return self.pinned if self._installed(self.pinned) else None

    def location(self):
        """Return the module's assets directory once its code can be imported, else None."""
        if self.pinned is None:
            return self.host_assets if importlib.util.find_spec(self.package) else None
        current = self.current()
        if current is None:
            return None
        target = self.root / current['sha256'][:16]
        if str(target) not in sys.path:
            sys.path.insert(0, str(target))
        return target / 'assets' if (target / 'assets').is_dir() else self.host_assets

    def install(self, stop=None, progress=None, entry=None):
        entry = entry or self.entry
        asset = dict(browser_download_url=RELEASE_URL.format(version=entry['release'], asset=entry['asset']),
                     digest='sha256:' + entry['sha256'], size=entry['size'], version=entry['version'], file=entry['asset'])
        archive = download_asset(asset, self.root / 'downloads', stop, progress)
        before, record = self.current(), self.record()
        target, staging = self.root / entry['sha256'][:16], self.root / ('.staging-' + uuid.uuid4().hex)
        expected = dict(name=self.name, package=self.package, version=entry['version'], **({'api': entry['api']} if 'api' in entry else {}))
        try:
            with zipfile.ZipFile(archive) as package:
                for name in package.namelist():
                    parts = PurePosixPath(name).parts
                    if name.startswith('/') or '..' in parts or not parts or parts[0] not in (self.package, 'assets', 'module.json'):
                        raise ValueError('Unexpected file in module package: ' + name)
                info = json.loads(package.read('module.json')) if 'module.json' in package.namelist() else None
                if not isinstance(info, dict) or any(info.get(key) != value for key, value in expected.items()):
                    raise ValueError('Module package does not match its listing')
                package.extractall(staging)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            archive.unlink(missing_ok=True)
        previous = before if before and before['sha256'] != entry['sha256'] else record.get('previous')
        self._save(active=entry, previous=previous, bad=record.get('bad', []))
        # The package in use and the one before it stay for falling back; anything older is removed.
        keep = {target, self.root / 'downloads'} | ({self.root / previous['sha256'][:16]} if self._installed(previous) else set())
        for old in self.root.iterdir():
            if old.is_dir() and old not in keep:
                shutil.rmtree(old, ignore_errors=True)

    def update(self, index, stop=None):
        """Take the entries of a fresh index and install the chosen package beside the one in use; True once installed."""
        self.listed = listed_updates(index, self.name)
        current, entry = self.current(), self.entry
        if current is None or entry is None or entry['sha256'] == current['sha256']:
            return False
        self.install(stop, entry=entry)
        return True

    def reject(self):
        """The package in use failed to load: never pick it again and unload it; False when only the pinned one is left."""
        current = self.current()
        if current is None or current['sha256'] == self.pinned['sha256']:
            return False
        record = self.record()
        self._save(active=record.get('previous'), previous=None, bad=sorted(set(record.get('bad', [])) | {current['sha256']}))
        failed = str(self.root / current['sha256'][:16])
        while failed in sys.path:
            sys.path.remove(failed)
        for module in [m for m in sys.modules if m == self.package or m.startswith(self.package + '.')]:
            del sys.modules[module]
        return True


def update_modules(extensions, stop=None):
    """Updater step: read the module index once and update each loaded module; True when a restart would load one."""
    try:
        index = fetch_index()
    except Exception:
        return False  # No reachable index: every installed package stays as it is.
    installed = False
    for ext in extensions.values():
        if ext.state != 'ready':
            ext.store.listed = listed_updates(index, ext.store.name)  # Used when the module is first switched on.
            continue
        try:
            installed = ext.store.update(index, stop) or installed
        except Exception:
            pass  # A failed download or a mismatched package keeps the one in use.
    return installed


class Extension(QObject):
    """Settings card state for one module; the host supplies what loading and switching mean."""
    changed = Signal()

    def __init__(self, store, *, is_on, load, set_on, open_window, allow_download=True):
        super().__init__()
        self.store, self.is_on, self.load, self.set_on, self.open_window = store, is_on, load, set_on, open_window
        self.allow_download = allow_download
        self.assets = store.location()
        self._state = 'ready' if self.assets is not None else 'missing'
        self._progress, self.stop, self.worker, self.result, self.error = 0., threading.Event(), None, None, ''

    def _size(self):
        size = (self.store.entry or {}).get('size', 0)
        return f'{size/1_000_000:.0f} MB' if size >= 1_000_000 else f'{max(1, round(size/1000))} KB' if size else ''

    enabled = Property(bool, lambda self: self._state == 'downloading' or (self._state == 'ready' and self.is_on()), notify=changed)
    state = Property(str, lambda self: self._state, notify=changed)
    progress = Property(float, lambda self: self._progress, notify=changed)
    downloadSize = Property(str, _size, notify=changed)

    def start(self):
        """At launch: load an installed module, or fetch one the saved settings already enable."""
        if self._state == 'ready':
            self._activate()
        elif self.is_on() and self.allow_download and self.store.entry:
            self.download()

    def _activate(self):
        try:
            self.load(self.assets)
        except Exception as ex:
            # An update that fails to load is dropped for the package installed before it.
            assets = self.store.location() if self.store.reject() else None
            if assets is None:
                self._state, self.error = 'error', str(ex)
                return False
            self.assets = assets
            return self._activate()
        return True

    @Slot(bool)
    def setEnabled(self, value):
        if self._state == 'downloading':
            if not value:
                self.stop.set()  # The worker reports the cancellation on the next poll.
        elif not value:
            if self._state == 'ready':
                self.set_on(False)
        elif self._state == 'ready':
            self.set_on(True)
        elif self.allow_download and self.store.entry:
            self.download()
        else:
            self._state, self.error = 'error', 'Module package unavailable'
        self.changed.emit()

    @Slot()
    def open(self):
        if self._state == 'ready':
            self.open_window()

    def download(self):
        self.stop.clear()
        self._state, self._progress, self.result = 'downloading', 0., None
        def run():
            try:
                self.store.install(self.stop, lambda done, total: setattr(self, '_progress', done / max(1, total)))
                self.result = 'ready'
            except Exception as ex:
                self.result, self.error = ('cancelled' if self.stop.is_set() else 'error'), str(ex)
        self.worker = threading.Thread(target=run, daemon=True, name='RIO-module-' + self.store.name)
        self.worker.start()

    def poll(self):
        """GUI-thread step: publish progress and load the module once its download finishes."""
        if self._state != 'downloading':
            return
        if self.worker.is_alive():
            self.changed.emit()
            return
        self.worker = None
        if self.result == 'ready':
            self.assets = self.store.location()
            self._state = 'ready' if self.assets is not None else 'error'
            if self._state == 'ready' and self._activate():
                self.set_on(True)
        else:
            self._state = 'missing' if self.result == 'cancelled' else 'error'
        self.changed.emit()

    def close(self):
        self.stop.set()
        worker = self.worker
        if worker:
            worker.join(2)
        return not (worker and worker.is_alive())


def import_path(name, assets, root):
    """Make an installed module importable for an explicit command-line entry; False when absent."""
    return ModuleStore(name, root, read_manifest(assets), assets).location() is not None

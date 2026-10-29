"""Downloadable extension modules: verified packages from the module Release, loaded on demand and updated apart from the program."""
import importlib.util, json, re, shutil, sys, threading, time, urllib.request, uuid, zipfile
from pathlib import Path, PurePosixPath
from PySide6.QtCore import QObject, Signal, Property, Slot
from . import __version__
from .updater import REPOSITORY, download_asset, version_key

PACKAGES = {'fangcun': 'rio_fangcun', 'blackshark': 'rio_blackshark'}
# Version of what modules use from the host: the host adapters, shared Rio.UI components and their properties,
# libraries bundled in the EXE and the calls the host makes into a module. Raise it whenever a module could come to
# depend on a change there; a module package installs only on hosts with the same value.
# 2: modules carry their own version numbers (rc0.1 onward) and come only from the module Release, never the program's.
MODULE_API = 2
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/download/{version}/{asset}'
# Module packages live in one prerelease, so releases/latest stays the program.
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
    """One module package: importable as source, or installed from the module index and updated there."""
    def __init__(self, name, root, manifest, host_assets):
        self.name, self.package = name, PACKAGES[name]
        self.root, self.host_assets = Path(root) / name, Path(host_assets)
        # Packaged builds list the modules they host; their code is never in the EXE and comes only from the index.
        self.packaged = name in (manifest or {}).get('modules', ())
        self.listed = []  # Entries from the last index read; empty until a read succeeds.
        self.lock = threading.Lock()  # The updater and the settings card may both install.

    @property
    def entry(self):
        """The package to install: the newest listed one that never failed here."""
        bad = self.record().get('bad', [])
        usable = [e for e in self.listed if e['sha256'] not in bad]
        return max(usable, key=lambda e: version_key(e['version'])) if usable else None

    def refresh(self, index=None):
        """Read this module's entries from the module index, fetched now unless given; returns the entry to install."""
        self.listed = listed_updates(fetch_index() if index is None else index, self.name)
        return self.entry

    def record(self):
        """active.json: the package in use, the one before it and packages that failed to load here."""
        try:
            data = json.loads((self.root / 'active.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, **record):
        path = self.root / 'active.json'; temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record, indent=2), encoding='utf-8'); temp.replace(path)

    def _usable(self, entry, record):
        """Installed, built for this host and never failed to load here."""
        return (isinstance(entry, dict) and isinstance(entry.get('sha256'), str) and entry.get('api') == MODULE_API
                and entry['sha256'] not in record.get('bad', []) and (self.root / entry['sha256'][:16] / self.package / '__init__.py').is_file())

    def current(self):
        """The installed package to load, or None until one suiting this host is installed."""
        record = self.record()
        return record['active'] if self.packaged and self._usable(record.get('active'), record) else None

    def location(self):
        """Return the module's assets directory once its code can be imported, else None."""
        if not self.packaged:
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
        if entry is None:
            raise LookupError('No package of this module is listed for this program')
        with self.lock:
            self._install(entry, stop, progress)

    def _install(self, entry, stop, progress):
        asset = dict(browser_download_url=RELEASE_URL.format(version=entry['release'], asset=entry['asset']),
                     digest='sha256:' + entry['sha256'], size=entry['size'], version=entry['version'], file=entry['asset'])
        archive = download_asset(asset, self.root / 'downloads', stop, progress)
        before, record = self.current(), self.record()
        target, staging = self.root / entry['sha256'][:16], self.root / ('.staging-' + uuid.uuid4().hex)
        expected = dict(name=self.name, package=self.package, version=entry['version'], api=entry['api'])
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
        previous = previous if self._usable(previous, record) and previous['sha256'] != entry['sha256'] else None
        self._save(active=entry, previous=previous, bad=record.get('bad', []))
        # The package in use and the one before it stay for falling back; anything older, or for another host, is removed.
        keep = {target, self.root / 'downloads'} | ({self.root / previous['sha256'][:16]} if previous else set())
        for old in self.root.iterdir():
            if old.is_dir() and old not in keep:
                shutil.rmtree(old, ignore_errors=True)

    def reject(self):
        """The package in use failed to load: never pick it again and fall back to the one before it; False when none is left."""
        current = self.current()
        if current is None:
            return False
        record = self.record()
        self._save(active=record.get('previous'), previous=None, bad=sorted(set(record.get('bad', [])) | {current['sha256']}))
        failed = str(self.root / current['sha256'][:16])
        while failed in sys.path:
            sys.path.remove(failed)
        for module in [m for m in sys.modules if m == self.package or m.startswith(self.package + '.')]:
            del sys.modules[module]
        return self.current() is not None


def update_modules(extensions):
    """Updater step: read the module index once; each card offers a newer package, installed only when clicked."""
    try:
        index = fetch_index()
    except Exception:
        return  # No reachable index: the cards keep what they show.
    for ext in extensions.values():
        ext.offer(index)


class Extension(QObject):
    """Settings card state for one module; the host supplies what loading and switching mean."""
    changed = Signal()

    def __init__(self, store, *, is_on, load, set_on, open_window, allow_download=True, installed=lambda: None):
        super().__init__()
        self.store, self.is_on, self.load, self.set_on, self.open_window = store, is_on, load, set_on, open_window
        # installed() runs once an update is in place; it loads at the next start, which packaged hosts make once idle.
        self.allow_download, self.installed = allow_download, installed
        self.assets = store.location()
        self._state = 'ready' if self.assets is not None else 'missing'
        self._progress, self.stop, self.worker, self.result, self.error = 0., threading.Event(), None, None, ''
        # The card's update state: what it shows, the version it offers or installed, and its worker's result.
        # loaded is the package running now; found is a newer version the updater's check listed, offered at the next poll.
        self.loaded, self.found, self._update, self._offer = None, None, '', ''
        self.checker, self.update_result, self.update_at = None, None, 0.

    def _size(self):
        size = (self.store.entry or {}).get('size', 0)
        return f'{size/1_000_000:.0f} MB' if size >= 1_000_000 else f'{max(1, round(size/1000))} KB' if size else ''

    def _version(self):
        """The module version in use; before the first download, the one that would be installed."""
        if self._state != 'ready':
            return (self.store.entry or {}).get('version', '')
        return (self.loaded or {}).get('version') or getattr(sys.modules.get(self.store.package), '__version__', '')

    enabled = Property(bool, lambda self: self._state == 'downloading' or (self._state == 'ready' and self.is_on()), notify=changed)
    state = Property(str, lambda self: self._state, notify=changed)
    progress = Property(float, lambda self: self._progress, notify=changed)
    downloadSize = Property(str, _size, notify=changed)
    version = Property(str, _version, notify=changed)
    # '', checking, latest, available, upgrading, installed or failed; newVersion is the one offered or installed.
    updateState = Property(str, lambda self: self._update, notify=changed)
    newVersion = Property(str, lambda self: self._offer, notify=changed)
    updatable = Property(bool, lambda self: self._state == 'ready' and self.store.packaged and self.allow_download, notify=changed)

    def start(self):
        """At launch: load an installed module, or fetch one the saved settings already enable."""
        if self._state == 'ready':
            self._activate()
        elif self.is_on() and self.allow_download and self.store.packaged:
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
        self.loaded = self.store.current()
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
        elif self.allow_download and self.store.packaged:
            self.download()
        else:
            self._state, self.error = 'error', 'Module package unavailable'
        self.changed.emit()

    @Slot()
    def open(self):
        if self._state == 'ready':
            self.open_window()

    @Slot()
    def checkUpdate(self):
        """Card link: read the module index now; a different package it lists is then offered to upgrade()."""
        if not self.updatable or self.checker or self._update == 'installed':
            return
        def check():
            entry, current = self.store.refresh(), self.store.current()
            if entry is None or entry['sha256'] == (self.loaded or {}).get('sha256'):
                return 'latest', ''
            return ('installed' if current and current['sha256'] == entry['sha256'] else 'available'), entry['version']
        self._work('checking', check)

    @Slot()
    def upgrade(self):
        """Card link, clicked on an offer: install the package beside the one in use; it loads at the next start."""
        entry = self.store.entry
        if self._update != 'available' or self.checker or entry is None:
            return
        def install():
            self.store.install(self.stop, lambda done, total: setattr(self, '_progress', done / max(1, total)), entry=entry)
            return 'installed', entry['version']
        self.stop.clear(); self._progress = 0.
        self._work('upgrading', install)

    def offer(self, index):
        """Updater step, off the GUI thread: list this module's packages; a newer one is offered at the next poll."""
        entry = self.store.refresh(index)  # Before the first download this also gives the card its download size.
        if self.updatable and entry and entry['sha256'] != (self.loaded or {}).get('sha256'):
            self.found = entry['version']

    def _work(self, state, job):
        def run():
            try:
                self.update_result = job()
            except Exception as ex:
                self.update_result, self.error = ('failed', ''), str(ex)
        self._update, self.update_result = state, None
        self.checker = threading.Thread(target=run, daemon=True, name='RIO-module-update-' + self.store.name)
        self.checker.start()
        self.changed.emit()

    def _poll_update(self):
        if self.found and not self.checker:
            # The updater's check offers what the card's own would; an offer, upgrade or install already shown stays.
            if self._update in ('', 'latest', 'failed'):
                self._update, self._offer = 'available', self.found
                self.changed.emit()
            self.found = None
        if self.checker is None:
            # A result that needs nothing more fades back to the module's own status line.
            if self._update in ('latest', 'failed') and time.monotonic() - self.update_at > 5:
                self._update = ''; self.changed.emit()
            return
        if self.checker.is_alive():
            if self._update == 'upgrading':
                self.changed.emit()
            return
        self.checker = None
        (self._update, self._offer), self.update_at = self.update_result, time.monotonic()
        if self._update == 'installed':
            self.installed()
        self.changed.emit()

    def download(self):
        self.stop.clear()
        self._state, self._progress, self.result = 'downloading', 0., None
        def run():
            try:
                self.store.refresh()  # The newest package listed for this host.
                self.store.install(self.stop, lambda done, total: setattr(self, '_progress', done / max(1, total)))
                self.result = 'ready'
            except Exception as ex:
                self.result, self.error = ('cancelled' if self.stop.is_set() else 'error'), str(ex)
        self.worker = threading.Thread(target=run, daemon=True, name='RIO-module-' + self.store.name)
        self.worker.start()

    def poll(self):
        """GUI-thread step: publish progress, load the module once its download finishes and show update results."""
        self._poll_update()
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
        # An index read changes nothing on disk and may be left behind; downloads and upgrades stop first.
        workers = [w for w in (self.worker, self.checker if self._update == 'upgrading' else None) if w]
        for worker in workers:
            worker.join(2)
        return not any(worker.is_alive() for worker in workers)


def import_path(name, assets, root):
    """Make an installed module importable for an explicit command-line entry; False when absent."""
    return ModuleStore(name, root, read_manifest(assets), assets).location() is not None

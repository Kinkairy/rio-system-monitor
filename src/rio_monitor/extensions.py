"""Downloadable extension modules: pinned Release packages, verified before use, loaded on demand."""
import importlib.util, json, shutil, sys, threading, uuid, zipfile
from pathlib import Path, PurePosixPath
from PySide6.QtCore import QObject, Signal, Property, Slot
from . import __version__
from .updater import REPOSITORY, download_asset

PACKAGES = {'fangcun': 'rio_fangcun', 'blackshark': 'rio_blackshark'}
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/download/{version}/{asset}'


def read_manifest(assets):
    """Packaged builds carry modules.json; source runs import modules from src/ instead."""
    path = Path(assets) / 'modules.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


class ModuleStore:
    """One module package, either importable as source or installed from its pinned download."""
    def __init__(self, name, root, manifest, host_assets, version=__version__):
        self.name, self.package = name, PACKAGES[name]
        self.root, self.host_assets, self.version = Path(root) / name, Path(host_assets), version
        self.entry = (manifest or {}).get('modules', {}).get(name)

    def location(self):
        """Return the module's assets directory once its code can be imported, else None."""
        if self.entry is None:
            return self.host_assets if importlib.util.find_spec(self.package) else None
        target = self.root / self.entry['sha256'][:16]
        if not (target / self.package / '__init__.py').is_file():
            return None
        if str(target) not in sys.path:
            sys.path.insert(0, str(target))
        return target / 'assets' if (target / 'assets').is_dir() else self.host_assets

    def install(self, stop=None, progress=None):
        entry = self.entry
        asset = dict(browser_download_url=RELEASE_URL.format(version=self.version, asset=entry['asset']),
                     digest='sha256:' + entry['sha256'], size=entry['size'], version=self.version, file=entry['asset'])
        archive = download_asset(asset, self.root / 'downloads', stop, progress)
        target, staging = self.root / entry['sha256'][:16], self.root / ('.staging-' + uuid.uuid4().hex)
        try:
            with zipfile.ZipFile(archive) as package:
                for name in package.namelist():
                    parts = PurePosixPath(name).parts
                    if name.startswith('/') or '..' in parts or not parts or parts[0] not in (self.package, 'assets', 'module.json'):
                        raise ValueError('Unexpected file in module package: ' + name)
                package.extractall(staging)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            archive.unlink(missing_ok=True)
        # Earlier versions of this module are replaced, not kept beside it.
        for old in self.root.iterdir():
            if old.is_dir() and old not in (target, self.root / 'downloads'):
                shutil.rmtree(old, ignore_errors=True)


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
            self._state, self.error = 'error', str(ex)
            return False
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

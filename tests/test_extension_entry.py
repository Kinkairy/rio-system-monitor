"""Settings is the only module entry: one switch and one settings button per extension."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile, threading, time, unittest
from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl, QMetaObject, QPointF, Qt
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from rio_monitor.qt_app import Bridge, Frames
from rio_monitor.settings import Settings
from rio_monitor.ui import install_ui
from rio_monitor.extensions import Extension

ASSETS = Path(__file__).resolve().parents[1]/'assets'


class Fangcun(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__(); self._enabled = False; self.refuse = False; self.opened = 0
    enabled = Property(bool, lambda self: self._enabled, notify=changed)
    @Slot(bool)
    def setEnabled(self, value):
        if not self.refuse: self._enabled = value
        self.changed.emit()
    @Slot()
    def openPanel(self): self.opened += 1


class Module:
    def __init__(self, busy=False, closes=True):
        self.busy, self.closes, self.pages, self.starts, self.closed = busy, closes, [], 0, 0
        self.runtime = Mock(); self.runtime.snapshot = lambda: dict(busy=self.busy)
    def show(self, page=0): self.pages.append(page)
    def start(self): self.starts += 1
    def close(self): self.closed += 1; return self.closes


def visible(obj): return obj.property('visible') and obj.property('enabled')


def item(window, name):
    pending = [window.contentItem()]
    while pending:
        current = pending.pop()
        if current.objectName() == name: return current
        pending.extend(current.childItems())


def click(window, name):
    target = item(window, name); point = target.mapToScene(QPointF(target.width()/2, target.height()/2)).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point); QTest.qWait(40)


class Installed:
    name, package, packaged, entry = 'demo', 'rio_entry_demo', True, None
    def location(self): return ASSETS
    def current(self): return {'version': 'rc0.1', 'sha256': 'b'*64}
    def refresh(self): return self.entry


class Downloadable(Installed):
    entry = {'size': 58_000_000}
    def __init__(self): self.ready = False; self.gate = threading.Event()
    def location(self): return ASSETS if self.ready else None
    def current(self): return Installed.current(self) if self.ready else None
    def install(self, stop, progress):
        progress(1, 4); self.gate.wait(5); self.ready = True


class Updatable(Installed):
    """An installed module whose index lists a newer package once read."""
    def __init__(self): self.entry, self.installs, self.gate = None, [], threading.Event()
    def refresh(self):
        self.entry = dict(version='rc0.2', sha256='c'*64, size=45_000); return self.entry
    def install(self, stop, progress, entry):
        progress(1, 2); self.gate.wait(5); self.installs.append(entry['version'])


def child(parent, name):
    pending = [parent]
    while pending:
        current = pending.pop()
        if current.objectName() == name: return current
        pending.extend(current.childItems())


def settle(ext):
    for _ in range(200):
        ext.poll()
        if ext.checker is None: return
        time.sleep(.01)


def load_settings(bridge, fangcun_ext, blackshark_ext):
    engine = QQmlApplicationEngine(); install_ui(engine, ASSETS); engine.addImageProvider('monitor', bridge.frames)
    for name, value in (('bridge', bridge), ('fangcunExt', fangcun_ext), ('blacksharkExt', blackshark_ext)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(ASSETS/'ui/Main.qml')))
    assert engine.rootObjects(); window = engine.rootObjects()[0]; bridge.win = window; window.show(); QTest.qWait(50)
    return engine, window


class ExtensionEntryTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    QQuickStyle.setStyle('Basic'); cls.app = QApplication.instance() or QApplication([])

  def setUp(self):
    folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
    environment = patch.dict(os.environ, {'LOCALAPPDATA': folder.name}); environment.start(); self.addCleanup(environment.stop)
    self.bridge = Bridge(self.app, Settings(language='zh'), Mock(), Frames(), capture=True)
    self.addCleanup(lambda: (self.bridge.save_timer.stop(), self.bridge.storage.close()))

  def test_extensions_header_tab_shows_switch_and_settings_per_module(self):
    app, bridge = self.app, self.bridge
    fangcun = Fangcun()
    # Wired as in qt_app.main for installed modules.
    fangcun_ext = Extension(Installed(), is_on=lambda: fangcun.enabled, load=lambda assets: None, set_on=fangcun.setEnabled, open_window=fangcun.openPanel)
    blackshark_ext = Extension(Installed(), is_on=lambda: bridge.s.blackshark_enabled, load=lambda assets: None, set_on=bridge.setBlackSharkEnabled, open_window=bridge.openBlackShark)
    fangcun.changed.connect(fangcun_ext.changed); bridge.changed.connect(fangcun_ext.changed); bridge.changed.connect(blackshark_ext.changed)
    engine, window = load_settings(bridge, fangcun_ext, blackshark_ext)
    shown = []
    bridge._blackshark = lambda: shown.append(1) or module
    module = Module()
    try:
        assert (window.width(), window.height()) == (448, 730)
        assert window.findChild(QObject, 'extensionsPopup') is None and window.findChild(QObject, 'extensionsButton') is None
        settings, page, save = (window.findChild(QObject, n) for n in ('settingsPage', 'extensionsPage', 'saveButton'))
        assert window.property('tab') == 0 and settings.property('visible') and not page.property('visible') and save.property('visible')
        click(window, 'headerTab1')
        assert window.property('tab') == 1 and page.property('visible') and not settings.property('visible') and not save.property('visible')
        cultivation = window.findChild(QObject, 'cultivationSwitch'); cooler = window.findChild(QObject, 'blacksharkSwitch')
        open_fangcun = window.findChild(QObject, 'fangcunOpenButton'); open_cooler = window.findChild(QObject, 'blacksharkOpenButton')
        assert not cultivation.property('checked') and not cooler.property('checked')
        assert not open_fangcun.property('enabled') and not open_cooler.property('enabled')
        # A refused switch returns to the module state and stays bound to it.
        fangcun.refuse = True; cultivation.setProperty('checked', True); QMetaObject.invokeMethod(cultivation, 'toggled')
        assert not cultivation.property('checked')
        fangcun.refuse = False; fangcun.setEnabled(True); assert cultivation.property('checked') and visible(open_fangcun)
        QMetaObject.invokeMethod(open_fangcun, 'clicked'); QTest.qWait(40)
        assert fangcun.opened == 1 and page.property('visible')
        bridge.storage.update(busy=True); bridge.changed.emit(); assert not cultivation.property('enabled')
        bridge.storage.update(busy=False); bridge.changed.emit()
        cooler.setProperty('checked', True); QMetaObject.invokeMethod(cooler, 'toggled')
        assert bridge.s.blackshark_enabled and cooler.property('checked') and visible(open_cooler)
        QMetaObject.invokeMethod(open_cooler, 'clicked'); QTest.qWait(40)
        assert module.pages == [0] and page.property('visible')
        bridge.setLanguage('en'); QTest.qWait(20)
        assert open_cooler.property('text') == 'Open settings' and window.property('tabs').toVariant() == ['Settings', 'Extensions']
        click(window, 'headerTab0'); assert settings.property('visible') and not page.property('visible')
    finally:
        window.hide(); engine.deleteLater(); app.processEvents()


  def test_missing_module_card_shows_size_progress_and_opens_only_when_ready(self):
    app, bridge = self.app, self.bridge
    store, fangcun = Downloadable(), Fangcun(); loaded = []
    fangcun_ext = Extension(store, is_on=lambda: fangcun.enabled, load=loaded.append, set_on=fangcun.setEnabled, open_window=fangcun.openPanel)
    blackshark_ext = Extension(Installed(), is_on=lambda: False, load=lambda assets: None, set_on=lambda value: None, open_window=lambda: None)
    fangcun.changed.connect(fangcun_ext.changed)
    engine, window = load_settings(bridge, fangcun_ext, blackshark_ext)
    try:
        card = window.findChild(QObject, 'fangcunExtension'); switch = window.findChild(QObject, 'cultivationSwitch')
        opener = window.findChild(QObject, 'fangcunOpenButton')
        click(window, 'headerTab1')
        assert card.property('detail') == '未下载 · 开启后下载 · 58 MB' and not switch.property('checked') and not opener.property('enabled')
        switch.setProperty('checked', True); QMetaObject.invokeMethod(switch, 'toggled'); fangcun_ext.poll(); QTest.qWait(20)
        assert card.property('detail') == '正在下载 25%' and card.property('progress') == .25 and switch.property('checked') and not opener.property('enabled')
        # The switch waits for the download; the update link appears only once the module is installed.
        assert not switch.property('enabled') and not child(item(window, 'fangcunExtension'), 'moduleUpdateLink').property('visible')
        QTest.qWait(200); assert switch.property('indicator').property('color').name() == '#587c2b'  # Dimmed, still reads as on.
        assert any(v.property('visible') for v in window.findChildren(QObject, 'downloadTrack'))
        store.gate.set()
        for _ in range(100):
            fangcun_ext.poll()
            if fangcun_ext.state != 'downloading': break
            time.sleep(.01)
        QTest.qWait(20)
        assert loaded == [ASSETS] and fangcun.enabled and card.property('detail') == '修仙模式已开启'
        assert card.property('progress') == -1 and opener.property('enabled') and not card.property('failed')
        assert switch.property('enabled') and visible(child(item(window, 'fangcunExtension'), 'moduleUpdateLink'))
    finally:
        window.hide(); engine.deleteLater(); app.processEvents()


  def test_cards_show_module_versions_and_offer_each_update_behind_a_link(self):
    app, bridge = self.app, self.bridge
    store, restarts = Updatable(), []
    fangcun_ext = Extension(Installed(), is_on=lambda: False, load=lambda assets: None, set_on=lambda value: None, open_window=lambda: None)
    blackshark_ext = Extension(store, is_on=lambda: False, load=lambda assets: None, set_on=lambda value: None, open_window=lambda: None,
                               installed=lambda: restarts.append(True))
    fangcun_ext.start(); blackshark_ext.start()
    engine, window = load_settings(bridge, fangcun_ext, blackshark_ext)
    def press(link):
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, link.mapToScene(link.boundingRect().center()).toPoint())
    try:
        click(window, 'headerTab1')
        fangcun_card, card = item(window, 'fangcunExtension'), item(window, 'blacksharkExtension')
        assert child(fangcun_card, 'moduleVersion').property('text') == 'rc0.1' and child(card, 'moduleVersion').property('text') == 'rc0.1'
        link, opener, switch = child(card, 'moduleUpdateLink'), child(card, 'blacksharkOpenButton'), child(card, 'blacksharkSwitch')
        assert visible(link) and link.property('text') == 'Check updates' and opener.property('width') == card.property('width')-28
        assert card.property('detail') == '散热器控制未开启' and child(card, 'moduleUpdateButton') is None
        press(link); settle(blackshark_ext); QTest.qWait(20)
        assert card.property('detail') == '发现新版本 rc0.2' and link.property('text') == 'Update to rc0.2' and visible(link)
        assert child(card, 'moduleVersion').property('text') == 'rc0.1' and store.installs == []
        press(link)
        for _ in range(100):
            blackshark_ext.poll()
            if blackshark_ext.progress == .5: break
            time.sleep(.01)
        QTest.qWait(20)
        assert card.property('detail') == '正在升级 50%' and not link.property('enabled') and not switch.property('enabled')
        store.gate.set(); settle(blackshark_ext); QTest.qWait(20)
        assert store.installs == ['rc0.2'] and restarts == [True] and switch.property('enabled')
        assert card.property('detail') == '已升级到 rc0.2 · 重启后生效' and link.property('text') == 'Check updates' and not link.property('enabled')
        assert child(card, 'moduleVersion').property('text') == 'rc0.1'  # The running package until RIO restarts.
        # The other card is untouched by this module's update.
        assert child(fangcun_card, 'moduleUpdateLink').property('text') == 'Check updates' and fangcun_card.property('detail') == '修仙模式未开启'
    finally:
        store.gate.set(); window.hide(); engine.deleteLater(); app.processEvents()


  def test_blackshark_switch_starts_stops_and_never_interrupts_a_device_write(self):
    bridge = self.bridge
    bridge.capture = False; created = []
    bridge._blackshark = lambda: bridge.blackshark_module or created.append(Module()) or setattr(bridge, 'blackshark_module', created[-1]) or created[-1]
    bridge.setBlackSharkEnabled(True)
    assert bridge.s.blackshark_enabled and created[0].starts == 1
    created[0].busy = True; bridge.setBlackSharkEnabled(False)
    assert bridge.s.blackshark_enabled and created[0].closed == 0 and '请稍候' in bridge.notice
    created[0].busy = False; created[0].closes = False; bridge.setBlackSharkEnabled(False)
    assert bridge.s.blackshark_enabled and bridge.blackshark_module is created[0]
    created[0].closes = True; bridge.setBlackSharkEnabled(False)
    assert not bridge.s.blackshark_enabled and bridge.blackshark_module is None
    # A closed module is replaced, never reused.
    bridge.setBlackSharkEnabled(True); assert len(created) == 2 and created[1].starts == 1
    bridge.capture = True


  def test_startup_resume_follows_the_switch(self):
    bridge = self.bridge
    bridge.capture = False; module = Module(); bridge._blackshark = lambda: module
    bridge.resumeBlackShark(); assert module.starts == 0
    bridge.s.blackshark_enabled = True; bridge.resumeBlackShark(); assert module.starts == 1
    bridge.capture = True


  def test_tray_keeps_only_program_actions(self):
    bridge = self.bridge
    bridge.tray = QSystemTrayIcon(); bridge.updateMenu()
    assert [a.text() for a in bridge.menu.actions()] == ['退出', '设置', '登录后启动']
    assert all(a.menu() is None for a in bridge.menu.actions())
    bridge.setLanguage('en')
    assert [a.text() for a in bridge.menu.actions()] == ['Exit', 'Settings', 'Start at login']


if __name__ == '__main__':
    unittest.main()

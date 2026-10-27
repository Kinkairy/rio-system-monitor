"""RIO host adapter: shared UI/engine, telemetry and the maintained WASAPI service."""
import time
from PySide6.QtCore import QObject,Signal,Property,Slot
from .ui import create_panel

class BlackSharkHost(QObject):
    changed=Signal()
    def __init__(self,bridge,engine):
        super().__init__();self.bridge=bridge;self.engine=engine;self._panels=[]
        bridge.changed.connect(self.changed)
    language=Property(str,lambda self:self.bridge.s.language,notify=changed)
    @Slot(str)
    def setLanguage(self,value):self.bridge.setLanguage(value)
    def samples(self):return self.bridge.blackshark_samples()
    def reactive(self):return HostAudio()
    def create_window(self,source,properties,context):
        window,owner=create_panel(self.engine,source,properties,context)
        self._panels.append(owner);window.setIcon(self.bridge.app.windowIcon());return window
    def release_window(self,window):
        for owner in list(self._panels):
            if owner[0] is window:
                self._panels.remove(owner)
                for obj in owner:obj.deleteLater()
                return

class HostAudio:
    def __init__(self):
        from .music.state import Audio
        self.audio = Audio()
        self.loopback = None

    def configure(self, enabled):
        if enabled and self.loopback is None:
            from .music.windows import Loopback
            self.loopback = Loopback(self._publish)
            self.loopback.start()
        elif not enabled:
            self.close()

    def _publish(self, audio):
        self.audio = audio

    def level(self, now=None):
        value = self.audio.current(time.monotonic() if now is None else now)
        return value.level, value.status

    def close(self):
        if self.loopback is not None:
            self.loopback.close()
            if self.loopback.thread is not None and self.loopback.thread.is_alive():
                return False
            self.loopback = None
        return True

"""RIO implementation of the Fangcun host contract, including shared UI creation."""
from PySide6.QtCore import QObject,Signal,Property,Slot
from .ui import create_panel

class FangcunHost(QObject):
    changed=Signal()
    def __init__(self, bridge, engine):
        super().__init__();self.bridge=bridge;self.engine=engine;self._panels=[]
        bridge.changed.connect(self.changed)
    language=Property(str,lambda self:self.bridge.s.language,notify=changed)
    rotation=Property(int,lambda self:self.bridge.s.rotation,notify=changed)
    @property
    def enabled(self):return self.bridge.s.game_enabled
    @property
    def settings_window(self):return self.bridge.win
    @property
    def gourd_position(self):return self.bridge.s.gourd_x,self.bridge.s.gourd_y
    def set_enabled(self,value):
        if self.bridge.storage.snapshot()['busy']:return False
        self.bridge.applySettings(game_enabled=value)
        if value and self.bridge.storage.session.mode!='monitor':self.bridge.resumeMonitor()
        return True
    def show_settings(self):self.bridge.show()
    def save_gourd_position(self,x,y):self.bridge.applySettings(gourd_x=x,gourd_y=y)
    @Slot(str)
    def setLanguage(self,value):self.bridge.setLanguage(value)
    def create_window(self,source,properties,context):
        window,owner=create_panel(self.engine,source,properties,context)
        self._panels.append(owner);window.setIcon(self.bridge.app.windowIcon());return window
    def release_window(self,window):
        for owner in list(self._panels):
            if owner[0] is window:
                self._panels.remove(owner)
                for obj in owner:obj.deleteLater()
                return

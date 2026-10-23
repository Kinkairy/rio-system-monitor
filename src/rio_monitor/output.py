import queue,threading
from .protocol import FrameSender,ProtocolError,encode_rgb565
from .winusb import WinUSB
class ScreenOutput:
    """Latest-frame queue; never pile up or retry an uncertain USB operation."""
    def __init__(self,path):
        self.path=path;self.frames=queue.Queue(maxsize=1);self.stop=threading.Event()
        self.finished=threading.Event()
        self.error=None;self.sent=0;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    @property
    def needs_frame(self):
        return not self.stop.is_set() and not self.frames.full()
    def submit(self,image):
        if self.stop.is_set():return
        try:self.frames.get_nowait()
        except queue.Empty:pass
        try:self.frames.put_nowait(image.copy())
        except queue.Full:pass
    def run(self):
        transport=None
        try:
            transport=WinUSB(self.path);sender=FrameSender(transport);sender.lcd_info()
            while not self.stop.is_set():
                try:image=self.frames.get(timeout=.2)
                except queue.Empty:continue
                if image.size!=(480,480):raise ValueError('Expected a 480x480 frame')
                sender.send(encode_rgb565(image));self.sent+=1
        except Exception as exc:
            self.error=str(exc);self.stop.set()
            if transport and isinstance(exc,(OSError,ProtocolError)):
                try:transport.reset_pipes()
                except Exception as recovery:self.error+='; USB pipe reset failed: '+str(recovery)
        finally:
            try:
                if transport:transport.close()
            finally:self.finished.set()
    def close(self):
        self.stop.set();self.thread.join(timeout=5)
        return not self.thread.is_alive()

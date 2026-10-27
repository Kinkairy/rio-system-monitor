import queue,threading,time
from .protocol import FrameSender,ProtocolError,encode_rgb565
from .winusb import WinUSB
class ScreenOutput:
    """Latest-frame queue; never pile up or retry an uncertain USB operation."""
    frame_interval=1/12
    initialization_delay=1.0
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
            # OEM CD03 IN query selects the live session; allow firmware to settle.
            transport=WinUSB(self.path);sender=FrameSender(transport)
            sender.lcd_info()
            if self.stop.wait(self.initialization_delay):return
            next_send=0
            while not self.stop.is_set():
                # Pace complete frames; choose the newest queued image after waiting.
                if self.stop.wait(max(0,next_send-time.monotonic())):break
                try:image=self.frames.get(timeout=.2)
                except queue.Empty:continue
                if image.size!=(480,480):raise ValueError('Expected a 480x480 frame')
                pixels=encode_rgb565(image)
                next_send=time.monotonic()+self.frame_interval
                sender.send(pixels);self.sent+=1
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

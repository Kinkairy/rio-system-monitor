import io,queue,threading
from .protocol import FrameSender
from .winusb import WinUSB
class ScreenOutput:
    """Latest-frame queue; never pile up or retry an uncertain USB operation."""
    def __init__(self,path):
        self.path=path;self.frames=queue.Queue(maxsize=1);self.stop=threading.Event()
        self.error=None;self.sent=0;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def submit(self,image):
        if self.stop.is_set():return
        try:self.frames.get_nowait()
        except queue.Empty:pass
        try:self.frames.put_nowait(image.copy())
        except queue.Full:pass
    def run(self):
        transport=None
        try:
            transport=WinUSB(self.path);sender=FrameSender(transport)
            while not self.stop.is_set():
                try:image=self.frames.get(timeout=.2)
                except queue.Empty:continue
                stream=io.BytesIO();image.convert('RGB').save(stream,format='JPEG',quality=75)
                sender.send(stream.getvalue());self.sent+=1
        except Exception as exc:self.error=str(exc);self.stop.set()
        finally:
            if transport:transport.close()
    def close(self):
        self.stop.set();self.thread.join(timeout=5)
        return not self.thread.is_alive()

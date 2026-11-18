import logging,queue,threading,time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .protocol import FrameSender
from .display_protocols import create_protocol,LEGACY
from .winusb import WinUSB, device_arrival
logger=logging.getLogger('rio_monitor.usb')

def configure_usb_logging(folder):
    """Bounded, local diagnostics; logging availability must not stop the display."""
    try:
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=str((folder/'usb.log').resolve())
        if any(getattr(handler,'baseFilename',None)==path for handler in logger.handlers):return True
        handler=RotatingFileHandler(path,maxBytes=256*1024,backupCount=2,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler);logger.setLevel(logging.INFO);logger.propagate=False
        return True
    except OSError:return False

class ScreenOutput:
    """Latest-frame queue; never pile up or retry an uncertain USB operation."""
    # The hardware adapter owns pacing; legacy remains capped by its capability.
    frame_interval=0.0
    initialization_delay=None
    def __init__(self,path,driver=None):
        self.driver=driver or create_protocol(path,WinUSB,FrameSender)
        self.capabilities=self.driver.capabilities
        self.path=path;self.frames=queue.Queue(maxsize=1);self.stop=threading.Event()
        self.finished=threading.Event()
        self.error=None;self.sent=0;self.requires_replug=False;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    @property
    def needs_frame(self):
        # Keep replacing the single pending image while USB is busy. Otherwise
        # hidden-window animations send a stale frame after each slow ACK.
        return getattr(self,'capabilities',LEGACY).frames and not self.stop.is_set()
    def submit(self,image):
        if not getattr(self,'capabilities',LEGACY).frames:return
        self._submit(image.copy())
    def submit_samples(self,samples):
        if not getattr(self,'capabilities',LEGACY).samples:return
        self._submit(dict(samples))
    def _submit(self,content):
        if self.stop.is_set():return
        try:self.frames.get_nowait()
        except queue.Empty:pass
        try:self.frames.put_nowait(content)
        except queue.Full:pass
    def run(self):
        driver=getattr(self,'driver',None) or create_protocol(self.path,WinUSB,FrameSender)
        phase='open'
        try:
            # The adapter owns initialization; never bypass a failed handshake.
            driver.open(self.path)
            self.device_arrival = device_arrival(self.path)
            phase='initialization';driver.initialize()
            logger.info('Display initialized; protocol=%s', driver.capabilities.protocol)
            delay=driver.capabilities.startup_delay if self.initialization_delay is None else self.initialization_delay
            if delay and self.stop.wait(delay):return
            next_send=0
            while not self.stop.is_set():
                # Pace complete frames; choose the newest queued image after waiting.
                if self.stop.wait(max(0,next_send-time.monotonic())):break
                try:image=self.frames.get(timeout=.2)
                except queue.Empty:continue
                next_send=time.monotonic()+max(self.frame_interval,driver.capabilities.interval)
                phase='frame' if driver.capabilities.frames else 'samples'
                acknowledged=driver.send(image,cancelled=self.stop.is_set)
                if acknowledged:self.sent+=1
                if acknowledged and self.sent==1:logger.info('Display first %s update acknowledged; protocol=%s',phase,driver.capabilities.protocol)
        except Exception as exc:
            self.error=str(exc);self.stop.set()
            self.requires_replug=getattr(exc,'requires_replug',False)
            logger.warning('USB failure at %s after %d acknowledged frames; requires_replug=%s: %s',phase,self.sent,self.requires_replug,self.error)
            # Closing the handle is not a firmware reset. Keep late replies for
            # the next tagged query; resetting/flushing here loses framing.
        finally:
            try:
                driver.close()
            finally:self.finished.set()
    def close(self):
        self.stop.set();self.thread.join(timeout=8)
        return not self.thread.is_alive()

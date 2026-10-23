"""Single USB owner and explicit background preparation/resource replacement."""
from pathlib import Path
import tempfile, threading, time
from .media import prepare_media
from .resources import ResourceSender, validate_blob
from .stored_preview import StoredPreviewCache

class DisplaySession:
    def __init__(self,mode='monitor',enumerator=None,output_factory=None,transport_factory=None):
        self.mode=mode;self.lock=threading.RLock();self.output=None;self.retiring=None;self.error=None
        self.resource_active=False;self._enumerator=enumerator;self._output_factory=output_factory;self._transport_factory=transport_factory
        self.stop=threading.Event();self.thread=None;self.retry_at=0;self.retry_delay=1;self.connection_attempts=0
    def start(self):
        with self.lock:
            if self.stop.is_set():return
            if self.thread and self.thread.is_alive():return
            self.thread=threading.Thread(target=self.maintain,daemon=True,name='RIO-USB-reconnect');self.thread.start()
    def maintain(self):
        while not self.stop.is_set():
            self.reconnect()
            self.stop.wait(.2)
    def reconnect(self,now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            if self.stop.is_set() or self.mode!='monitor' or self.resource_active:return
            output=self.output
            if output and not output.error and not output.finished.is_set():
                if output.sent:self.retry_delay=1;self.retry_at=0
                return
            # The failed worker must finish freeing WinUSB before another handle opens.
            if output and not output.finished.is_set():return
            if self.retiring and not self.retiring.finished.is_set():return
            if now<self.retry_at:return
            self.connection_attempts+=1
            try:self.connect()
            except Exception as exc:self.error=str(exc)
            self.retry_at=now+self.retry_delay;self.retry_delay=min(5,self.retry_delay*2)
    def paths(self):
        if self._enumerator:return self._enumerator()
        from .winusb import enumerate_paths
        return enumerate_paths()
    def one_path(self):
        paths=self.paths()
        if len(paths)!=1:raise RuntimeError('Connect exactly one compatible screen / 请连接一块兼容圆屏')
        return paths[0]
    @property
    def live(self):
        with self.lock:return self.output is not None and not self.output.error
    def submit(self,frame):
        with self.lock:
            if self.output and not self.output.error:self.output.submit(frame)
    def connect(self):
        with self.lock:
            if self.stop.is_set():raise RuntimeError('Display session is closed')
            if self.resource_active:raise RuntimeError('Resource transfer is active')
            self.mode='monitor'  # Keep retrying if a requested live recovery finds no device yet.
            if self.retiring:
                if not self.retiring.close():raise RuntimeError('Previous USB writer has not stopped')
                self.retiring=None
            if self.output:
                if not self.output.close():raise RuntimeError('Previous USB writer has not stopped')
                self.output=None
            factory=self._output_factory
            if factory is None:
                from .output import ScreenOutput
                factory=ScreenOutput
            self.output=factory(self.one_path());self.mode='monitor';self.error=None
    def replace(self,blob,progress,before_erase=None):
        validate_blob(blob)
        with self.lock:
            if self.stop.is_set():raise RuntimeError('Display session is closed')
            if self.resource_active:raise RuntimeError('Another transfer is active')
            self.resource_active=True;self.mode='stored';self.retiring=self.output;self.output=None
        transport=None
        try:
            # Do not open a second handle until the frame worker has closed its handle.
            if self.retiring and not self.retiring.close():raise RuntimeError('USB writer could not stop; nothing erased')
            self.retiring=None
            factory=self._transport_factory
            if factory is None:
                from .winusb import WinUSB
                factory=WinUSB
            path=self.one_path();transport=factory(path);transport.set_timeout(3000)
            ResourceSender(transport).upload(blob,progress,lambda:before_erase(path) if before_erase else None)
            self.error=None
            return path
        except Exception as exc:
            self.error=str(exc);raise
        finally:
            if transport:transport.close()
            with self.lock:self.resource_active=False
    def close(self):
        with self.lock:
            if self.resource_active:return False
            self.stop.set();worker=self.thread
        if worker:
            worker.join(5)
            if worker.is_alive():return False
        with self.lock:
            for output in (self.output,self.retiring):
                if output and not output.close():return False
            self.output=self.retiring=None
            return True
    def snapshot(self):
        with self.lock:return dict(mode=self.mode,usb_sent=self.output.sent if self.output else 0,usb_error=self.error or (self.output.error if self.output else None),usb_connection_attempts=self.connection_attempts,usb_auto_reconnect=bool(self.thread and self.thread.is_alive() and self.mode=='monitor' and not self.stop.is_set()))

class StorageJob:
    def __init__(self,session,assets,cache_dir=None):
        self.session=session;self.assets=Path(assets);self.lock=threading.RLock()
        self.temp=tempfile.TemporaryDirectory(prefix='rio-media-',ignore_cleanup_errors=True)
        self.cancel=threading.Event();self.thread=None;self.serial=0;self.prepared=None
        self.cache=StoredPreviewCache(cache_dir) if cache_dir is not None else None
        self.state=dict(phase='idle',busy=False,writing=False,progress=0.0,name='',detail='',preview='',ready=False,error='',preview_cache_error='')
    def snapshot(self):
        with self.lock:return dict(self.state,mode=self.session.mode)
    def update(self,**values):
        with self.lock:self.state.update(values)
    @staticmethod
    def detail(media):
        return f'480 × 480 · {len(media.gif)/1_000_000:.2f} / 3.4 MB · {media.frames} frames'
    def open_preview(self):
        with self.lock:
            if self.state['busy']:return False
            self.prepared=None;stored=None
            if self.cache:
                try:stored=self.cache.load(self.session.one_path())
                except (OSError,RuntimeError,ValueError):pass
            self.update(ready=False,preview=str(stored.preview) if stored else '',
                        name=stored.name if stored else '',detail=self.detail(stored) if stored else '')
            return True
    def prepare(self,path,write_after=False):
        with self.lock:
            if self.state['busy']:return False
            self.prepared=None;self.serial+=1;self.cancel.clear()
            self.update(phase='prepare',busy=True,writing=False,ready=False,preview='',name=Path(path).name,detail='',error='',progress=0)
        def work():
            succeeded=False
            try:
                prepared=prepare_media(path,Path(self.temp.name)/str(self.serial),self.assets/'media/ffmpeg.exe',self.cancel.is_set)
                self.prepared=prepared
                self.update(phase='ready',ready=True,preview=str(prepared.preview),detail=self.detail(prepared))
                succeeded=True
            except InterruptedError:self.update(phase='idle',error='')
            except Exception as exc:self.update(phase='error',error=str(exc))
            finally:self.update(busy=False)
            if succeeded and write_after and not self.cancel.is_set():self.write()
        self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return True
    def write(self):
        with self.lock:
            if self.state['busy'] or not self.prepared or not self.state['ready']:return False
            prepared=self.prepared;previous_mode=self.session.mode;self.update(phase='connecting',busy=True,writing=True,ready=False,progress=0,error='',preview_cache_error='')
        def progress(phase,done,total):self.update(phase=phase,progress=done/total)
        def work():
            try:
                if self.cache:
                    device=self.session.replace(prepared.blob,progress,before_erase=self.cache.invalidate)
                else:self.session.replace(prepared.blob,progress)
            except Exception as exc:
                error=str(exc)
                if previous_mode=='monitor':
                    try:self.session.connect()
                    except Exception as recovery:error+='; real-time recovery failed: '+str(recovery)
                self.update(phase='error',error=error)
            else:
                if self.cache:
                    try:self.cache.store(device,prepared)
                    except OSError as exc:self.update(preview_cache_error=str(exc))
                self.update(phase='stored',progress=1)
            finally:self.update(busy=False,writing=False)
        self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return True
    def resume(self):
        with self.lock:
            if self.state['busy']:return False
            self.update(busy=True,phase='connecting',error='')
        def work():
            try:self.session.connect();self.update(phase='live',ready=bool(self.prepared))
            except Exception as exc:self.update(phase='error',error=str(exc))
            finally:self.update(busy=False)
        self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return True
    def close(self):
        if self.snapshot()['writing']:return False
        self.cancel.set()
        if self.thread:self.thread.join(2)
        if self.thread and self.thread.is_alive():return False
        self.temp.cleanup();return True

"""Identify supported factory screens and install the bundled RIO firmware."""
import datetime,hashlib,json,os,sys,threading,time
from pathlib import Path
from . import firmware_segments as segments
from . import firmware_animation, firmware_release
from .t113_display import WAVESHARE_FIRMWARE, install_firmware, is_t113_update_path, read_firmware_package

PLAN_SHA='a077ac68c9fd06f003ef6b513c038f35c6cc1a8003fcb8c0fa6869b950a2e40a'
IMAGE_SHA='30780997a3baf2d0002462443c3922f4d54997f1b6e7929c8e80b15a15883a9a'

def save_journal(path,journal):
    temp=path.with_name(path.name+'.new')
    with temp.open('w',encoding='utf-8') as log:
        json.dump(journal,log,indent=2)
        log.flush()
        os.fsync(log.fileno())
    os.replace(temp,path)

def run_segments(port,package,install,journal,record,progress=lambda value:None):
    device=segments.RioLoader(port)
    journal['transport']=device.counts
    return segments.update(device,package,install,record,progress)

def load_plan(folder):
    raw=(Path(folder)/'em133-v3-rio1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PLAN_SHA:raise ValueError('Firmware package checksum mismatch')
    plan=json.loads(raw)
    if plan['image_sha256']!=IMAGE_SHA or plan['length']!=12288:raise ValueError('Wrong firmware profile')
    return plan

def stock_paths():
    # Descriptor evidence from the actual original screen. This is a candidate
    # match only: exact application/guard CRCs are verified in boot mode.
    import hid
    expected=dict(vendor_id=0xeeef,product_id=0x1616,manufacturer_string='LEVETOP',
                  product_string='USB-HID',release_number=0x100,usage_page=1,usage=0,interface_number=0)
    return [d['path'].decode() if isinstance(d['path'],bytes) else d['path']
            for d in hid.enumerate(0xeeef,0x1616) if all(d.get(k)==v for k,v in expected.items())]

def _windows_boot_port(api=None, registry=None):
    # pyserial 3.5 drops serials containing '.' on Windows. Resolve the exact
    # PRESENT instance instead; a cached registry key alone is not evidence.
    if sys.platform!='win32':return None
    import ctypes,re
    if registry is None:import winreg as registry
    if api is None:api=ctypes.WinDLL('cfgmgr32',use_last_error=True)
    word=ctypes.c_uint32
    api.CM_Locate_DevNodeW.argtypes=[ctypes.POINTER(word),ctypes.c_wchar_p,word]
    api.CM_Locate_DevNodeW.restype=word
    api.CM_Get_DevNode_Status.argtypes=[ctypes.POINTER(word),ctypes.POINTER(word),word,word]
    api.CM_Get_DevNode_Status.restype=word
    instance=r'USB\VID_EEEF&PID_268A\TEST_1.0'
    node=word();result=api.CM_Locate_DevNodeW(ctypes.byref(node),instance,0)
    if result==0x0d:return None  # CR_NO_SUCH_DEVNODE; never request PHANTOM.
    if result:raise OSError('Boot instance lookup failed: %d'%result)
    status=word();problem=word()
    result=api.CM_Get_DevNode_Status(ctypes.byref(status),ctypes.byref(problem),node,0)
    if result==0x0d:return None
    if result:raise OSError('Boot instance status failed: %d'%result)
    if not status.value&8 or status.value&0x400:return None  # DN_STARTED/HAS_PROBLEM
    try:
        with registry.OpenKey(registry.HKEY_LOCAL_MACHINE,
                '\\'.join(('SYSTEM','CurrentControlSet','Enum',instance,'Device Parameters'))) as key:
            port,kind=registry.QueryValueEx(key,'PortName')
    except FileNotFoundError:return None
    return port if kind==registry.REG_SZ and isinstance(port,str) and re.fullmatch(r'COM[1-9][0-9]*',port) else None

def boot_ports():
    from serial.tools.list_ports import comports
    ports=[p for p in comports() if (p.vid,p.pid)==(0xeeef,0x268a)]
    exact=_windows_boot_port() if any(not p.serial_number for p in ports) else None
    return sorted({p.device for p in ports if p.serial_number=='TEST_1.0' or
                   (not p.serial_number and exact is not None and p.device==exact)})

def open_port(name):
    import serial
    port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=5)
    port.dtr=False;port.rts=False;port.port=name;port.open()
    return port

def program(port,plan,record=lambda item:None,progress=lambda value:None,cancelled=lambda:False):
    """No retries, no rollback, no implicit reset. Run only after both CRCs pass."""
    requests=[plan['requests'][0],*plan['preflight_requests'],*plan['requests'][1:]]
    for index,q in enumerate(requests):
        # Before programming mode, cancellation cannot interrupt a flash write.
        if index<=3 and cancelled():raise RuntimeError('Upgrade cancelled before writing')
        if port.in_waiting:raise OSError('Unexpected pending bootloader input')
        payload=bytes.fromhex(q['tx'])
        record(dict(name=q['name'],state='sending',tx=q['tx']))
        if port.write(payload)!=len(payload):raise OSError('Short bootloader write; not retried')
        if q['name']=='run_application':
            record(dict(name=q['name'],state='run_sent'));progress(1.0);return
        data=bytearray();deadline=time.monotonic()+10
        while len(data)<63 and time.monotonic()<deadline:
            data.extend(port.read(63-len(data)))
        record(dict(name=q['name'],state='received',rx=bytes(data).hex()))
        if len(data)!=63 or data[0]!=q['expect']:raise OSError('Invalid loader reply: '+q['name'])
        word=lambda offset:int.from_bytes(data[offset:offset+4],'little')
        if q['expect']==0x4b and (word(1),word(5),word(9),word(13))!=(q['identity_crc'],q['echo_crc'],plan['boot_version'],plan['boot_kind']):
            raise OSError('Bootloader identity mismatch')
        if q['expect'] in (0x4a,0x4c) and data[1]!=0:raise OSError('Loader rejected '+q['name'])
        if q['expect']==0x4a and word(2)!=q['offset']:raise OSError('Wrong write offset reply')
        if q['expect']==0x4e and (word(1),word(5))!=(q['crc'],q['length']):
            raise OSError('Firmware compatibility/CRC mismatch: '+q['name'])
        record(dict(name=q['name'],state='validated'))
        progress((index+1)/len(requests))
    raise OSError('Missing verified application start')

class FirmwareUpdate:
    def __init__(self,session,folder,log_folder,ports=boot_ports,opener=open_port,detector=stock_paths):
        self.session=session;self.folder=Path(folder);self.logs=Path(log_folder)
        self.ports=ports;self.opener=opener;self.detector=detector;self.lock=threading.RLock()
        self.thread=None;self.cancel_event=threading.Event()
        self.watcher=None
        self.watch_stop=threading.Event()
        self.last_stock=None
        self.last_boot=None
        self.last_waveshare=None
        self.waveshare_package=self.folder/WAVESHARE_FIRMWARE
        self.segment_package=None
        self.data=dict(state='idle',progress=0.,error='',busy=False,segmented=False)
    def snapshot(self):
        with self.lock:return dict(self.data)
    def update(self,**values):
        with self.lock:self.data.update(values)
    def start_watching(self):
        if self.watcher is not None or not any(path.is_file() for path in
                (self.folder/firmware_release.FILENAME, self.waveshare_package)):
            return
        self.watcher=threading.Thread(target=self._watch,daemon=True,name='RIO-firmware-detect')
        self.watcher.start()

    def _watch(self):
        while not self.watch_stop.is_set():
            try:
                self.detect()
            except (ImportError,OSError,ValueError,RuntimeError):
                # Temporary absence or a device in transition is retried by discovery.
                pass
            self.watch_stop.wait(1)

    def detect(self):
        if self.snapshot()['busy'] or self.watch_stop.is_set():
            return False
        with self.session.lock:
            if self.session.resource_active or self.session.mode=='firmware' or self.session.stop.is_set():
                return False
            output=self.session.output
            generation=self.session.attachment_generation
            if output is not None and not output.error:
                if is_t113_update_path(output.path):
                    return bool(output.sent) and self._start_waveshare(output.path, generation)
                self.last_waveshare=None
                if output.capabilities.protocol!='levetop-emonitor' or not output.sent:
                    self.last_boot=None
                    return False
                path=output.path
            else:
                path=None
        boot_present=False
        if path is not None:
            token=(generation,path)
            if self.last_stock==token:
                return False
            if self.detector()!=[path] or self.session.paths()!=[path]:
                return False
            self.last_stock=token
            self.last_boot=None
        else:
            paths=self.session.paths()
            if len(paths)==1 and is_t113_update_path(paths[0]):
                if self.session.mode=='stored':
                    return self._start_waveshare(paths[0], generation)
                return False  # Wait for the first acknowledged live frame.
            if not paths:
                self.last_waveshare=None
            if paths:
                # A screen being opened by the monitor worker has not completed its handshake yet.
                if self.session.mode!='stored' or len(paths)!=1 or self.detector()!=paths:
                    return False
                token=(generation,paths[0])
                if self.last_stock==token:return False
                self.last_stock=token
                self.last_boot=None
            else:
                self.last_stock=None
                ports=self.ports()
                if not ports:
                    self.last_boot=None
                    return False
                if len(ports)!=1 or ports[0]==self.last_boot:return False
                self.last_boot=ports[0]
                boot_present=True
        try:
            self.select_bundled()
        except (OSError,ValueError) as exc:
            self.update(state='error',error=str(exc))
            return False
        return self.start(automatic=True,boot_present=boot_present)

    def dismiss(self):
        with self.lock:
            if self.data['state']=='waiting':self.cancel_event.set()
            elif not self.data['busy']:
                self.segment_package=None;self.update(state='idle',segmented=False)
    def select_package(self,path):
        self._select(firmware_release.selected(path,self.folder))
    def select_bundled(self):
        self._select(firmware_release.bundled(self.folder))
    def _select(self,package):
        with self.lock:
            if self.data['busy']:raise RuntimeError('An upgrade is already active')
            self.segment_package=package
            self.update(state='available',progress=0.,error='',segmented=True)
    def start(self,automatic=False,boot_present=False):
        with self.lock:
            if self.watch_stop.is_set() or self.data['busy'] or self.data['state']!='available':return False
            self.data.update(state='checking' if boot_present else 'waiting',progress=0.,error='',busy=True)
            self.cancel_event.clear()
            self.thread=threading.Thread(target=self._run,args=(automatic,),daemon=True,name='RIO-firmware-update')
            self.thread.start();return True
    def _start_waveshare(self, path, generation):
        token=(generation,path)
        with self.lock:
            if self.watch_stop.is_set() or self.data['busy'] or token==self.last_waveshare:
                return False
            if not self.waveshare_package.is_file() or self.session.paths()!=[path]:
                return False
            self.last_waveshare=token
            self.data.update(state='checking',progress=0.,error='',busy=True,segmented=False)
            self.thread=threading.Thread(target=self._run_waveshare,args=(path,generation),daemon=True,
                                         name='RIO-Waveshare-update')
            self.thread.start()
            return True

    def _run_waveshare(self, path, generation):
        previous=None
        log=None
        journal={}
        try:
            package=read_firmware_package(self.waveshare_package)
            with self.session.lock:
                if (self.session.resource_active or self.session.stop.is_set() or self.session.mode=='firmware'
                        or generation!=self.session.attachment_generation or self.session.paths()!=[path]):
                    self.last_waveshare=None
                    self.update(state='idle')
                    return
                for output in (self.session.retiring,self.session.output):
                    if output and not output.close():
                        raise RuntimeError('Display writer did not stop / 实时发送未停止')
                self.session.output=self.session.retiring=None
                previous=self.session.mode
                self.session.mode='firmware'
            self.logs.mkdir(parents=True,exist_ok=True)
            log=self.logs/('waveshare-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            journal.update(port=path,trigger='automatic',package_sha256=hashlib.sha256(package[0]).hexdigest())
            result=install_firmware(path,package,self.session.paths,
                                    lambda value:self.update(state='writing',progress=value))
            journal.update(result)
            if result.get('skipped'):
                self.update(state='skipped')
            else:
                self.update(state='current' if result['already_current'] else 'done',progress=1.)
        except Exception as exc:
            journal['error']=str(exc)
            self.update(state='error',error=str(exc))
        finally:
            if log:
                try:save_journal(log,journal)
                except OSError:pass
            if previous is not None:
                with self.session.lock:
                    self.session.mode=previous
                    self.session.retry_at=0
            self.update(busy=False)

    def _run(self,automatic=False):
        port=None;owned=False;path=None;journal=dict(events=[],error=None)
        try:
            package=self.segment_package
            plan=None if package else load_plan(self.folder)
            # Freeze the same session owner before any bootloader handle opens.
            with self.session.lock:
                if self.session.resource_active or self.session.stop.is_set():raise RuntimeError('Display is busy or closing')
                if self.session.retiring and not self.session.retiring.close():raise RuntimeError('Previous display worker did not stop')
                if self.session.output and not self.session.output.close():raise RuntimeError('Display worker did not stop')
                self.session.output=self.session.retiring=None
                self.session.mode='firmware';owned=True
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if self.cancel_event.is_set():self.update(state='cancelled');return
                ports=self.ports()
                if len(ports)>1:raise RuntimeError('Connect only one upgrade-mode screen')
                if ports:
                    if self.session.paths():raise RuntimeError('Disconnect other screens before firmware update')
                    break
                self.cancel_event.wait(.5)
            else:raise TimeoutError('Upgrade mode not detected within 3 minutes; nothing written')
            if self.cancel_event.is_set():self.update(state='cancelled');return
            self.logs.mkdir(parents=True,exist_ok=True)
            path=self.logs/('em133-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            journal['port']=ports[0]
            if package:journal.update(package.describe())
            else:journal.update(plan_sha256=PLAN_SHA,image_sha256=IMAGE_SHA)
            def record(item):
                journal['events'].append(item)
                save_journal(path,journal)
            if automatic:self.last_boot=ports[0]
            port=self.opener(ports[0])
            # Disable cancellation/exit before the bounded handshake+write phase.
            with self.lock:
                if self.cancel_event.is_set():self.update(state='cancelled');return
                self.update(state='writing')
            if isinstance(package,firmware_release.Release):
                io=firmware_animation.Connections(self.ports,self.opener,self.session.paths)
                journal['result']=firmware_animation.run(
                    port,package,self.logs/'backups',True,record,
                    lambda state,p:self.update(state=state,progress=p),io,factory_only=automatic)
            elif package:
                journal['result']=run_segments(port,package,True,journal,record,lambda p:self.update(progress=p))
            else:program(port,plan,record,lambda p:self.update(progress=p))
            self.update(state='current' if journal.get('result') in ('already_installed_and_verified','rio_firmware_present','unrecognized_firmware') else 'done',progress=1.)
        except segments.EraseScopeUnknown as exc:
            journal.update(error=str(exc),result='erase_scope_unproven');self.update(state='scope_unknown',error='')
        except Exception as exc:
            journal['error']=str(exc);self.update(state='error',error=str(exc))
        finally:
            if port:
                try:port.close()
                except OSError as exc:
                    journal['error']=str(exc);self.update(state='error',error=str(exc))
            if path:
                try:save_journal(path,journal)
                except OSError:pass
            if owned:
                with self.session.lock:
                    self.session.mode='monitor';self.session.retry_at=0
            self.update(busy=False)
    def close(self):
        with self.lock:
            if self.data['state']=='writing' or self.data['busy'] and self.data['state']!='waiting':return False
            self.watch_stop.set()
            self.cancel_event.set()
        if self.watcher:self.watcher.join(2)
        if self.thread:self.thread.join(2)
        return not (self.watcher and self.watcher.is_alive() or self.thread and self.thread.is_alive())

def main(argv=None):
    import argparse
    from .settings import acquire_instance
    from .display_protocols import enumerate_paths
    p=argparse.ArgumentParser(description='Manual eM133-V3 upgrade. Close RIO; hold bottom button while reconnecting USB, release after 3 seconds.')
    p.add_argument('--firmware-dir',type=Path,default=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'firmware')
    p.add_argument('--write-em133-v3',action='store_true',help='Explicitly authorize one 12 KiB write after original-firmware checks')
    source=p.add_mutually_exclusive_group()
    source.add_argument('--segmented-package',type=Path,help='A RIO release ZIP; preview offline by default')
    source.add_argument('--bundled-animation',action='store_true',help='Use the startup firmware built into RIO')
    action=p.add_mutually_exclusive_group()
    action.add_argument('--check-segments',action='store_true',help='Read physical checksums, then return to the current application')
    action.add_argument('--install-segments',action='store_true',help='Install only if all required erase windows are physically qualified')
    p.add_argument('--journal',type=Path,required=True)
    args=p.parse_args(argv)
    if ((args.check_segments or args.install_segments) and not (args.segmented_package or args.bundled_animation)
            or args.write_em133_v3 and (args.segmented_package or args.bundled_animation)):
        p.error('Select exactly one firmware workflow')
    try:
        with args.journal.open('x') as reservation:reservation.write('{}')
    except FileExistsError:
        raise SystemExit('Journal exists; do not replay a consumed attempt')
    journal=dict(events=[],error=None,write_requested=args.write_em133_v3,plan_sha256=PLAN_SHA)
    def record(item):
        journal['events'].append(item);save_journal(args.journal,journal)
    try:
        package=None
        built_in=(args.firmware_dir/firmware_release.FILENAME).is_file()
        if args.bundled_animation or args.write_em133_v3 and built_in:
            package=firmware_release.bundled(args.firmware_dir)
        elif args.segmented_package:
            package=firmware_release.selected(args.segmented_package,args.firmware_dir)
        if package is not None:
            journal.pop('plan_sha256')
            journal.update(package.describe(),write_requested=args.install_segments or args.write_em133_v3)
            if not (args.check_segments or journal['write_requested']):
                journal['result']='package_verified_offline'
                return 0
        # The exact same process mutex prevents an independent manual writer
        # competing with the running main application.
        instance=acquire_instance()
        if instance is None:raise RuntimeError('Close RIO before using the manual firmware tool')
        plan=None if package is not None else load_plan(args.firmware_dir)
        ports=boot_ports()
        if len(ports)!=1 or enumerate_paths():raise RuntimeError('Connect only one screen, already in upgrade mode')
        journal['port']=ports[0]
        if isinstance(package,firmware_release.Release):
            io=firmware_animation.Connections(boot_ports,open_port,enumerate_paths)
            from .settings import config_path
            backups=config_path().parent/'firmware-logs'/'backups'
            with open_port(ports[0]) as port:
                journal['result']=firmware_animation.run(port,package,backups,journal['write_requested'],
                                                         record,lambda state,p:None,io)
        elif args.segmented_package:
            with open_port(ports[0]) as port:
                journal['result']=run_segments(port,package,args.install_segments,journal,record)
        elif args.write_em133_v3:
            with open_port(ports[0]) as port:program(port,plan,record)
            journal['result']='verified_and_started'
        else:journal['result']='preview_only_no_device_commands'
    except segments.EraseScopeUnknown as exc:
        journal.update(error=str(exc),result='erase_scope_unproven')
    except Exception as exc:
        journal['error']=str(exc);journal['result']='stopped'
    finally:save_journal(args.journal,journal)
    return 1 if journal['error'] else 0

if __name__=='__main__':raise SystemExit(main())

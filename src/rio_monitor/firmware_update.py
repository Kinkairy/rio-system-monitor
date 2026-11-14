"""One explicit eM133-V3 upgrade, shared by the settings guide and manual CLI.

Firmware is an external, SHA-pinned build input. Discovery never arms writing.
The original loader/profile must match before any programming-mode command.
"""
import datetime,hashlib,json,sys,threading,time
from pathlib import Path

PLAN_SHA='a077ac68c9fd06f003ef6b513c038f35c6cc1a8003fcb8c0fa6869b950a2e40a'
IMAGE_SHA='30780997a3baf2d0002462443c3922f4d54997f1b6e7929c8e80b15a15883a9a'

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
        self.thread=None;self.cancel_event=threading.Event();self.offered=False;self.offered_generation=None
        self.data=dict(state='idle',progress=0.,error='',busy=False)
    def snapshot(self):
        with self.lock:return dict(self.data)
    def update(self,**values):
        with self.lock:self.data.update(values)
    def offer(self,protocol):
        generation=self.session.attachment_generation
        if self.offered_generation!=generation:self.offered=False
        if protocol=='levetop-emonitor' and not self.offered and self.snapshot()['state']=='idle':
            try:
                output=self.session.output
                if output is None or output.path not in self.detector():return False
            except (ImportError,OSError):return False
            self.offered=True;self.offered_generation=generation;self.update(state='available');return True
        return False
    def dismiss(self):
        with self.lock:
            if self.data['state']=='waiting':self.cancel_event.set()
            elif not self.data['busy']:self.update(state='idle')
    def start(self):
        with self.lock:
            if self.data['busy'] or self.data['state']!='available':return False
            self.data.update(state='waiting',progress=0.,error='',busy=True)
            self.cancel_event.clear()
            self.thread=threading.Thread(target=self._run,daemon=True,name='RIO-firmware-update')
            self.thread.start();return True
    def _run(self):
        port=None;owned=False;path=None;journal=dict(events=[],error=None)
        try:
            plan=load_plan(self.folder)
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
            journal.update(plan_sha256=PLAN_SHA,image_sha256=IMAGE_SHA,port=ports[0])
            def record(item):
                journal['events'].append(item)
                path.write_text(json.dumps(journal,indent=2))
            port=self.opener(ports[0])
            # Disable cancellation/exit before the bounded handshake+write phase.
            with self.lock:
                if self.cancel_event.is_set():self.update(state='cancelled');return
                self.update(state='writing')
            program(port,plan,record,lambda p:self.update(progress=p))
            self.update(state='done')
        except Exception as exc:
            journal['error']=str(exc);self.update(state='error',error=str(exc))
        finally:
            if port:
                try:port.close()
                except OSError as exc:
                    journal['error']=str(exc);self.update(state='error',error=str(exc))
            if path:
                try:path.write_text(json.dumps(journal,indent=2))
                except OSError:pass
            if owned:
                with self.session.lock:
                    self.session.mode='monitor';self.session.retry_at=0
            self.update(busy=False)
    def close(self):
        with self.lock:
            if self.data['state']=='writing':return False
            self.cancel_event.set()
        if self.thread:self.thread.join(2)
        return not self.thread or not self.thread.is_alive()

def main(argv=None):
    import argparse
    from .settings import acquire_instance
    from .display_protocols import enumerate_paths
    p=argparse.ArgumentParser(description='Manual eM133-V3 upgrade. Close RIO; hold bottom button while reconnecting USB, release after 3 seconds.')
    p.add_argument('--firmware-dir',type=Path,default=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'firmware')
    p.add_argument('--write-em133-v3',action='store_true',help='Explicitly authorize one 12 KiB write after original-firmware checks')
    p.add_argument('--journal',type=Path,required=True)
    args=p.parse_args(argv)
    if args.journal.exists():raise SystemExit('Journal exists; do not replay a consumed attempt')
    journal=dict(events=[],error=None,write_requested=args.write_em133_v3,plan_sha256=PLAN_SHA)
    def record(item):
        journal['events'].append(item);args.journal.write_text(json.dumps(journal,indent=2))
    try:
        # The exact same process mutex prevents an independent manual writer
        # competing with the running main application.
        instance=acquire_instance()
        if instance is None:raise RuntimeError('Close RIO before using the manual firmware tool')
        plan=load_plan(args.firmware_dir);ports=boot_ports()
        if len(ports)!=1 or enumerate_paths():raise RuntimeError('Connect only one screen, already in upgrade mode')
        journal['port']=ports[0]
        if args.write_em133_v3:
            with open_port(ports[0]) as port:program(port,plan,record)
            journal['result']='verified_and_started'
        else:journal['result']='preview_only_no_device_commands'
    except Exception as exc:
        journal['error']=str(exc);journal['result']='stopped'
    finally:args.journal.write_text(json.dumps(journal,indent=2))
    return 1 if journal['error'] else 0

if __name__=='__main__':raise SystemExit(main())

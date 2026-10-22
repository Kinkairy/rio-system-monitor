"""Unprivileged sensor discovery and explicit one-time temperature installation.

Startup never requests elevation. The elevated helper installs a protected service;
ordinary reads and the on/off control use separate ProgramData directories.
"""
import ctypes,json,math,os,subprocess,threading,time
from pathlib import Path

SERVICE='RIOHardwareMonitor'

def data_dir():return Path(os.environ.get('PROGRAMDATA',r'C:\ProgramData'))/'RIO-Monitor'

def service_installed():
    if os.name!='nt':return False
    import winreg
    expected=Path(os.environ.get('ProgramW6432',os.environ.get('PROGRAMFILES',r'C:\Program Files')))/'RIO-Monitor'/'Temperature'/'RIO-Temperature.exe'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Services'+'\\'+SERVICE) as key:
            command=winreg.QueryValueEx(key,'ImagePath')[0]
        return command.casefold()==('"'+str(expected)+'" --service').casefold()
    except OSError:return False

def valid_temperature(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<=125

def read_status(path=None,now=None):
    try:
        path=path or data_dir()/'State'/'sensors.json'
        if path.stat().st_size>4096:return None
        row=json.loads(path.read_text(encoding='utf-8-sig'))
        stamp=row.get('timestamp');now=time.time() if now is None else now
        if row.get('version')!=1 or not isinstance(stamp,(int,float)) or isinstance(stamp,bool) or not math.isfinite(stamp) or not 0<=now-stamp<=5:return None
        if row.get('status') not in ('ready','disabled','unsupported','error','stopped'):return None
        if not valid_temperature(row.get('cpu_temperature')):row['cpu_temperature']=None
        return row
    except (OSError,ValueError,TypeError,AttributeError):return None

def write_enabled(enabled):
    # Never create installation directories or change their ACLs as the GUI user.
    path=data_dir()/'Control'/'enabled.json'
    tmp=path.with_name('enabled-'+__import__('uuid').uuid4().hex+'.tmp')
    try:
        with tmp.open('x',encoding='utf-8') as file:json.dump({'enabled':bool(enabled)},file)
        tmp.replace(path)
    finally:
        try:tmp.unlink(missing_ok=True)
        except OSError:pass

def start_existing_service():
    try:
        executable=Path(os.environ.get('SYSTEMROOT',r'C:\Windows'))/'System32'/'sc.exe'
        result=subprocess.run([str(executable),'start',SERVICE],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.returncode in (0,1056)
    except (OSError,subprocess.TimeoutExpired):return False

def elevate_helper(helper,stop,operation):
    """Only called in response to the user's temperature-toggle action."""
    from ctypes import wintypes as w
    class Execute(ctypes.Structure):
        _fields_=[('cbSize',w.DWORD),('fMask',w.ULONG),('hwnd',w.HWND),('lpVerb',w.LPCWSTR),('lpFile',w.LPCWSTR),('lpParameters',w.LPCWSTR),('lpDirectory',w.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',w.HINSTANCE),('lpIDList',ctypes.c_void_p),('lpClass',w.LPCWSTR),('hkeyClass',w.HKEY),('dwHotKey',w.DWORD),('hIcon',w.HANDLE),('hProcess',w.HANDLE)]
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(Execute)];shell.ShellExecuteExW.restype=w.BOOL
    kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)];kernel.CloseHandle.argtypes=[w.HANDLE]
    if operation not in ('install','uninstall'):raise ValueError('Unsupported component operation')
    request=Execute();request.cbSize=ctypes.sizeof(request);request.fMask=0x40|0x100;request.lpVerb='runas';request.lpFile=str(helper);request.lpParameters='--'+operation;request.lpDirectory=str(helper.parent);request.nShow=0
    if not shell.ShellExecuteExW(ctypes.byref(request)):
        error=ctypes.get_last_error()
        if error==1223:return 'cancelled'
        raise ctypes.WinError(error)
    try:
        deadline=time.monotonic()+300
        while not stop.is_set() and time.monotonic()<deadline:
            result=kernel.WaitForSingleObject(request.hProcess,250)
            if result==0:
                code=w.DWORD()
                if not kernel.GetExitCodeProcess(request.hProcess,ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
                return 'reboot' if code.value==3010 else (('uninstalled' if operation=='uninstall' else 'installed') if code.value==0 else 'failed')
            if result!=258:raise ctypes.WinError(ctypes.get_last_error())
        return 'pending'  # Do not terminate an elevated installer when the GUI exits.
    finally:kernel.CloseHandle(request.hProcess)

def elevate_install(helper,stop):return elevate_helper(helper,stop,'install')
def elevate_uninstall(helper,stop):return elevate_helper(helper,stop,'uninstall')

class TemperatureComponent:
    def __init__(self,assets,enabled=True,start=True,installer=elevate_install,uninstaller=elevate_uninstall):
        self.helper=Path(assets)/'temperature'/'RIO-Temperature.exe';self.enabled=enabled;self.installer=installer
        self.lock=threading.RLock();self.stop=threading.Event();self.wake=threading.Event();self.thread=None;self.process=None
        self.value=None;self.source='unavailable';self.stamp=0.;self.native_value=None;self.native_stamp=0.;self.installed=False;self.state='detecting';self.busy=False;self.install_requested=False;self.failure=None;self.reboot=False;self.command_until=0.
        self.uninstaller=uninstaller;self.uninstall_requested=False;self.operation='installing';self.external=False;self.removed=False;self.remove_reboot=False
        if start:self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
        else:self.state='missing'
    def note_native(self,value):
        if valid_temperature(value):
            with self.lock:self.native_value=value;self.native_stamp=time.monotonic()
    def temperature(self):
        with self.lock:
            if not self.enabled:return None
            return self.value if time.monotonic()-self.stamp<=5 and valid_temperature(self.value) else None
    def snapshot(self):
        with self.lock:
            return dict(enabled=self.enabled,checked=self.enabled and (self.busy or self.installed or self.state=='existing'),busy=self.busy,state=self.operation if self.busy else self.state,installed=self.installed,external=self.external)
    def request(self,enabled):
        with self.lock:
            if self.busy or self.external:return
            self.failure=None
            previous=self.enabled
            try:
                if self.installed:write_enabled(enabled)
            except OSError:
                self.state='error';self.failure='error';self.enabled=previous;return
            self.enabled=enabled
            if enabled:self.remove_reboot=False
            self.command_until=time.monotonic()+3
            if not enabled and self.installed:
                self.busy=True;self.uninstall_requested=True;self.operation='uninstalling';self.state='uninstalling';self.value=None
                self.wake.set();return
            if enabled and not (self.installed and read_status()) and self.state not in ('existing','ready','unsupported'):
                self.busy=True;self.install_requested=True;self.state='installing';self.operation='installing';self.removed=False
            elif enabled:self.state='starting' if self.installed else 'existing'
            elif not enabled:self.state='off';self.value=None
        self.wake.set()
    def probe_existing(self):
        if not self.helper.is_file():return None
        try:
            self.process=subprocess.Popen([str(self.helper),'--probe-existing'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            data=self.process.communicate(timeout=6)[0]
            if len(data)>4096:return None
            row=json.loads(data)
            return row if valid_temperature(row.get('cpu_temperature')) else None
        except (OSError,ValueError,subprocess.TimeoutExpired):
            if self.process and self.process.poll() is None:self.process.kill();self.process.wait(timeout=1)
            return None
        finally:self.process=None
    def poll(self):
        installed=service_installed();row=read_status() if installed else None
        with self.lock:
            self.installed=installed
            if self.remove_reboot:self.state='uninstall_reboot';return
            if self.reboot:self.state='reboot';return
            if not self.enabled and installed:self.value=None;self.state=self.failure or 'off';self.external=False;return
            if row and row['status']=='disabled':
                self.value=None
                if time.monotonic()<self.command_until:self.state='starting'
                else:self.enabled=False;self.state='off'
                return
            if row and row['status'] in ('ready','unsupported','error'):
                self.value=row['cpu_temperature'];self.stamp=time.monotonic();self.source=row.get('source','RIO service');self.state=row['status'];self.external=False;return
            if valid_temperature(self.native_value) and time.monotonic()-self.native_stamp<=5:
                self.value=self.native_value;self.stamp=time.monotonic();self.source='Windows CPU thermal zone';self.state='existing';self.external=not installed;self.enabled=True;return
        existing=self.probe_existing()
        with self.lock:
            if existing:self.value=existing['cpu_temperature'];self.source=str(existing['source']);self.stamp=time.monotonic();self.state='existing';self.external=not installed;self.enabled=True
            else:self.value=None;self.external=False;self.state=(self.failure or ('removed' if self.removed else 'off')) if not self.enabled else ('error' if installed else 'missing')
    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock:install=self.install_requested;remove=self.uninstall_requested;self.install_requested=False;self.uninstall_requested=False
            if remove:
                try:result=self.uninstaller(self.helper,self.stop)
                except OSError:result='failed'
                with self.lock:
                    self.busy=False;self.installed=service_installed();self.value=None
                    self.removed=result in ('uninstalled','reboot') and not self.installed
                    self.remove_reboot=result=='reboot'
                    self.enabled=self.installed if result not in ('uninstalled','reboot') else False
                    self.failure=None if self.removed else ('cancelled' if result=='cancelled' else 'error')
                    self.state='uninstall_reboot' if result=='reboot' else ('removed' if self.removed else self.failure)
                    if self.enabled:
                        try:write_enabled(True)
                        except OSError:self.failure='error';self.state='error'
                self.wake.wait(1);continue
            if install:
                # Discovery is repeated at the explicit action, avoiding installation
                # when another monitor has just exposed a usable existing interface.
                if self.installed and start_existing_service():self.stop.wait(1)
                self.poll()
                try:result='installed' if self.state in ('existing','ready','unsupported') else self.installer(self.helper,self.stop)
                except OSError:result='failed'
                with self.lock:
                    self.busy=False;self.installed=service_installed();self.reboot=result=='reboot'
                    if result not in ('installed','reboot'):self.enabled=False;self.failure='cancelled' if result=='cancelled' else 'error';self.state=self.failure
                if result=='installed':self.stop.wait(1)
            if not install or result in ('installed','reboot'):self.poll()
            self.wake.wait(1)
    def close(self):
        self.stop.set();self.wake.set()
        process=self.process
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
        if self.thread:self.thread.join(timeout=1)

"""Windows WinUSB adapter. Explicit open only. No driver install or flash commands."""
import os,ctypes,uuid
from ctypes import wintypes as w

class GUID(ctypes.Structure):
    _fields_=[('Data1',w.DWORD),('Data2',w.WORD),('Data3',w.WORD),('Data4',ctypes.c_ubyte*8)]
    @classmethod
    def parse(cls,text):
        return cls.from_buffer_copy(uuid.UUID(text.strip('{}')).bytes_le)
class InterfaceData(ctypes.Structure):
    _fields_=[('cbSize',w.DWORD),('InterfaceClassGuid',GUID),('Flags',w.DWORD),('Reserved',ctypes.c_size_t)]
class PipeInfo(ctypes.Structure):
    _fields_=[('PipeType',ctypes.c_int),('PipeId',ctypes.c_ubyte),('MaximumPacketSize',w.USHORT),('Interval',ctypes.c_ubyte)]

def interface_guids(key):
    """Windows drivers use either the singular REG_SZ or plural REG_MULTI_SZ."""
    import winreg
    guids=set()
    for name in ('DeviceInterfaceGUIDs','DeviceInterfaceGUID'):
        try:value,_=winreg.QueryValueEx(key,name)
        except FileNotFoundError:continue
        guids.update(value if isinstance(value,list) else [value])
    return guids

def enumerate_paths():
    if os.name!='nt':return []
    import winreg
    guids=set()
    base=r'SYSTEM\CurrentControlSet\Enum\USB'
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,base) as root:
        i=0
        while True:
            try:name=winreg.EnumKey(root,i);i+=1
            except OSError:break
            if not name.lower().startswith('vid_2a55&pid_9990'):continue
            with winreg.OpenKey(root,name) as device:
                j=0
                while True:
                    try:instance=winreg.EnumKey(device,j);j+=1
                    except OSError:break
                    try:
                        with winreg.OpenKey(device,instance+r'\Device Parameters') as key:
                            guids.update(interface_guids(key))
                    except FileNotFoundError:pass
    setup=ctypes.WinDLL('setupapi',use_last_error=True)
    setup.SetupDiGetClassDevsW.argtypes=[ctypes.POINTER(GUID),w.LPCWSTR,w.HWND,w.DWORD];setup.SetupDiGetClassDevsW.restype=w.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.POINTER(GUID),w.DWORD,ctypes.POINTER(InterfaceData)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes=[w.HANDLE,ctypes.POINTER(InterfaceData),ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes=[w.HANDLE]
    paths=[]
    for text in guids:
        guid=GUID.parse(text);handle=setup.SetupDiGetClassDevsW(ctypes.byref(guid),None,None,0x12)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:
            i=0
            while True:
                data=InterfaceData();data.cbSize=ctypes.sizeof(data)
                if not setup.SetupDiEnumDeviceInterfaces(handle,None,ctypes.byref(guid),i,ctypes.byref(data)):
                    err=ctypes.get_last_error()
                    if err==259:break
                    raise ctypes.WinError(err)
                i+=1;needed=w.DWORD()
                setup.SetupDiGetDeviceInterfaceDetailW(handle,ctypes.byref(data),None,0,ctypes.byref(needed),None)
                buf=ctypes.create_string_buffer(needed.value)
                ctypes.cast(buf,ctypes.POINTER(w.DWORD))[0]=8 if ctypes.sizeof(ctypes.c_void_p)==8 else 6
                if not setup.SetupDiGetDeviceInterfaceDetailW(handle,ctypes.byref(data),buf,len(buf),ctypes.byref(needed),None):raise ctypes.WinError(ctypes.get_last_error())
                path=ctypes.wstring_at(ctypes.addressof(buf)+4)
                if 'vid_2a55&pid_9990' in path.lower():paths.append(path)
        finally:setup.SetupDiDestroyDeviceInfoList(handle)
    return sorted(set(paths))

class WinUSB:
    def __init__(self,path):
        if os.name!='nt':raise OSError('WinUSB requires Windows')
        if 'vid_2a55&pid_9990' not in path.lower():raise ValueError('Unexpected device')
        self.file=None;self.handle=ctypes.c_void_p()
        self.k=ctypes.WinDLL('kernel32',use_last_error=True);self.u=ctypes.WinDLL('winusb',use_last_error=True)
        self.k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE];self.k.CreateFileW.restype=w.HANDLE
        self.k.CloseHandle.argtypes=[w.HANDLE]
        self.u.WinUsb_Initialize.argtypes=[w.HANDLE,ctypes.POINTER(ctypes.c_void_p)]
        self.u.WinUsb_Free.argtypes=[ctypes.c_void_p]
        self.u.WinUsb_QueryPipe.argtypes=[ctypes.c_void_p,ctypes.c_ubyte,ctypes.c_ubyte,ctypes.POINTER(PipeInfo)]
        self.u.WinUsb_SetPipePolicy.argtypes=[ctypes.c_void_p,ctypes.c_ubyte,w.ULONG,w.ULONG,ctypes.c_void_p]
        for name in ('WinUsb_ResetPipe','WinUsb_FlushPipe'):
            getattr(self.u,name).argtypes=[ctypes.c_void_p,ctypes.c_ubyte]
            getattr(self.u,name).restype=w.BOOL
        for name in ('WinUsb_WritePipe','WinUsb_ReadPipe'):
            getattr(self.u,name).argtypes=[ctypes.c_void_p,ctypes.c_ubyte,ctypes.c_void_p,w.ULONG,ctypes.POINTER(w.ULONG),ctypes.c_void_p]
        self.file=self.k.CreateFileW(path,0xc0000000,3,None,3,0x40000000,None)
        if self.file==ctypes.c_void_p(-1).value:self.file=None;raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.u.WinUsb_Initialize(self.file,ctypes.byref(self.handle)):raise ctypes.WinError(ctypes.get_last_error())
            found=set()
            for index in range(32):
                info=PipeInfo()
                if not self.u.WinUsb_QueryPipe(self.handle,0,index,ctypes.byref(info)):break
                if info.PipeType==2:found.add(info.PipeId)
            if not {1,0x81}.issubset(found):raise OSError('Expected bulk endpoints are missing')
            self.set_timeout(1500)
        except Exception:self.close();raise
    def set_timeout(self,milliseconds):
        if not 100<=milliseconds<=5000:raise ValueError('Invalid USB timeout')
        timeout=w.ULONG(milliseconds)
        for ep in (1,0x81):
            if not self.u.WinUsb_SetPipePolicy(self.handle,ep,3,4,ctypes.byref(timeout)):raise ctypes.WinError(ctypes.get_last_error())
    def device_descriptor(self):
        function=self.u.WinUsb_GetDescriptor
        function.argtypes=[ctypes.c_void_p,ctypes.c_ubyte,ctypes.c_ubyte,w.USHORT,ctypes.c_void_p,w.ULONG,ctypes.POINTER(w.ULONG)]
        function.restype=w.BOOL
        buf=ctypes.create_string_buffer(18);actual=w.ULONG()
        if not function(self.handle,1,0,0,buf,18,ctypes.byref(actual)):raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw[:actual.value]
    def write(self,ep,payload):
        buf=ctypes.create_string_buffer(payload);actual=w.ULONG()
        if not self.u.WinUsb_WritePipe(self.handle,ep,buf,len(payload),ctypes.byref(actual),None):raise ctypes.WinError(ctypes.get_last_error())
        return actual.value
    def read(self,ep,length):
        buf=ctypes.create_string_buffer(length);actual=w.ULONG()
        if not self.u.WinUsb_ReadPipe(self.handle,ep,buf,length,ctypes.byref(actual),None):raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw[:actual.value]
    def reset_pipes(self):
        """Recover failed synchronous I/O before closing this worker's handle."""
        for ep in (1,0x81):
            if not self.u.WinUsb_ResetPipe(self.handle,ep):raise ctypes.WinError(ctypes.get_last_error())
        if not self.u.WinUsb_FlushPipe(self.handle,0x81):raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle.value:self.u.WinUsb_Free(self.handle);self.handle=ctypes.c_void_p()
        if self.file:self.k.CloseHandle(self.file);self.file=None

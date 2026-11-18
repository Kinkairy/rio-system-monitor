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

class SetupPacket(ctypes.Structure):
    _pack_=1
    _fields_=[('RequestType',ctypes.c_ubyte),('Request',ctypes.c_ubyte),
              ('Value',ctypes.c_uint16),('Index',ctypes.c_uint16),('Length',ctypes.c_uint16)]

def interface_guids(key):
    """Windows drivers use either the singular REG_SZ or plural REG_MULTI_SZ."""
    import winreg
    guids=set()
    for name in ('DeviceInterfaceGUIDs','DeviceInterfaceGUID'):
        try:value,_=winreg.QueryValueEx(key,name)
        except FileNotFoundError:continue
        guids.update(value if isinstance(value,list) else [value])
    return guids

def supported_identity(path):
    from .display_protocols import device_id, rio_frame_interface
    return device_id(path) == (0x2a55,0x9990) or rio_frame_interface(path)

class DevicePropertyKey(ctypes.Structure):
    _fields_ = [('fmtid', GUID), ('pid', w.DWORD)]


def device_arrival(path):
    """LastArrivalDate of the device behind a live interface, when Windows supplies it."""
    if os.name != 'nt':
        return None
    try:
        cfg = ctypes.windll.cfgmgr32
        interface_property = cfg.CM_Get_Device_Interface_PropertyW
        locate = cfg.CM_Locate_DevNodeW
        node_property = cfg.CM_Get_DevNode_PropertyW
    except (AttributeError, OSError):
        return None
    prop_args = [ctypes.POINTER(DevicePropertyKey), ctypes.POINTER(w.ULONG),
                 ctypes.c_void_p, ctypes.POINTER(w.ULONG), w.ULONG]
    interface_property.argtypes = [w.LPCWSTR, *prop_args]
    locate.argtypes = [ctypes.POINTER(w.ULONG), w.LPCWSTR, w.ULONG]
    node_property.argtypes = [w.ULONG, *prop_args]
    instance_key = DevicePropertyKey(GUID.parse('78c34fc8-104a-4aca-9ea4-524d52996e57'), 256)
    arrival_key = DevicePropertyKey(GUID.parse('83da6326-97a6-4088-9453-a1923f573b29'), 102)
    instance = ctypes.create_unicode_buffer(200)  # MAX_DEVICE_ID_LEN
    kind, size = w.ULONG(), w.ULONG(ctypes.sizeof(instance))
    if interface_property(path, ctypes.byref(instance_key), ctypes.byref(kind), instance,
                          ctypes.byref(size), 0) or kind.value != 0x12:  # DEVPROP_TYPE_STRING
        return None
    node = w.ULONG()
    if locate(ctypes.byref(node), instance.value, 0):
        return None
    arrival = ctypes.c_uint64()
    size = w.ULONG(ctypes.sizeof(arrival))
    if node_property(node, ctypes.byref(arrival_key), ctypes.byref(kind), ctypes.byref(arrival),
                     ctypes.byref(size), 0) or kind.value != 0x10 or size.value != 8:  # FILETIME
        return None
    return arrival.value or None


def enumerate_paths():
    if os.name!='nt':return []
    import winreg
    from .display_protocols import RIO_FRAME_GUID
    guids={RIO_FRAME_GUID}
    base=r'SYSTEM\CurrentControlSet\Enum\USB'
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,base) as root:
        i=0
        while True:
            try:name=winreg.EnumKey(root,i);i+=1
            except OSError:break
            if not supported_identity(name):continue
            with winreg.OpenKey(root,name) as device:
                j=0
                while True:
                    try:instance=winreg.EnumKey(device,j);j+=1
                    except OSError:break
                    try:
                        with winreg.OpenKey(device,instance+r'\Device Parameters') as key:
                            guids.update(text.lower() for text in interface_guids(key))
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
                if supported_identity(path):paths.append(path)
        finally:setup.SetupDiDestroyDeviceInfoList(handle)
    return sorted(set(paths))

class WinUSB:
    endpoints=(1,0x81)
    def __init__(self,path,*,profile='legacy'):
        if os.name!='nt':raise OSError('WinUSB requires Windows')
        from .display_protocols import device_id, rio_frame_interface
        if profile == 'legacy':
            qualified = device_id(path) == (0x2a55,0x9990) and not rio_frame_interface(path)
            self.endpoints = (1,0x81)
        elif profile == 'lt168b-bench':
            qualified = rio_frame_interface(path)
            self.endpoints = (1,0x82)
        else:
            raise ValueError('Unknown USB profile')
        if not qualified:raise ValueError('Unexpected device')
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
            if not set(self.endpoints).issubset(found):raise OSError('Expected bulk endpoints are missing')
            self.set_timeout(1500)
        except Exception:self.close();raise
    def set_timeout(self,milliseconds):
        if not 100<=milliseconds<=5000:raise ValueError('Invalid USB timeout')
        timeout=w.ULONG(milliseconds)
        for ep in self.endpoints:
            if not self.u.WinUsb_SetPipePolicy(self.handle,ep,3,4,ctypes.byref(timeout)):raise ctypes.WinError(ctypes.get_last_error())
    def device_descriptor(self):
        function=self.u.WinUsb_GetDescriptor
        function.argtypes=[ctypes.c_void_p,ctypes.c_ubyte,ctypes.c_ubyte,w.USHORT,ctypes.c_void_p,w.ULONG,ctypes.POINTER(w.ULONG)]
        function.restype=w.BOOL
        buf=ctypes.create_string_buffer(18);actual=w.ULONG()
        if not function(self.handle,1,0,0,buf,18,ctypes.byref(actual)):raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw[:actual.value]
    def _raise_io_error(self,api,ep,requested,reported):
        error=ctypes.WinError(ctypes.get_last_error())
        error.usb_api=api;error.usb_endpoint=ep
        error.usb_requested=requested;error.usb_reported=reported
        raise error  # The count on failure is diagnostic, never a completed transfer.
    def write(self,ep,payload):
        buf=ctypes.create_string_buffer(payload);actual=w.ULONG()
        if not self.u.WinUsb_WritePipe(self.handle,ep,buf,len(payload),ctypes.byref(actual),None):self._raise_io_error('WinUsb_WritePipe',ep,len(payload),actual.value)
        return actual.value
    def read(self,ep,length):
        buf=ctypes.create_string_buffer(length);actual=w.ULONG()
        if not self.u.WinUsb_ReadPipe(self.handle,ep,buf,length,ctypes.byref(actual),None):self._raise_io_error('WinUsb_ReadPipe',ep,length,actual.value)
        return buf.raw[:actual.value]
    def control(self,request_type,request,value,index,length):
        """Bounded vendor handshake/reset used only by an explicit adapter."""
        probe = (request_type == 0xc1 and request == 0x54 and length == 64
                 and value in (0, 1, 2) and 0 <= index < 4096
                 and (value != 0 or index == 0))
        maintenance = value == 0xb201 and (
            (request_type,request,index,length) in ((0xc0,0x57,0,64),(0x40,0x59,0,0))
            or (request_type,request,length)==(0xc0,0x58,4096) and 0<=index<147
            or request_type==0x40 and request in (0x5a,0x5b) and length==0 and 0<=index<333)
        if not maintenance and not probe and (request_type,request,value,index,length) not in ((0xc1,0x52,0,0,32),(0x41,0x53,0,0,0)):
            raise ValueError('Unsupported control request')
        if self.endpoints!=(1,0x82):raise ValueError('Control protocol requires bench profile')
        function=self.u.WinUsb_ControlTransfer
        function.argtypes=[ctypes.c_void_p,SetupPacket,ctypes.c_void_p,w.ULONG,ctypes.POINTER(w.ULONG),ctypes.c_void_p]
        function.restype=w.BOOL
        setup=SetupPacket(request_type,request,value,index,length)
        buf=ctypes.create_string_buffer(max(1,length));actual=w.ULONG()
        if not function(self.handle,setup,buf,length,ctypes.byref(actual),None):
            self._raise_io_error('WinUsb_ControlTransfer',0,length,actual.value)
        return buf.raw[:actual.value]
    def reset_pipes(self):
        """Recover failed synchronous I/O before closing this worker's handle."""
        for ep in self.endpoints:
            if not self.u.WinUsb_ResetPipe(self.handle,ep):raise ctypes.WinError(ctypes.get_last_error())
        if not self.u.WinUsb_FlushPipe(self.handle,self.endpoints[1]):raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle.value:self.u.WinUsb_Free(self.handle);self.handle=ctypes.c_void_p()
        if self.file:self.k.CloseHandle(self.file);self.file=None

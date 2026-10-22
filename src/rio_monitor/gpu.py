"""Optional driver-provided NVIDIA counter. Does not install/ship a vendor DLL."""
import os,ctypes
from pathlib import Path
class Utilization(ctypes.Structure):
    _fields_=[('gpu',ctypes.c_uint),('memory',ctypes.c_uint)]
class Nvidia:
    def __init__(self):
        self.lib=None;self.handle=ctypes.c_void_p()
        if os.name!='nt':return
        paths=[Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'nvml.dll',Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'NVIDIA Corporation'/'NVSMI'/'nvml.dll']
        for path in paths:
            if not path.is_file():continue
            try:
                lib=ctypes.CDLL(str(path))
                lib.nvmlDeviceGetHandleByIndex_v2.argtypes=[ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p)]
                lib.nvmlDeviceGetUtilizationRates.argtypes=[ctypes.c_void_p,ctypes.POINTER(Utilization)]
                if lib.nvmlInit_v2()!=0:continue
                if lib.nvmlDeviceGetHandleByIndex_v2(0,ctypes.byref(self.handle))!=0:lib.nvmlShutdown();continue
                self.lib=lib;break
            except (OSError,AttributeError):continue
    def usage(self):
        if not self.lib:return None
        u=Utilization()
        return float(u.gpu) if self.lib.nvmlDeviceGetUtilizationRates(self.handle,ctypes.byref(u))==0 else None
    def close(self):
        if self.lib:self.lib.nvmlShutdown();self.lib=None

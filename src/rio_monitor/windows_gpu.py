"""Windows GPU identity and utilization using DXGI LUIDs and English PDH paths."""
import ctypes as C
import math
import os
import re
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Adapter:
    identifier:str
    name:str
    vendor:int


def aggregate_engines(rows):
    """Sum processes on each engine, then report the busiest engine per adapter."""
    engines={}
    pattern=r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)_eng_(\d+)'
    for name,value in rows:
        match=re.search(pattern,name,re.I)
        if not match or not math.isfinite(value) or value<0:continue
        high,low,physical,engine=match.groups()
        identifier=f'{int(high,16):08x}:{int(low,16):08x}'
        key=(identifier,physical,engine)
        engines[key]=engines.get(key,0)+value
    result={}
    for (identifier,_,_),value in engines.items():result[identifier]=max(result.get(identifier,0),min(100.0,value))
    return result


def enumerate_adapters():
    if os.name!='nt':return []
    class LUID(C.Structure):_fields_=[('low',C.c_uint32),('high',C.c_int32)]
    class Desc(C.Structure):
        _fields_=[('name',C.c_wchar*128),('vendor',C.c_uint32),('device',C.c_uint32),('subsystem',C.c_uint32),('revision',C.c_uint32),('video_memory',C.c_size_t),('system_memory',C.c_size_t),('shared_memory',C.c_size_t),('luid',LUID),('flags',C.c_uint32)]
    dxgi=C.WinDLL('dxgi');factory=C.c_void_p()
    iid=C.create_string_buffer(uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    dxgi.CreateDXGIFactory1.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)];dxgi.CreateDXGIFactory1.restype=C.c_int32
    if dxgi.CreateDXGIFactory1(iid,C.byref(factory))<0:return []
    def method(obj,index,restype,*args):
        table=C.cast(obj,C.POINTER(C.POINTER(C.c_void_p))).contents
        return C.WINFUNCTYPE(restype,C.c_void_p,*args)(table[index])
    adapters=[]
    try:
        enum=method(factory,12,C.c_int32,C.c_uint32,C.POINTER(C.c_void_p))
        for index in range(32):
            adapter=C.c_void_p();status=enum(factory,index,C.byref(adapter))
            if status & 0xffffffff==0x887a0002:break
            if status<0:raise OSError(f'DXGI adapter enumeration failed: {status & 0xffffffff:08x}')
            try:
                desc=Desc()
                if method(adapter,10,C.c_int32,C.POINTER(Desc))(adapter,C.byref(desc))<0:continue
                if desc.flags & 2:continue  # Microsoft software rasterizer
                identifier=f'{desc.luid.high & 0xffffffff:08x}:{desc.luid.low:08x}'
                adapters.append(Adapter(identifier,desc.name,desc.vendor))
            finally:method(adapter,2,C.c_uint32)(adapter)
    finally:method(factory,2,C.c_uint32)(factory)
    return adapters


class EngineCounters:
    def __init__(self,path=r'\GPU Engine(*)\Utilization Percentage'):
        self.query=C.c_void_p();self.counter=C.c_void_p();self.error=None;self.warmed=False
        if os.name!='nt':return
        try:
            self.pdh=C.WinDLL('pdh')
            self.pdh.PdhOpenQueryW.argtypes=[C.c_wchar_p,C.c_size_t,C.POINTER(C.c_void_p)]
            self.pdh.PdhAddEnglishCounterW.argtypes=[C.c_void_p,C.c_wchar_p,C.c_size_t,C.POINTER(C.c_void_p)]
            self.pdh.PdhCollectQueryData.argtypes=[C.c_void_p]
            self.pdh.PdhGetFormattedCounterArrayW.argtypes=[C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32),C.c_void_p]
            self.pdh.PdhCloseQuery.argtypes=[C.c_void_p]
            self._check(self.pdh.PdhOpenQueryW(None,0,C.byref(self.query)))
            self._check(self.pdh.PdhAddEnglishCounterW(self.query,path,0,C.byref(self.counter)))
            self._check(self.pdh.PdhCollectQueryData(self.query))
        except (OSError,AttributeError) as exc:self.error=str(exc);self.close()

    @staticmethod
    def _check(status):
        if status:raise OSError(f'GPU counter status: {status & 0xffffffff:08x}')

    def read_raw(self):
        if not self.query.value:return None
        try:
            self._check(self.pdh.PdhCollectQueryData(self.query))
            size=C.c_uint32();count=C.c_uint32();flags=0x200|0x8000
            status=self.pdh.PdhGetFormattedCounterArrayW(self.counter,flags,C.byref(size),C.byref(count),None)
            if status & 0xffffffff!=0x800007d2:self._check(status)
            if size.value==0:return []
            if size.value>32*1024*1024:raise OSError('GPU counter buffer is too large')
            class Value(C.Structure):_fields_=[('status',C.c_uint32),('number',C.c_double)]
            class Item(C.Structure):_fields_=[('name',C.c_wchar_p),('value',Value)]
            buffer=C.create_string_buffer(size.value)
            self._check(self.pdh.PdhGetFormattedCounterArrayW(self.counter,flags,C.byref(size),C.byref(count),buffer))
            items=C.cast(buffer,C.POINTER(Item));rows=[]
            for index in range(count.value):
                item=items[index]
                if item.value.status in (0,1):rows.append((item.name,item.value.number))
            self.warmed=True;self.error=None
            return rows
        except OSError as exc:self.error=str(exc);return None

    def read(self):
        rows=self.read_raw()
        return aggregate_engines(rows) if rows is not None else None

    def close(self):
        if self.query.value:self.pdh.PdhCloseQuery(self.query);self.query=C.c_void_p()


class AdapterTemperatures:
    """Read WDDM performance temperature through Windows' existing graphics driver."""
    def __init__(self):
        self.gdi=None
        if os.name!='nt':return
        try:
            self.gdi=C.WinDLL('gdi32')
            for name in ('D3DKMTOpenAdapterFromLuid','D3DKMTQueryAdapterInfo','D3DKMTCloseAdapter'):
                getattr(self.gdi,name).argtypes=[C.c_void_p];getattr(self.gdi,name).restype=C.c_int32
        except (OSError,AttributeError):self.gdi=None
    def read(self,identifier):
        if self.gdi is None:return None
        class Open(C.Structure):_fields_=[('low',C.c_uint32),('high',C.c_int32),('handle',C.c_uint32)]
        class Perf(C.Structure):
            _fields_=[('physical',C.c_uint32),('memory',C.c_uint64),('max_memory',C.c_uint64),('max_memory_oc',C.c_uint64),('bandwidth',C.c_uint64),('pcie_bandwidth',C.c_uint64),('fan',C.c_uint32),('power',C.c_uint32),('temperature',C.c_uint32),('power_override',C.c_ubyte)]
        class Query(C.Structure):_fields_=[('handle',C.c_uint32),('type',C.c_int32),('data',C.c_void_p),('size',C.c_uint32)]
        high,low=identifier.split(':');opened=Open(int(low,16),C.c_int32(int(high,16)).value,0)
        if self.gdi.D3DKMTOpenAdapterFromLuid(C.byref(opened))<0:return None
        try:
            perf=Perf();query=Query(opened.handle,62,C.addressof(perf),C.sizeof(perf))
            if self.gdi.D3DKMTQueryAdapterInfo(C.byref(query))<0:return None
            return perf.temperature/10 if 0<perf.temperature<=1250 else None
        finally:
            handle=C.c_uint32(opened.handle);self.gdi.D3DKMTCloseAdapter(C.byref(handle))

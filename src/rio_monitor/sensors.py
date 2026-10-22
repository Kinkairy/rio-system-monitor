"""System-only hardware data. No helper, sensor library or driver installation."""
import math,os,re,time
from .model import GPUReading
from .windows_gpu import enumerate_adapters,EngineCounters,AdapterTemperatures
from .gpu_selection import ActiveGPU


def cpu_model():
    if os.name!='nt':return ''
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            return winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    except OSError:return ''


def short_model(name):
    name=re.sub(r'\((?:R|TM)\)|®|™','',name,flags=re.I)
    name=re.sub(r'\b(?:NVIDIA|GeForce|Laptop GPU|Intel|AMD|Processor|CPU)\b','',name,flags=re.I)
    name=re.sub(r'\s+@\s+\S+.*','',name)
    return ' '.join(name.split())


def cpu_zone_temperature(rows):
    """An anonymous ACPI zone is not evidence of CPU temperature."""
    values=[]
    for name,kelvin in rows or []:
        if not re.search(r'cpu|processor|package|tctl',name,re.I):continue
        value=kelvin-273.15
        if math.isfinite(value) and 0<value<=125:values.append(value)
    return max(values) if values else None


class HardwareSensors:
    def __init__(self,adapters=None,counters=None,temperatures=None,thermal=None,clock=time.monotonic,component=None):
        self.adapters=enumerate_adapters() if adapters is None else adapters
        self.counters=EngineCounters() if counters is None else counters
        self.temperatures=AdapterTemperatures() if temperatures is None else temperatures
        self.thermal=EngineCounters(r'\Thermal Zone Information(*)\Temperature') if thermal is None else thermal
        self.cpu_name=cpu_model();self.clock=clock;self.notice='';self.component=component;self.selection=ActiveGPU()
    def read(self):
        now=self.clock();usage=self.counters.read();cpu_temperature=cpu_zone_temperature(self.thermal.read_raw())
        if self.component:
            self.component.note_native(cpu_temperature)
            cpu_temperature=(cpu_temperature if self.component.enabled and cpu_temperature is not None else self.component.temperature())
        self.notice='' if cpu_temperature is not None else 'Windows does not expose a CPU-specific temperature sensor'
        count=len(self.adapters)
        readings=tuple(GPUReading(a.identifier,a.name,usage.get(a.identifier,0.0) if usage is not None else None,self.temperatures.read(a.identifier),now,i,count) for i,a in enumerate(self.adapters))
        selected=self.selection.select(readings)
        return cpu_temperature,readings,selected
    def close(self):self.counters.close();self.thermal.close()

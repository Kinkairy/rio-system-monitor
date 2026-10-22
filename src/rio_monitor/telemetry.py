"""Read-only OS counters. Never install a sensor driver or substitute demo data."""
import time
import psutil
from .model import Sample,Readings

class Collector:
    def __init__(self,temperature=None):
        self.warmed = False
        self.previous_net = None
        self.previous_time = None
        from .sensors import HardwareSensors
        self.gpu = HardwareSensors(component=temperature)
        psutil.cpu_percent(None)
    def collect(self):
        now = time.monotonic()
        mem = psutil.virtual_memory()
        net = psutil.net_io_counters()
        cpu=psutil.cpu_percent(None)
        temperature,gpus,selected=self.gpu.read()
        result = Readings({'cpu': Sample(cpu if self.warmed else None,now),
                  'ram_used':Sample(mem.used/1024**3,now),
                  'ram_total':Sample(mem.total/1024**3,now),
                  'temperature':Sample(temperature,now,self.gpu.component.source if self.gpu.component else 'Windows CPU thermal zone'),
                  'gpu':Sample(selected.usage if selected else None,now,selected.identifier if selected else 'unavailable')},
                  cpu_name=self.gpu.cpu_name,gpus=gpus,selected_gpu=selected)
        result['gpu_temperature']=Sample(selected.temperature if selected else None,now,selected.identifier if selected else 'unavailable')
        rx=tx=None
        if self.previous_net is not None and now>self.previous_time:
            dt=now-self.previous_time
            dr=net.bytes_recv-self.previous_net.bytes_recv
            ds=net.bytes_sent-self.previous_net.bytes_sent
            if dr>=0 and ds>=0:rx,tx=dr/dt/1e6,ds/dt/1e6
        result['download']=Sample(rx,now)
        result['upload']=Sample(tx,now)
        self.previous_net,self.previous_time=net,now
        self.warmed=True
        # Unix sensor support; Windows temperature requires a supported backend.
        if hasattr(psutil,'sensors_temperatures'):
            try:
                temps=psutil.sensors_temperatures()
                for key in ('coretemp','k10temp','cpu_thermal'):
                    if temps.get(key):
                        result['temperature']=Sample(max(t.current for t in temps[key]),now,key)
                        break
            except (OSError,RuntimeError):pass
        return result

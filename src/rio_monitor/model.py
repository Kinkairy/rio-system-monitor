from dataclasses import dataclass
import math

@dataclass(frozen=True)
class GPUReading:
    identifier:str
    name:str
    usage:float | None
    temperature:float | None
    timestamp:float
    index:int=0
    count:int=1

class Readings(dict):
    """Numeric samples plus hardware identity, kept out of numeric freshness checks."""
    def __init__(self,*args,cpu_name='',gpus=(),selected_gpu=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.cpu_name=cpu_name;self.gpus=tuple(gpus);self.selected_gpu=selected_gpu

@dataclass(frozen=True)
class Sample:
    value: float | None
    timestamp: float
    source: str = 'system'

    def current(self, now: float, ttl: float = 5.0):
        if self.value is None or not math.isfinite(self.value):
            return None
        return self.value if 0 <= now - self.timestamp <= ttl else None

class Spring:
    """Damped movement; finite steps and bounded overshoot, no synthetic activity."""
    def __init__(self, value=0.0, stiffness=180, damping=21):
        self.stiffness, self.damping = stiffness, damping
        self.value = float(value)
        self.velocity = 0.0
    def update(self, target, dt):
        if not math.isfinite(target) or not math.isfinite(dt) or dt <= 0:
            return self.value
        # Clamp elapsed time after suspend; substep to keep numerical stability.
        remaining = min(dt, 0.2)
        while remaining > 0:
            step = min(remaining, 1/120)
            self.velocity += ((target-self.value)*self.stiffness - self.velocity*self.damping)*step
            self.value += self.velocity*step
            remaining -= step
        if abs(self.value-target)<0.001 and abs(self.velocity)<0.01:
            self.value, self.velocity = target, 0.0
        return self.value

class History:
    def __init__(self, limit=120):
        from collections import deque
        self.points = deque(maxlen=limit)
    def append(self, sample):
        self.points.append(sample)

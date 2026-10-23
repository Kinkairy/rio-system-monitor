from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Track:
    source: str = ''
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: float = 0
    position: float | None = None
    playing: bool = False
    observed: float = 0
    cover: bytes = b''
    @property
    def key(self): return (self.source, self.title, self.artist, self.album)
    def position_at(self, now):
        if self.position is None or now-self.observed>3:return None
        value=self.position+(max(0,now-self.observed) if self.playing else 0)
        return max(0,min(self.duration,value)) if self.duration>0 else max(0,value)

@dataclass(frozen=True)
class Audio:
    bands: tuple = (0.0,)*12
    level: float = 0
    observed: float = 0
    status: str = 'off'
    def current(self,now):
        return self if 0<=now-self.observed<=.35 else Audio(status=self.status)

class Spectrum:
    """12 log-spaced FFT bands, DC removed, bounded dB range; no fake beats."""
    def __init__(self,rate):self.rate=rate
    def analyze(self,pcm,channels,now):
        import numpy as np
        x=np.asarray(pcm,dtype=np.float32).reshape(-1,channels)
        # Power over channels avoids cancellation for opposite-phase stereo.
        x=np.nan_to_num(x,nan=0,posinf=0,neginf=0);x=x-x.mean(axis=0)
        rms=float(np.sqrt(np.mean(x*x))) if len(x) else 0
        if len(x)<64 or rms<1e-5:return Audio(observed=now,status='ready')
        window=np.hanning(len(x));fft=np.fft.rfft(x*window[:,None],axis=0)
        power=np.mean(abs(fft)**2,axis=1)/(max(1,window.sum())**2)
        frequencies=np.fft.rfftfreq(len(x),1/self.rate)
        edges=np.geomspace(35,min(16000,self.rate*.48),13)
        bands=[]
        for lo,hi in zip(edges,edges[1:]):
            values=power[(frequencies>=lo)&(frequencies<hi)]
            db=10*math.log10(max(1e-12,float(values.sum())))
            bands.append(max(0,min(1,(db+65)/55)))
        level=max(0,min(1,(20*math.log10(max(1e-9,rms))+55)/50))
        return Audio(tuple(bands),level,now,'ready')

def select_session(items,preferred='',previous=''):
    """items: (app_id, playing, session); explicit choice never silently changes."""
    if preferred:return next((x for x in items if x[0]==preferred),None)
    return (next((x for x in items if x[0]==previous and x[1]),None)
            or next((x for x in items if x[1]),None)
            or next((x for x in items if x[0]==previous),None)
            or (items[0] if items else None))

class AutomaticMusicView:
    """Enter on playback; return after 30 continuous paused/stopped seconds."""
    def __init__(self):self.active=False;self.idle_since=None
    def select(self,snapshot,now):
        if not snapshot['enabled']:
            self.active=False;self.idle_since=None;return False
        track=snapshot['track']
        playing=(snapshot['status']=='ready' and track.playing and 0<=now-track.observed<=3)
        if playing:self.active=True;self.idle_since=None
        elif self.active:
            if self.idle_since is None:self.idle_since=now
            if now-self.idle_since>=30:self.active=False
        return self.active

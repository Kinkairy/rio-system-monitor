"""Sparse temperature sheen: random idle intervals, clipped to lime glyphs."""
import random
from PIL import Image,ImageChops

class TemperatureSheen:
    duration=1.5
    def __init__(self,rng=None):
        self.rng=rng or random.Random()
        self.next_at=None
        self.started=None
    def phase(self,now):
        if self.next_at is None:
            self.next_at=now+self.rng.uniform(20,40)
        if self.started is None and now>=self.next_at:
            self.started=now
        if self.started is None:return None
        elapsed=now-self.started
        if elapsed>=self.duration:
            self.started=None
            self.next_at=now+self.rng.uniform(20,40)
            return None
        return elapsed/self.duration
    @staticmethod
    def apply(im,phase):
        if phase is None or not 0<=phase<=1:return
        box=(413,320,825,484)
        crop=im.crop(box);w,h=crop.size
        r,g,b=crop.split()
        mask=ImageChops.multiply(r.point(lambda v:255 if v>80 else 0),g.point(lambda v:255 if v>130 else 0))
        mask=ImageChops.multiply(mask,b.point(lambda v:255 if v<120 else 0))
        center=-110+phase*(w+220)
        # Crisp pure-white diagonal highlight, clipped to glyphs only.
        band=Image.new('L',(w,h))
        band.putdata([255 if (abs(x+(y-h/2)*.32-center)<=26 or abs(x+(y-h/2)*.32-center-60)<=8) else 0 for y in range(h) for x in range(w)])
        alpha=ImageChops.multiply(mask,band)
        im.paste((255,255,255),box,alpha)

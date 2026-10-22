"""Nine real historical samples; damped visual heights never change readings."""
from PIL import ImageDraw
from .model import Spring
CPU=[(10,95,111),(12,142,160),(15,188,196),(26,226,204),(113,248,147),(224,251,97)]
GPU=[(102,36,137),(147,41,168),(196,44,177),(241,54,163),(255,110,130),(255,186,110)]
class UsageChart:
 def __init__(self):
  self.values=[None]*9;self.springs=[Spring(damping=14) for _ in range(9)];self.last_stamp=None
 def update(self,sample,now,dt):
  if sample is not None and sample.timestamp!=self.last_stamp:
   self.values=self.values[1:]+[sample.current(now)];self.last_stamp=sample.timestamp
  fresh=sample is not None and sample.current(now) is not None
  for s,v in zip(self.springs,self.values):s.update(v if v is not None else 0,dt)
  return fresh
 def draw(self,im,left,palette,fresh):
  d=ImageDraw.Draw(im);scale=im.width/480
  for i,(s,v) in enumerate(zip(self.springs,self.values)):
   height=max(0,min(100,s.value))/100*6 if v is not None and fresh else 0
   for j in range(6):
    x=left+77+i*13;y=327-j*9
    box=tuple(round(z*scale) for z in (x,y-6,x+8,y))
    d.rectangle(box,fill=(12,43,35))
    portion=max(0,min(1,height-j))
    if portion:
     top=box[3]-round((box[3]-box[1]+1)*portion)+1
     if top<=box[3]:d.rectangle((box[0],max(box[1],top),box[2],box[3]),fill=palette[j])

"""Render actual bundled font outlines without distorting glyph proportions."""
from PIL import Image,ImageDraw,ImageFont
from functools import lru_cache
from pathlib import Path
import re
FONTS={'born':'Born2bSporty.otf','operator':'PixelOperatorHB.ttf','upheaval':'Upheaval.ttf'}
class RollingText:
 def __init__(self,assets,choice='born'):
  self.path=Path(assets)/'fonts'/FONTS[choice];self.choice=choice;self.states={}
 @lru_cache(maxsize=256)
 def font(self,size):
  f=ImageFont.truetype(str(self.path),size)
  if self.choice=='pixelify':f.set_variation_by_axes([700])
  return f
 @lru_cache(maxsize=512)
 def layout(self,text,w,h):
  for size in range(250,5,-1):
   f=self.font(size);box=f.getbbox('0123456789')
   advance=max(f.getlength(c) for c in '0123456789')
   widths=[advance if c.isdigit() else (h*.32 if c=='/' else f.getlength(c)) for c in text]
   if sum(widths)<=w and box[3]-box[1]<=h:return size,box,tuple(widths)
  return size,box,tuple(widths)
 def draw(self,canvas,key,text,box,color,now):
  old,target,start=self.states.get(key,(text,text,now))
  if target!=text:old,target,start=target,text,now
  self.states[key]=(old,target,start)
  x,y,w,h=box;size,bounds,widths=self.layout(text,w,h);f=self.font(size)
  layer=Image.new('RGBA',(w,h));d=ImageDraw.Draw(layer)
  phase=min(1,max(0,(now-start)/.35));eased=1-(1-phase)**3
  direction=1
  try:direction=1 if float(re.search(r'\d+(?:\.\d+)?',text)[0])>=float(re.search(r'\d+(?:\.\d+)?',old)[0]) else -1
  except (TypeError,ValueError):pass
  left=(w-sum(widths))/2;top=(h-(bounds[3]-bounds[1]))/2-bounds[1]
  for i,(ch,advance) in enumerate(zip(text,widths)):
   fill='white' if key=='ram' and '/' in text and i>=text.index('/') else color
   px=left+(advance-f.getlength(ch))/2
   if ch=='/':
    # A geometric separator, independent of the selected font and digit animation.
    cy=h/2;length=h*.68;thickness=max(2,round(h*.075))
    cx=left+advance/2
    d.line((cx-length*.18,cy+length/2,cx+length*.18,cy-length/2),fill=fill,width=thickness)
    left+=advance
    continue
   previous=old[i] if len(old)==len(text) else ch
   if previous!=ch and phase<1:
    d.text((px,top-direction*eased*h),previous,font=f,fill=fill)
    d.text((px,top+direction*(1-eased)*h),ch,font=f,fill=fill)
   else:d.text((px,top),ch,font=f,fill=fill)
   left+=advance
  canvas.paste(layer,(x,y),layer)

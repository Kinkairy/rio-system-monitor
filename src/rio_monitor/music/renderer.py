"""Approved 480px music layout, real values only; UI preview artwork stays private."""
from PIL import Image,ImageDraw,ImageFont,ImageOps
from pathlib import Path
from functools import lru_cache
from bisect import bisect_right
import math,io,os,time
from ..model import Spring
from .state import Track,Audio
from .lyrics import current_lines

S=1

def source_label(app):
    value=app.lower()
    for key,name in [('qqmusic','QQ MUSIC'),('cloudmusic','NETEASE'),('spotify','SPOTIFY'),('applemusic','APPLE MUSIC'),('kugou','KUGOU'),('kwmusic','KUWO')]:
        if key in value:return name
    return 'MEDIA SESSION' if app else 'RIO MUSIC'

def marquee_offset(width,viewport,elapsed,speed=32,pause=1):
    distance=max(0,width-viewport)
    if not distance:return 0
    travel=distance/speed;phase=max(0,elapsed)%(2*(travel+pause))
    if phase<pause:return 0
    if phase<pause+travel:return (phase-pause)*speed
    if phase<2*pause+travel:return distance
    return distance-(phase-2*pause-travel)*speed

def lyric_scroll_offset(distance,elapsed,span):
    if distance<=0:return 0
    hold=min(.65,span*.15)
    return distance*max(0,min(1,(elapsed-hold)/max(.1,span-2*hold)))

class MusicRenderer:
 def __init__(self,assets):
  self.assets=Path(assets);self.columns=[Spring(damping=14) for _ in range(24)];self.level=Spring(damping=14)
  self.current=Track();self.previous=Track();self.changed=None;self.previous_lines=((),(),0);self.last_lines=self.previous_lines;self.last=None;self.angle=0;self.covers={};self.title_key=None;self.title_since=0
  self.pixel=str(self.assets/'fonts/RIOPixel-Regular.ttf')
  if not Path(self.pixel).is_file():self.pixel=str(self.assets/'fonts/Born2bSporty.otf')
  self.chinese=next((str(p) for p in [self.assets/'fonts/NotoSansCJK-Regular.ttc',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc',Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')] if p.is_file()),self.pixel)
  path=self.assets/'rio-brand.png'
  if path.exists():self.badge=Image.open(path).convert('RGBA').crop((8,88,248,168)).resize((96*S,32*S),Image.Resampling.LANCZOS)
  else:
   self.badge=Image.new('RGBA',(96*S,32*S),'#eadd3d');ImageDraw.Draw(self.badge).text((10,4),'RIO',font=ImageFont.load_default(size=40),fill='black')
 @lru_cache(maxsize=32)
 def font(self,path,size):
  try:return ImageFont.truetype(path,size)
  except OSError:return ImageFont.load_default(size=size)
 @lru_cache(maxsize=4)
 def title_strip(self,text,fontpath):
  font=self.font(fontpath,25*S);width=math.ceil(font.getlength(text))
  strip=Image.new('RGBA',(width,38*S))
  ImageDraw.Draw(strip).text((0,19*S),text,font=font,fill='#ebdf50',anchor='lm')
  return strip
 def draw_title(self,image,text,now):
  if text!=self.title_key:self.title_key=text;self.title_since=now
  fontpath=self.chinese if any(ord(ch)>127 for ch in text) else self.pixel
  strip=self.title_strip(text,fontpath);viewport=310*S
  if strip.width<=viewport:
   image.paste(strip,((image.width-strip.width)//2,89*S),strip)
  else:
   offset=round(marquee_offset(strip.width,viewport,now-self.title_since,speed=32*S))
   visible=strip.crop((offset,0,offset+viewport,strip.height))
   image.paste(visible,(85*S,89*S),visible)
 def cover_for(self,track):
  key=(track.key,hash(track.cover))
  if key in self.covers:return self.covers[key]
  try:
   source=Image.open(io.BytesIO(track.cover))
   if source.width*source.height>16000000:raise ValueError('Oversized cover')
   source=ImageOps.fit(source.convert('RGBA'),(188*S,188*S),method=Image.Resampling.LANCZOS)
  except Exception:
   source=None
  if source is not None:
   mask=Image.new('L',source.size);ImageDraw.Draw(mask).ellipse((0,0,188*S-1,188*S-1),fill=255);source.putalpha(mask)
  self.covers[key]=source
  if len(self.covers)>3:self.covers.pop(next(iter(self.covers)))
  return source
 @lru_cache(maxsize=2)
 def private_record_art(self,name,size):
  try:
   with Image.open(self.assets/'music'/name) as source:
    if source.width*source.height>16000000:raise ValueError('Oversized artwork')
    return source.convert('RGBA').resize((size,size),Image.Resampling.LANCZOS)
  except (OSError,ValueError):
   # Source-only checkout remains usable; approved RIO art is private.
   image=Image.new('RGBA',(size,size));draw=ImageDraw.Draw(image)
   draw.ellipse((0,0,size-1,size-1),fill='#f5dc42' if 'label' in name else '#090c10')
   if 'label' not in name:
    for r in range(size//5,size//2-2,4):draw.ellipse((size//2-r,size//2-r,size//2+r,size//2+r),outline='#1a2025')
    draw.ellipse((size//3,size//3,size*2//3,size*2//3),fill='#f5dc42')
   r=max(1,round(size*(4/74 if 'label' in name else 4/222)))
   draw.ellipse((size//2-r,size//2-r,size//2+r,size//2+r),fill='#080c10')
   return image
 def lyric_lines(self,snapshot,now,zh):
  track=snapshot['track'];position=track.position_at(now)
  if not track.title:return (('等待播放' if zh else 'WAITING',),(),0)
  if position is None:return (('暂无时间轴' if zh else 'NO TIMELINE',),(),0)
  current,nextline=current_lines(snapshot['rows'],position)
  if not current and not nextline:
   status=snapshot['lyric_status']
   message={'loading':('加载歌词','LOADING'),'instrumental':('纯音乐','INSTRUMENTAL'),'online_off':('未开启在线歌词','LYRICS OFF')}.get(status,('暂无歌词','NO LYRICS'))
   return ((message[0 if zh else 1],),(),0)
  parts=self.wrap_text(current,19);following=self.wrap_text(nextline,13);progress=0
  index=bisect_right([row.time for row in snapshot['rows']],position)-1
  if index>=0:
   start=snapshot['rows'][index].time
   end=snapshot['rows'][index+1].time if index+1<len(snapshot['rows']) else track.duration
   span=end-start if end>start else 8
   progress=lyric_scroll_offset(1,position-start,span)
  return ((parts[0],''.join(parts[1:])),(following[0],''.join(following[1:])),progress)
 @lru_cache(maxsize=128)
 def wrap_text(self,text,size):
  parts=[''];font=self.font(self.chinese,size*S)
  for char in text:
   if font.getlength(parts[-1]+char)>125*S and parts[-1]:
    parts.append('')
   parts[-1]+=char
  return parts
 @lru_cache(maxsize=16)
 def lyric_strip(self,text,size,color):
  font=self.font(self.chinese,size*S);height=(28 if size>13 else 20)*S
  strip=Image.new('RGBA',(max(1,math.ceil(font.getlength(text))),height))
  ImageDraw.Draw(strip).text((0,height/2),text,font=font,fill=color,anchor='lm')
  return strip
 def draw_lyric_row(self,layer,text,size,color,x,y,progress):
  strip=self.lyric_strip(text,size,color);offset=max(0,strip.width-125*S)*progress
  visible=strip.transform((125*S,strip.height),Image.Transform.AFFINE,(1,0,offset,0,1,0),resample=Image.Resampling.BICUBIC)
  layer.paste(visible,(round(x*S),round(y*S-strip.height/2)))
 def render(self,snapshot,now=None,language='en'):
  now=time.monotonic() if now is None else now;zh=language=='zh';dt=min(.1,max(0,now-self.last)) if self.last is not None else 1/30;self.last=now
  incoming=snapshot['track'];audio=snapshot['audio'].current(now)
  if incoming.key!=self.current.key:
   self.previous=self.current;self.previous_lines=self.last_lines;self.current=incoming;self.changed=now if self.previous.title else None
  else:self.current=incoming
  elapsed=now-self.changed if self.changed is not None else 100
  exiting=elapsed<.34;track=self.previous if exiting else self.current
  self.last_lines=self.lyric_lines(snapshot,now,zh)
  lines=self.previous_lines if exiting else self.last_lines
  if incoming.playing:self.angle=(self.angle+dt*45)%360
  if exiting:
   p=max(0,min(1,elapsed/.26));record_dx=-300*p*p
  else:
   p=max(0,min(1,(elapsed-.38)/.30));record_dx=-300*(1-p)**3
  def slide(row=0):
   if exiting:
    p=max(0,min(1,(elapsed-row*.04)/.18));return 250*p*p
   p=max(0,min(1,(elapsed-.38-row*.035)/.24));return 250*(1-p)**3
  font=self.pixel;cn=self.chinese
  def short(text,fontpath,size,width):
   f=self.font(cn if any(ord(ch)>127 for ch in text) else fontpath,size*S)
   while len(text)>1 and f.getlength(text)>width*S:text=text[:-2]+'…'
   return text
  im=Image.new('RGB',(480*S,480*S),'#030708');d=ImageDraw.Draw(im)
  def b(v):return tuple(round(x*S) for x in v)
  def line(p,c,w=1):d.line([b(v) for v in p],fill=c,width=w*S)
  def tx(x,y,s,n,c,fontfile=font,anchor='mm'):d.text(b((x,y)),s,font=self.font(cn if any(ord(ch)>127 for ch in s) else fontfile,n*S),fill=c,anchor=anchor)
  def rect(v,c):d.rectangle(b(v),fill=c)
  def poly(v,c):d.polygon([b(p) for p in v],fill=c)
  d.ellipse(b((6,6,474,474)),fill='#07110f',outline='#344e45',width=2)
  # Two mirrored gauges share the same beat envelope but distinct colors.
  energy=self.level.update(audio.level,dt)
  for side in (0,1):
   for k in range(19):
    f=k/18
    ca,cb=((25,203,241),(129,255,81)) if side==0 else ((172,102,244),(255,161,65))
    col=tuple(round(v+(w-v)*f) for v,w in zip(ca,cb))
    if (k+.5)/19>energy:col=tuple(round(v*.19) for v in col)
    angle=184+k*3.6
    aa,zz=angle+.45,angle+3.15
    if side:aa,zz=540-zz,540-aa
    aa,zz=math.radians(aa),math.radians(zz)
    poly([(240+r*math.cos(th),240+r*math.sin(th)) for r,th in [(223,aa),(223,zz),(204,zz),(204,aa)]],col)
  for k in range(64):
   a=math.radians(k*360/64);r=231
   line([(240+r*math.cos(a),240+r*math.sin(a)),(240+(r-4)*math.cos(a),240+(r-4)*math.sin(a))],'#34443d')
  # Compact header; generous spacing separates identity from content.
  badge=self.badge
  im.paste(badge,(143*S,58*S),badge);d=ImageDraw.Draw(im)
  tx(248,74,'MUSIC',17,'#d5e3d9',anchor='lm')
  for x,c in [(326,'#54d4d3'),(338,'#a880df')]:poly([(x,82),(x+7,70),(x+13,70),(x+6,82)],c)
  self.draw_title(im,track.title or ('暂无歌曲' if zh else 'NO TRACK'),now)
  tx(240,132,short(track.artist or source_label(track.source),font,14,310),14,'#719c8c')
  # Draw the record on an independent layer for the track transition.
  base=im
  im=Image.new('RGBA',base.size)
  # Offset record leaves a dedicated readable lyric column.
  cx,cy=160,246
  record=self.private_record_art('default-record.png',222*S).rotate(-self.angle,resample=Image.Resampling.BICUBIC)
  im.paste(record,((cx-111)*S,(cy-111)*S),record)
  cover=self.cover_for(track)
  if cover is not None:
   art=cover.rotate(-self.angle,resample=Image.Resampling.BICUBIC);im.paste(art,((cx-94)*S,(cy-94)*S),art)
   label=self.private_record_art('record-label.png',74*S).rotate(-self.angle,resample=Image.Resampling.BICUBIC)
   im.paste(label,((cx-37)*S,(cy-37)*S),label)
  moving=Image.new('RGBA',base.size);moving.paste(im,(round(record_dx*S),0))
  clip=Image.new('L',base.size);ImageDraw.Draw(clip).rectangle(b((43,135,435,358)),fill=255)
  from PIL import ImageChops
  moving.putalpha(ImageChops.multiply(moving.getchannel('A'),clip));base.paste(moving,(0,0),moving);im=base;d=ImageDraw.Draw(im)
  # Light connector makes the lyrics and record a single composition.
  line([(268,180),(282,180),(292,170),(350,170)],'#4da88f',2)
  rect((279,195,282,285),'#245c4c');rect((279,220,282,251),'#7cebbb')
  tx(302,194,'LYRICS',9,'#78958d',anchor='lm')
  base=im;im=Image.new('RGBA',base.size);d=ImageDraw.Draw(im)
  current=list(lines[0])+['',''];following=list(lines[1])+['','']
  for row,text,size,color,y in [(0,current[0],19,'#b9ffcb',226),(1,current[1],23,'#f0e351',254),(2,following[0],13,'#597d70',290),(3,following[1],13,'#597d70',311)]:
   self.draw_lyric_row(im,text,size,color,299+slide(row),y,lines[2])
  clip=Image.new('L',base.size);ImageDraw.Draw(clip).rectangle(b((290,205,433,322)),fill=255)
  im.putalpha(ImageChops.multiply(im.getchannel('A'),clip));base.paste(im,(0,0),im);im=base;d=ImageDraw.Draw(im)
  for x,c in [(306,'#62d3c7'),(322,'#ad8cda'),(338,'#e2d65b')]:poly([(x,335),(x+5,329),(x+10,329),(x+5,335)],c)
  # Short wide rhythm stage, independent rectangular lamps, no rainbow perimeter.
  for x in range(100,382,16):line([(x,361),(x,432)],'#143027')
  for y in range(363,433,13):line([(100,y),(382,y)],'#143027')
  palette=[(184,61,255),(77,89,255),(0,190,255),(0,240,200),(75,248,58),(255,232,39),(255,148,27),(255,56,74)]
  for k in range(24):
   distance=abs(k-11.5)-.5
   target=8*audio.bands[min(11,round(distance))]
   height=max(0,min(8,self.columns[k].update(target,dt)))
   x=100+k*11.8
   for j in range(8):
    y=430-j*9
    level=max(0,min(1,height-j))
    # Slight hue offset per column enriches the palette without losing vertical color bands.
    import colorsys
    idx=min(7,j*7/max(3,height-1)); lo=int(idx); hi=min(7,lo+1); mix=idx-lo
    shade=[a+(z-a)*mix for a,z in zip(palette[lo],palette[hi])]
    hue,sat,val=colorsys.rgb_to_hsv(*(v/255 for v in shade))
    tone=colorsys.hsv_to_rgb((hue+.008*math.sin(k*.6))%1,sat,val)
    col=tuple(round(v*255*(.08+.92*level)) for v in tone)
    rect((x,y-6,x+8,y),col)
    if level>.65:
     rim=tuple(round(v+(255-v)*.28) for v in col)
     rect((x,y-6,x+8,y-5.5),rim)
   # No traveling white cap; columns rise and settle like the CPU chart.
  tx(240,451,('AUDIO / LIVE' if audio.status=='ready' else 'AUDIO / N/A'),9,'#88afa0')
  return im.resize((480,480),Image.Resampling.LANCZOS)


"""Cache repeated clock rasterization without changing robot rendering ownership."""
import math
from PIL import Image,ImageDraw
from collections import OrderedDict
from .render import Renderer as BaseRenderer
from .typography import RollingText

class CachedText(RollingText):
    """Cache settled digits over this renderer's unchanged background plate."""
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.tiles=OrderedDict()
    def draw(self,canvas,key,text,box,color,now):
        old,target,started=self.states.get(key,(None,None,now));cache_key=(key,text,box,color)
        if target==text and (old==target or now-started>=.35) and cache_key in self.tiles:
            canvas.paste(self.tiles[cache_key],box[:2]);self.tiles.move_to_end(cache_key);return
        super().draw(canvas,key,text,box,color,now)
        old,target,started=self.states[key]
        if old==target or now-started>=.35:
            x,y,w,h=box;self.tiles[cache_key]=canvas.crop((x,y,x+w,y+h))
            if len(self.tiles)>128:self.tiles.popitem(last=False)

class Renderer(BaseRenderer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.digits=CachedText(self.assets,self.digits.choice)
    def clock(self,im,wall):
        text=f'{wall:%H:%M} · {wall:%m/%d} · '+('MON','TUE','WED','THU','FRI','SAT','SUN')[wall.weekday()]
        if text!=getattr(self,'_clock_text',None):
            self._clock_text=text;self._clock_tiles=[]
            cx,cy,radius=627.43618541,592.12015285,460.48761044
            angle=math.atan2(575.1-cy,136.9-cx)%(2*math.pi);draw=ImageDraw.Draw(im)
            for index,char in enumerate(text):
                font=self.clock_variable if char.isdigit() or char.isalpha() else self.clockfont
                step=(draw.textlength(char,font=font)+2)/radius;angle+=step/2
                tile=Image.new('RGBA',(120,120));ImageDraw.Draw(tile).text((60,60),char,font=font,anchor='mm',fill='#ffe600' if index<5 else '#7fffd4')
                tile=tile.rotate(-(math.degrees(angle)+90),resample=Image.Resampling.BICUBIC)
                self._clock_tiles.append((tile,(round(cx+radius*math.cos(angle)-60),round(cy+radius*math.sin(angle)-60))))
                angle+=step/2
        for tile,position in self._clock_tiles:im.paste(tile,position,tile)

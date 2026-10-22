from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import math,time,datetime,sys
from .model import Spring

from .typography import RollingText
from .effects import TemperatureSheen
from .usage_chart import UsageChart,CPU,GPU
from .weather import WeatherPanel
from .robot import RobotAnimator

class Renderer:
    def __init__(self,assets=None,font_choice="born"):
        self.assets=Path(assets or (Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'assets'))
        self.background=Image.open(self.assets/'background.png').convert('RGB')
        self.clockfont=ImageFont.truetype(str(self.assets/'clock.otf'),33)
        self.ram_separator=Image.open(self.assets/'ram-separator.png').convert('RGBA')
        self.robot = RobotAnimator(self.assets)
        self.gauge_mask=Image.open(self.assets/'gauge-mask.png').convert('L')
        self.gauge_colors=Image.new('RGB',self.background.size)
        gd=ImageDraw.Draw(self.gauge_colors)
        # Fixed green/yellow/orange/red temperature scale, same segmented mask.
        stops=[(0,(0,255,184)),(.32,(174,255,35)),(.55,(255,230,32)),(.78,(255,148,25)),(1,(255,45,50))]
        for degree in range(180,361):
            fraction=(degree-180)/180
            for (a,ca),(b,cb) in zip(stops,stops[1:]):
                if a<=fraction<=b:
                    t=(fraction-a)/(b-a);color=tuple(round(x+(y-x)*t) for x,y in zip(ca,cb));break
            gd.pieslice((60,25,1195,1159),degree,degree+1,fill=color)
        self.digits=RollingText(self.assets,font_choice);self.springs={k:Spring() for k in ('cpu','gpu','ram','temperature')}
        self.clock_variable=self.digits.font(next(n for n in range(80,10,-1) if self.digits.font(n).getbbox('0')[3]-self.digits.font(n).getbbox('0')[1]<=self.clockfont.getbbox('0')[3]-self.clockfont.getbbox('0')[1]))
        self.charts={k:UsageChart() for k in ("cpu","gpu")}
        self.sheen=TemperatureSheen()
        self.weather=WeatherPanel(self.assets)
        self.last=None;self.history=[];self.last_sample=None
    def clock(self,im,wall):
        s=f'{wall:%H:%M} · {wall:%m/%d} · '+ ('MON','TUE','WED','THU','FRI','SAT','SUN')[wall.weekday()]
        cx,cy,R=627.43618541,592.12015285,460.48761044
        angle=math.atan2(575.1-cy,136.9-cx)%(2*math.pi)
        draw=ImageDraw.Draw(im)
        for i,ch in enumerate(s):
            font=self.clock_variable if ch.isdigit() or ch.isalpha() else self.clockfont
            step=(draw.textlength(ch,font=font)+2)/R;angle+=step/2
            tile=Image.new('RGBA',(120,120));ImageDraw.Draw(tile).text((60,60),ch,font=font,anchor='mm',fill='#ffe600' if i<5 else '#7fffd4')
            tile=tile.rotate(-(math.degrees(angle)+90),resample=Image.Resampling.BICUBIC)
            x,y=cx+R*math.cos(angle),cy+R*math.sin(angle)
            im.paste(tile,(round(x-60),round(y-60)),tile);angle+=step/2
    def render(self,samples,now=None,wall=None,size=480,weather=None):
        now=time.monotonic() if now is None else now;wall=wall or datetime.datetime.now()
        dt=1/30 if self.last is None else max(0,now-self.last);self.last=now
        values={k:v.current(now) for k,v in samples.items()}
        im=self.background.copy();d=ImageDraw.Draw(im)
        cpu,gpu,temp=(values.get(k) for k in ('cpu','gpu','temperature'))
        used,total=values.get('ram_used'),values.get('ram_total')
        ram=used/total*100 if used is not None and total and total>0 else None
        for key,target in [('cpu',cpu),('gpu',gpu),('ram',ram),('temperature',temp)]:
            self.springs[key].update(target if target is not None else 0,dt)
        # Only variable digits use the selected font. Units, decimal points,
        # separators and labels are preserved in the approved background.
        def parts(value):
            return ('--','-') if value is None else f'{max(0,value):.1f}'.split('.')
        ri,rf=parts(used);di,df=parts(values.get('download'));ui,uf=parts(values.get('upload'))
        for key,text,box,color in [
            ('temperature','--' if temp is None else str(round(temp)),(420,326,305,150),'#aaff23'),
            ('cpu','--' if cpu is None else f'{round(cpu)}',(107,773,110,68),'#13dce8'),
            ('gpu','--' if gpu is None else f'{round(gpu)}',(666,773,110,68),'#ff2fa8'),
            ('ram_integer',ri,(439,879,99,65),'#cb51ff'),
            ('ram_fraction',rf,(570,879,59,65),'#cb51ff'),
            ('ram_total','--' if total is None else f'{total:.0f}',(700,881,85,63),'#ffffff'),
            ('download_integer',di,(373,1044,71,43),'#00c4fa'),
            ('download_fraction',df,(460,1044,35,43),'#00c4fa'),
            ('upload_integer',ui,(741,1044,31,43),'#ff3543'),
            ('upload_fraction',uf,(788,1044,36,43),'#ff3543')]:
            self.digits.draw(im,key,text,box,color,now)
        d=ImageDraw.Draw(im)
        for key,x,y,bw,bh,n,color,valid in [('ram',244,963,762,32,19,'#bd4cef',ram)]:
            fraction=max(0,min(1,self.springs[key].value/100)) if valid is not None else 0
            sw=(bw-8*(n-1))/n
            for k in range(n):
                left=round(x+k*(sw+8));right=round(left+sw-1)
                d.rectangle((left,y,right,y+bh),fill=(24,67,52))
                edge=min(right,round(x+bw*fraction)-1)
                if edge>=left:d.rectangle((left,y,edge,y+bh),fill=color)
        for key,left,palette in [("cpu",33,CPU),("gpu",247,GPU)]:
            fresh=self.charts[key].update(samples.get(key),now,dt)
            self.charts[key].draw(im,left,palette,fresh)
        gauge=self.gauge_colors.point(lambda p:round(p*.23))
        if temp is not None:
            progress=max(0,min(100,self.springs['temperature'].value))
            active=Image.new('L',im.size);ImageDraw.Draw(active).pieslice((60,25,1195,1159),180,180+progress*1.8,fill=255)
            gauge.paste(self.gauge_colors,(0,0),active)
        im.paste(gauge,(0,0),self.gauge_mask)
        sample=samples.get('temperature')
        if sample and sample.timestamp!=self.last_sample:
            self.history.append(temp);self.history=self.history[-120:];self.last_sample=sample.timestamp
        # The curve is actual temperature history, gaps stay gaps.
        for x in range(195,1063,34):d.line((x,543,x,675),fill=(9,59,40))
        for y in range(543,676,33):d.line((195,y,1062,y),fill=(9,59,40))
        for x in range(265,1062,84):
            for y in range(549,675,15):d.line((x,y,x,y+5),fill=(160,171,32),width=2)
        pts=[]
        for i,v in enumerate(self.history):
            if v is None:
                if len(pts)>1:d.line(pts,fill='#31ffaf',width=4)
                pts=[];continue
            pts.append((1062-(len(self.history)-1-i)*867/119,670-max(0,min(100,v))*1.2))
        if len(pts)>1:d.line(pts,fill='#31ffaf',width=4)
        if pts:
            x,y=pts[-1];d.ellipse((x-6,y-6,x+6,y+6),fill='#ffe533')
        # Original-art in-betweens, fixed base and anchor.
        plate=Image.new('RGBA',im.size);pd=ImageDraw.Draw(plate)
        pd.ellipse((904,385,1036,517),fill=(0,24,16,255))
        grid=Image.new('RGBA',(132,132));gg=ImageDraw.Draw(grid)
        for pos in range(0,132,22):
            gg.line((pos,0,pos,132),fill=(7,51,35,255));gg.line((0,pos,132,pos),fill=(7,51,35,255))
        clip=Image.new('L',(132,132));ImageDraw.Draw(clip).ellipse((0,0,131,131),fill=255)
        plate.paste(grid,(904,385),clip)
        im.paste(plate,(0,0),plate)
        self.robot.draw(im,now)
        self.weather.draw(im,weather,now)
        self.clock(im,wall)
        phase=self.sheen.phase(now)
        if temp is not None:self.sheen.apply(im,phase)
        return im.resize((size,size),Image.Resampling.LANCZOS)

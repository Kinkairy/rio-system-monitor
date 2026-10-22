"""Approved code-drawn weather icons. Time is monotonic seconds, not frame counts."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from dataclasses import dataclass
from functools import lru_cache
import math

@dataclass(frozen=True)
class WeatherReading:
    kind: str | None = None
    temperature: float | None = None
    timestamp: float = 0
    source: str = "unconfigured"
    def fresh(self, now):
        return 0 <= now-self.timestamp <= 1800

def _clip(a):
    a=a.resize((48,48),Image.Resampling.LANCZOS) if a.size != (48,48) else a
    mask=Image.new('L',(48,48));ImageDraw.Draw(mask).ellipse((1,1,46,46),fill=255)
    a.putalpha(ImageChops.multiply(a.getchannel('A'),mask));return a


def cloud(seconds):
    i=seconds*12.5
    poses = [[(17, 26, 5), (23, 22, 6), (29, 26, 5)], [(8, 26, 5), (17, 23, 7), (28, 25, 6), (37, 27, 5)], [(16, 27, 7), (23, 18, 10), (30, 26, 7)], [(13, 24, 8), (23, 27, 5), (32, 27, 5)]]
    poses[0] = [poses[0][0], poses[0][1], poses[0][1], poses[0][2]]
    poses[2] = [poses[2][0], poses[2][1], poses[2][1], poses[2][2]]
    poses[3] = [poses[3][0], poses[3][0], poses[3][1], poses[3][2]]
    phase = i / 30
    index = int(phase) % 4
    u = phase - int(phase)
    u = max(0, min(1, (u - 0.2) / 0.65))
    u = u * u * (3 - 2 * u)
    lobes = [tuple((v + (w - v) * u for v, w in zip(a, b))) for a, b in zip(poses[index], poses[(index + 1) % 4])]
    mask = Image.new('L', (48, 48))
    d = ImageDraw.Draw(mask)
    left = min((x - r for x, y, r in lobes))
    right = max((x + r for x, y, r in lobes))
    bottom = max((y + r for x, y, r in lobes))
    d.rounded_rectangle((round(left + 3), 26, round(right - 3), round(bottom)), radius=3, fill=255)
    for x, y, r in lobes:
        d.ellipse(tuple((round(v) for v in (x - r, y - r, x + r, y + r))), fill=255)
    bounds = mask.getbbox()
    centered = Image.new('L', (48, 48))
    centered.paste(mask, (round(24 - (bounds[0] + bounds[2]) / 2), round(24 - (bounds[1] + bounds[3]) / 2)))
    mask = centered
    a = Image.new('RGBA', (48, 48))
    a.paste((221, 255, 239), (0, 0, 48, 48), mask)
    shifted = Image.new('L', (48, 48))
    shifted.paste(mask, (0, -2))
    edge = ImageChops.subtract(mask, shifted)
    a.paste((108, 205, 183), (0, 0, 48, 48), edge)
    return _clip(a)


def rain(seconds):
    i=seconds*20
    clip = Image.new('L', (48, 48))
    ImageDraw.Draw(clip).ellipse((1, 1, 46, 46), fill=255)
    a = Image.new('RGBA', (48, 48))
    d = ImageDraw.Draw(a)
    for x, offset, r, passes in [(9, 0.1, 2, 2), (20, 0.46, 3, 3), (32, 0.72, 4, 4), (39, 0.27, 2, 2), (15, 0.87, 2, 3)]:
        y = (i / 120 * passes + offset) % 1 * 74 - 18
        center = y + r * 1.5
        alpha = round(255 * max(0, min(1, (center + 1) / 7, (49 - center) / 7)))
        c = (52, 205 + 8 * r, 255, alpha)
        d.polygon([(x, y), (x - r, y + r * 1.8), (x + r, y + r * 1.8)], fill=c)
        d.ellipse((x - r, y + r, x + r, y + r * 3), fill=c)
        if r >= 3:
            d.line((x - 1, y + r + 1, x - 1, y + r * 2), fill=(204, 251, 255, alpha), width=1)
    a.putalpha(ImageChops.multiply(a.getchannel('A'), clip))
    return _clip(a)


def thunder(seconds):
    i=seconds*20
    clip = Image.new('L', (48, 48))
    ImageDraw.Draw(clip).ellipse((1, 1, 46, 46), fill=255)
    settings = [(22, 37, -8, (24, 24), 0), (13, 23, -18, (12, 19), 0.55), (14, 25, 4, (35, 29), 1.1)]
    t = i * 0.05
    a = Image.new('RGBA', (48, 48))
    for w, h, angle, (cx, cy), start in settings:
        dt = (t - start) % 1.65
        alpha = 0 if dt > 1.0 else min(1, dt / 0.1) * (1 - max(0, dt - 0.25) / 0.75)
        if alpha <= 0:
            continue
        tile = Image.new('RGBA', (40, 48))
        d = ImageDraw.Draw(tile)
        d.polygon([(23, 3), (7, 28), (19, 25), (13, 46), (35, 17), (23, 20), (30, 3)], fill=(255, round(209 + 46 * alpha), round(35 + 120 * alpha), round(255 * alpha)))
        tile = tile.resize((w, h), Image.Resampling.NEAREST).rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        a.alpha_composite(tile, (round(cx - tile.width / 2), round(cy - tile.height / 2)))
    a.putalpha(ImageChops.multiply(a.getchannel('A'), clip))
    return _clip(a)


def snow(seconds):
    i=seconds*12.5
    a = Image.new('RGBA', (192, 192))
    d = ImageDraw.Draw(a)
    angle = 2 * math.pi * i / 120
    def point(x, y, q):
        xx = x * math.cos(q) - y * math.sin(q)
        yy = x * math.sin(q) + y * math.cos(q)
        z = -xx * math.sin(angle)
        perspective = 95 / (95 - z)
        return (96 + 4 * xx * math.cos(angle) * perspective, 96 + 4 * yy * perspective)
    for k in range(6):
        q = k * math.pi / 3 - math.pi / 2
        d.line([point(0, 0, q), point(17, 0, q)], fill=(212, 251, 255), width=6)
        for dist, l in [(9, 4.5), (14, 3.5)]:
            for side in [-1, 1]:
                d.line([point(dist, 0, q), point(dist - l, side * l, q)], fill=(149, 232, 251), width=5)
    d.ellipse((91, 91, 101, 101), fill=(239, 255, 255))
    return _clip(a)


def fog(seconds):
    i=seconds*14.285714285714286
    p = 2 * math.pi * i / 100
    a = Image.new('RGBA', (192, 192))
    for j, (yy, ww) in enumerate([(14, 27), (24, 35), (34, 25)]):
        q = p + j * 2.1
        cx = 24 + 3 * math.sin(q)
        w = ww + 3 * math.sin(q + 0.7)
        h = 4.5 + 0.7 * math.cos(q)
        alpha = round(205 + 35 * math.sin(q + 1))
        d = ImageDraw.Draw(a)
        d.rounded_rectangle(((cx - w / 2) * 4, (yy - h / 2) * 4, (cx + w / 2) * 4, (yy + h / 2) * 4), radius=h * 2, fill=(181, 224, 221, alpha))
        d.rounded_rectangle(((cx - w * 0.37) * 4, (yy - h * 0.22) * 4, (cx + w * 0.37) * 4, (yy + h * 0.1) * 4), radius=3, fill=(224, 245, 236, alpha))
    glow = a.filter(ImageFilter.GaussianBlur(2))
    glow.alpha_composite(a)
    return _clip(glow)


def sun(seconds):
    t=seconds/4.02;strength=.5-.5*math.cos(2*math.pi*t)
    a=Image.new('RGBA',(48,48));d=ImageDraw.Draw(a)
    d.ellipse((9,9,39,39),fill=(255,191,28,round(40+165*strength)))
    a=a.filter(ImageFilter.GaussianBlur(6))
    ray=Image.new('RGBA',(192,192));rd=ImageDraw.Draw(ray)
    for group in (0,1):
        intensity=(.5+.5*math.cos(2*math.pi*t)) if group==0 else strength
        for angle in range(0,360,45):
            q=math.radians(angle+group*22.5)
            rd.line((96+60*math.cos(q),96+60*math.sin(q),96+84*math.cos(q),96+84*math.sin(q)),fill=(255,round(170+75*intensity),round(20+70*intensity),round(30+225*intensity)),width=6)
    a.alpha_composite(ray.resize((48,48),Image.Resampling.LANCZOS))
    core=Image.new('RGBA',(40,40));d=ImageDraw.Draw(core);r=9+strength
    d.ellipse((20-r,20-r,20+r,20+r),fill=(255,round(150+95*strength),round(20+100*strength),255))
    d.ellipse((14,13,23,21),fill=(255,round(200+55*strength),round(60+120*strength),255))
    a.alpha_composite(core.resize((48,48),Image.Resampling.NEAREST));return _clip(a)

DRAWERS={'sun':sun,'cloud':cloud,'rain':rain,'snow':snow,'thunder':thunder,'fog':fog}


def color(t):
    stops = [(-20, (45, 100, 255)), (9.99, (54, 182, 255)), (10, (66, 218, 204)), (15, (153, 234, 109)), (20, (255, 215, 64)), (20.01, (255, 117, 106)), (40, (255, 42, 53))]
    if t <= stops[0][0]:
        return stops[0][1]
    for (a, c), (b, e) in zip(stops, stops[1:]):
        if t <= b:
            p = (t - a) / (b - a)
            return tuple((round(v + (w - v) * p) for v, w in zip(c, e)))
    return stops[-1][1]

@lru_cache(maxsize=256)
def temperature(v,font_path):
 a=Image.new('RGBA',(192,192));d=ImageDraw.Draw(a);col=(127,160,150) if v is None else color(v)
 d.rounded_rectangle((30,51,49,116),radius=9,outline='#b6f9e9',width=5)
 d.ellipse((23,107,56,140),fill=col);d.line((39,77,39,121),fill=col,width=7)
 for yy in (62,77,92):d.line((52,yy,59,yy),fill='#b6f9e9',width=3)
 s='--' if v is None else str(round(v))
 for sz in range(117,12,-1):
  f=ImageFont.truetype(str(font_path),sz);b=d.textbbox((0,0),s,font=f)
  if b[2]-b[0]<=76:break
 d.text((105-(b[2]-b[0])/2-b[0],52-b[1]),s,font=f,fill=col)
 # Small degree + C, centered below the numeric column.
 d.ellipse((147,60,158,71),outline='#9cf53d',width=3)
 d.line([(166,83),(153,83),(153,105),(166,105)],fill='#9cf53d',width=6)
 d.line((76,133,155,133),fill='#9cf53d',width=9)
 result=_clip(a)
 ImageDraw.Draw(result).line((19,33,39,33),fill='#9cf53d',width=2)
 return result



class WeatherPanel:
    def __init__(self,assets):
        self.font_path=assets/'fonts'/'Born2bSporty.otf'
        self.start=None
    def draw(self,im,reading,now):
        if self.start is None:self.start=now
        elapsed=max(0,now-self.start);phase=elapsed%11.2
        valid=reading is not None and reading.fresh(now)
        kind=reading.kind if valid else None
        value=reading.temperature if valid else None
        if value is not None and (not math.isfinite(value) or not -100<=value<=70):value=None
        a=DRAWERS[kind](elapsed) if kind in DRAWERS else temperature(None,self.font_path)
        numeric=temperature(value,self.font_path)
        mix=0 if phase<7.68 else ((phase-7.68)/.32 if phase<8 else (1 if phase<10.88 else 1-(phase-10.88)/.32))
        a=Image.blend(a,numeric,max(0,min(1,mix)))
        scale=im.width/480
        size=round(48*scale);a=a.resize((size,size),Image.Resampling.NEAREST)
        im.paste(a,(round(93*scale),round(149*scale)),a)

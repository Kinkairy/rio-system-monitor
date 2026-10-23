"""Approved-art turn atlas, vector LED expressions and occasional picture dialogue.
No runtime SciPy/NumPy or replacement 3D model. Uses monotonic elapsed time.
"""
from PIL import Image, ImageDraw
import json, math, random

def expression(t):
    m = int(t / 3) % 8
    im = Image.new('RGBA', (160, 110))
    d = ImageDraw.Draw(im)
    g = '#00eba1'
    blink = max(0.1, 1 - math.exp(-((t % 3 - 2.45) / 0.07) ** 2))
    for j, x in enumerate([43, 118]):
        if m == 0 or (m == 1 and j == 1):
            d.line([(x - 14, 49), (x, 34), (x + 14, 49)], fill=g, width=6)
        elif m == 4:
            d.line((x - 13, 49, x + 13, 49), fill=g, width=5)
        elif m == 5:
            d.line([(x - 13, 37), (x, 47), (x + 13, 37)], fill=g, width=5)
        elif m == 6:
            pts = []
            for n in range(90):
                a = n / 89 * math.pi * 4 + t * 4
                r = 1 + n / 89 * 13
                pts.append((x + r * math.cos(a), 43 + r * math.sin(a)))
            d.line(pts, fill=g, width=4)
        else:
            h = (18 if m == 2 else 10 if m == 3 and j else 15) * blink
            d.rounded_rectangle((x - 8, 43 - h, x + 8, 43 + h), radius=6, fill=g)
    if m == 2 or m == 4:
        d.ellipse((72, 72, 88, 89), outline=g, width=4)
    elif m == 5:
        d.arc((67, 80, 92, 95), 180, 360, fill=g, width=4)
    elif m == 3:
        d.line((68, 84, 93, 78), fill=g, width=5)
    else:
        d.line([(65, 76), (73, 83), (84, 83), (94, 74)], fill=g, width=5)
    return im

def bubble(t):
    p = t % 3
    env = min(1, p / 0.25, max(0, (2.8 - p) / 0.25))
    if env <= 0:
        return None
    im = Image.new('RGBA', (220, 165))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 5, 210, 130), radius=28, fill='#ffe83e', outline='#142b20', width=6)
    d.polygon([(44, 125), (64, 153), (90, 125)], fill='#ffe83e')
    d.line([(44, 129), (64, 153), (88, 130)], fill='#142b20', width=5)
    m = int(t / 3) % 8
    c = '#173c2b'
    if m == 0:
        d.polygon([(110, 112), (65, 69), (65, 45), (84, 31), (104, 38), (110, 48), (120, 35), (140, 31), (157, 47), (157, 68)], fill='#ed5079')
    elif m == 1:
        d.rounded_rectangle((67, 63, 154, 111), radius=8, fill='#04a87d', outline=c, width=4)
        d.rectangle((61, 52, 160, 68), fill='#18d9a2')
        d.rectangle((103, 53, 118, 111), fill='#fff3a5')
        d.ellipse((77, 27, 111, 56), outline=c, width=7)
        d.ellipse((109, 27, 143, 56), outline=c, width=7)
    elif m == 2:
        d.ellipse((81, 25, 141, 84), fill='#fff8d0', outline=c, width=6)
        d.rectangle((96, 80, 126, 99), fill=c)
        d.rounded_rectangle((99, 103, 123, 112), radius=4, fill=c)
        for aa in range(0, 360, 60):
            z = math.radians(aa)
            d.line((111 + 40 * math.cos(z), 55 + 40 * math.sin(z), 111 + 50 * math.cos(z), 55 + 50 * math.sin(z)), fill=c, width=5)
    elif m == 3:
        d.ellipse((68, 25, 133, 90), fill='#74e5c6', outline=c, width=8)
        d.line((125, 82, 153, 111), fill=c, width=14)
        d.arc((80, 37, 119, 76), 190, 270, fill='#fff8c9', width=5)
    elif m == 4:
        d.ellipse((75, 24, 151, 108), fill=c)
        d.ellipse((103, 15, 166, 83), fill='#ffe83e')
        d.polygon([(65, 48), (70, 58), (80, 63), (70, 68), (65, 78), (60, 68), (50, 63), (60, 58)], fill='#fffbe0')
    elif m == 5:
        d.polygon([(112, 22), (82, 67), (79, 89), (91, 109), (113, 116), (135, 108), (145, 87), (140, 67)], fill='#20bad8', outline=c, width=4)
        d.arc((88, 62, 125, 103), 80, 170, fill='#d8fffd', width=7)
    elif m == 6:
        pts = []
        for n in range(150):
            angle = n / 149 * math.pi * 4.5 - t * 3
            rr = 3 + n / 149 * 43
            pts.append((110 + rr * math.cos(angle), 68 + rr * math.sin(angle)))
        d.line(pts, fill=c, width=10)
    else:
        for aa in range(0, 360, 72):
            z = math.radians(aa)
            x = 110 + 24 * math.cos(z)
            y = 66 + 24 * math.sin(z)
            d.ellipse((x - 19, y - 19, x + 19, y + 19), fill='#eb6b98', outline=c, width=3)
        d.ellipse((96, 52, 124, 80), fill='#fff6bd', outline=c, width=3)
    return im.resize((max(1, round(65 * env)), max(1, round(49 * env))), Image.Resampling.LANCZOS)

class RobotAnimator:
    def __init__(self, assets, rng=None):
        with Image.open(assets/'robot-turn-atlas.png') as source:
            atlas = source.convert('RGBA')
        self.meta = json.loads((assets/'robot-turn.json').read_text())
        self.tiles = [atlas.crop(((i%8)*128,(i//8)*96,(i%8+1)*128,(i//8+1)*96)) for i in range(62)]
        self.rng = rng or random.Random()
        self.started = None
        self.next_bubble = None
        self.bubble_started = None
        self.bubble_mood = 0

    @staticmethod
    def frame_index(elapsed):
        p = elapsed % 8
        def step(v): return min(30,max(0,round((.5-.5*math.cos(v*math.pi))*30)))
        if p < 1 or p >= 7: return 0
        if p < 2: return step(p-1)
        if p < 3: return 31+step(p-2)
        if p < 5: return 61
        if p < 6: return 61-step(p-5)
        return 30-step(p-6)

    def draw(self, image, now):
        if self.started is None or now < self.started:
            self.started = now
            self.next_bubble = now + self.rng.uniform(18,40)
            self.bubble_started = None
        elapsed = now-self.started
        index = self.frame_index(elapsed)
        tile = self.tiles[index].copy()
        # Slow expression rotation; blink and spiral use continuous timestamps.
        expression_time = elapsed*.5
        face = expression(expression_time).transform(tile.size, Image.Transform.PERSPECTIVE, self.meta['frames'][index]['face_transform'], Image.Resampling.BICUBIC)
        tile.alpha_composite(face)
        image.paste(tile,(906,403),tile)
        if now >= self.next_bubble:
            self.bubble_started = now
            self.bubble_mood = int(expression_time/3)%8
            self.next_bubble = now + 3 + self.rng.uniform(18,40)
        if self.bubble_started is not None:
            age = now-self.bubble_started
            if 0 <= age < 3:
                art = bubble(self.bubble_mood*3+age)
                if art is not None: image.paste(art,(992,420-art.height),art)
            else:
                self.bubble_started = None

"""Centered pop and gentle overshoot shared by both live display views."""
from PIL import Image,ImageDraw


def pop_scale(progress):
    p=max(0,min(1,progress))-1
    return .72+.28*(1+3.6*p**3+2.6*p**2)


class ViewTransition:
    def __init__(self,duration=.55):
        self.duration=duration;self.view=None;self.started=0;self.outgoing=None;self.last=None

    def render(self,view,frame,now):
        if self.view is None:
            self.view=view
        elif view!=self.view:
            self.view=view;self.started=now;self.outgoing=self.last
        progress=(now-self.started)/self.duration
        if self.outgoing is None or now>=self.started+self.duration:
            self.outgoing=None;self.last=frame;return frame
        if progress<=0:return self.last
        size=tuple(max(1,round(edge*pop_scale(progress))) for edge in frame.size)
        incoming=frame.resize(size,Image.Resampling.BICUBIC)
        mask=Image.new('L',size);ImageDraw.Draw(mask).ellipse((0,0,size[0]-1,size[1]-1),fill=255)
        canvas=self.outgoing.copy()
        canvas.paste(incoming,tuple((a-b)//2 for a,b in zip(frame.size,size)),mask)
        self.last=Image.blend(self.outgoing,canvas,min(1,progress/.22))
        return self.last

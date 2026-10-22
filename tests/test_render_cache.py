import datetime,unittest
from pathlib import Path
from PIL import Image,ImageChops
from rio_monitor.render import Renderer as Original
from rio_monitor.render_cache import Renderer

@unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/background.png').is_file(),'Private artwork unavailable')
class ClockCacheTests(unittest.TestCase):
    def test_cached_clock_preserves_pixels_and_updates_at_minute_boundary(self):
        original=Original();cached=Renderer()
        for wall in (datetime.datetime(2026,10,23,10,59),datetime.datetime(2026,10,23,10,59,30),datetime.datetime(2026,10,23,11,0)):
            a=Image.new('RGB',(1280,1280),'#123456');b=a.copy()
            original.clock(a,wall);cached.clock(b,wall)
            self.assertIsNone(ImageChops.difference(a,b).getbbox())
    def test_cached_digits_preserve_pixels_during_changes_and_after_settling(self):
        from rio_monitor.typography import RollingText
        from rio_monitor.render_cache import CachedText
        original=Original();plain=RollingText(original.assets);cached=CachedText(original.assets)
        for now,text in ((0,'32'),(.1,'32'),(.4,'68'),(.5,'68'),(.8,'68'),(.9,'68'),(1,'32'),(1.1,'32'),(1.5,'32')):
            a=Image.new('RGB',(400,100),'#123456');b=a.copy();box=(10,10,110,68)
            plain.draw(a,'cpu',text,box,'#13dce8',now);cached.draw(b,'cpu',text,box,'#13dce8',now)
            self.assertIsNone(ImageChops.difference(a,b).getbbox())

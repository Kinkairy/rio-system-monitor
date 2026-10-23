import unittest,tempfile,io
from pathlib import Path
from PIL import Image
from rio_monitor.music.renderer import MusicRenderer
from rio_monitor.music.state import Track,Audio
class RecordTests(unittest.TestCase):
 def snapshot(self,cover=b'',playing=False):return dict(track=Track(title='Song',artist='Artist',cover=cover,position=1,duration=180,observed=1,playing=playing),audio=Audio(observed=1),rows=(),lyric_status='off')
 def assets(self,root):
  p=Path(root)/'music';p.mkdir();Image.new('RGBA',(222,222),'blue').save(p/'default-record.png');Image.new('RGBA',(74,74),'lime').save(p/'record-label.png')
 def test_missing_or_corrupt_cover_uses_whole_private_record(self):
  with tempfile.TemporaryDirectory() as root:
   self.assets(root);r=MusicRenderer(root)
   for cover in (b'',b'invalid'):
    im=r.render(self.snapshot(cover),1);self.assertEqual(im.getpixel((160,246)),(0,0,255));self.assertIsNone(r.cover_for(self.snapshot(cover)['track']))
 def test_valid_cover_kept_and_private_label_replaces_plain_circle(self):
  with tempfile.TemporaryDirectory() as root:
   self.assets(root);r=MusicRenderer(root);buf=io.BytesIO();Image.new('RGB',(100,100),'red').save(buf,format='PNG')
   im=r.render(self.snapshot(buf.getvalue()),1)
   self.assertEqual(im.getpixel((160,246)),(0,255,0));self.assertEqual(im.getpixel((160,186)),(255,0,0))
   self.assertEqual(im.getpixel((160,140)),(0,0,255))  # The supplied record remains underneath a valid cover.
 def test_missing_private_art_still_renders_and_cache_is_bounded(self):
  with tempfile.TemporaryDirectory() as root:
   r=MusicRenderer(root)
   self.assertEqual(r.render(self.snapshot(),1).size,(480,480))
   for i in range(10):r.cover_for(Track(title=str(i)))
   self.assertLessEqual(len(r.covers),3)
 def test_default_rotates_only_when_playing(self):
  with tempfile.TemporaryDirectory() as root:
   r=MusicRenderer(root);r.render(self.snapshot(playing=True),1);a=r.angle;r.render(self.snapshot(playing=False),1.1);self.assertEqual(a,r.angle)
   r.render(self.snapshot(playing=True),1.2);self.assertGreater(r.angle,a)

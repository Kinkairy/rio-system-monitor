import unittest,random
from PIL import Image,ImageChops
from rio_monitor.effects import TemperatureSheen
class EffectTests(unittest.TestCase):
 def test_random_idle_and_duration(self):
  e=TemperatureSheen(random.Random(7))
  self.assertIsNone(e.phase(0));self.assertTrue(20<=e.next_at<=40)
  start=e.next_at
  self.assertEqual(e.phase(start),0)
  self.assertAlmostEqual(e.phase(start+.75),.5)
  self.assertIsNone(e.phase(start+1.5))
  self.assertTrue(20<=e.next_at-(start+1.5)<=40)
 def test_highlight_stays_on_lime_glyphs(self):
  im=Image.new('RGB',(1254,1254),(0,24,16));before=im.copy()
  TemperatureSheen.apply(im,.5);self.assertIsNone(ImageChops.difference(im,before).getbbox())
  im.paste((170,255,35),(570,360,650,430));before=im.copy()
  TemperatureSheen.apply(im,.5)
  bbox=ImageChops.difference(im,before).getbbox()
  self.assertIsNotNone(bbox);self.assertGreaterEqual(bbox[0],570);self.assertLessEqual(bbox[2],650)

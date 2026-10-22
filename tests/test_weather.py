import unittest,math
from pathlib import Path
from PIL import Image,ImageChops
from rio_monitor.weather import DRAWERS,WeatherReading,WeatherPanel,color,temperature
from rio_monitor.weather_source import kind_for,coordinates
class WeatherTests(unittest.TestCase):
 def test_all_icons_have_bounded_alpha(self):
  for k,fn in DRAWERS.items():
   for t in (0,.13,.7,2,7.9,29):
    a=fn(t);self.assertEqual(a.size,(48,48));self.assertEqual(a.mode,'RGBA')
    self.assertEqual(a.getpixel((0,0))[3],0)
 def test_stale_and_future(self):
  r=WeatherReading('sun',24,100)
  self.assertTrue(r.fresh(101));self.assertFalse(r.fresh(99));self.assertFalse(r.fresh(1901))
 def test_mapping_and_invalid(self):
  self.assertEqual(kind_for(95),'thunder');self.assertEqual(kind_for(73),'snow');self.assertIsNone(kind_for(999))
  with self.assertRaises(ValueError):coordinates({'latitude':float('nan'),'longitude':0})
 def test_color_boundaries(self):
  self.assertGreater(color(9)[2],color(9)[0]);self.assertGreater(color(21)[0],color(21)[2])
  self.assertEqual(color(20),(255,215,64))
 @unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/fonts/Born2bSporty.otf').is_file(),'Private font unavailable')
 def test_temperature_range_and_units(self):
  font=Path(__file__).resolve().parents[1]/'assets/fonts/Born2bSporty.otf'
  for v in (None,-45,-1,0,9,10,20,21,45):self.assertEqual(temperature(v,font).size,(48,48))
  a,b=temperature(2,font),temperature(30,font)
  self.assertEqual(a.getpixel((30,33)),b.getpixel((30,33)))
 @unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/fonts/Born2bSporty.otf').is_file(),'Private font unavailable')
 def test_panel_is_only_local(self):
  assets=Path(__file__).resolve().parents[1]/'assets';p=WeatherPanel(assets)
  im=Image.new('RGB',(480,480));p.draw(im,WeatherReading('sun',24,0),0)
  box=im.getbbox();self.assertTrue(box[0]>=93 and box[2]<=141)

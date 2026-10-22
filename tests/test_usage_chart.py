import unittest
from PIL import Image
from rio_monitor.usage_chart import UsageChart,CPU
from rio_monitor.model import Sample
class UsageTests(unittest.TestCase):
 def test_bounce_settles_without_changing_history(self):
  c=UsageChart();s=Sample(60,0);seen=[]
  for i in range(180):
   fresh=c.update(s,i/60,1/60);seen.append(c.springs[-1].value)
   c.draw(Image.new('RGB',(480,480)),33,CPU,fresh)
  self.assertGreater(max(seen),62);self.assertAlmostEqual(seen[-1],60,places=2)
  self.assertEqual(c.values,[None]*8+[60])
 def test_stale_is_not_a_fake_zero_sample(self):
  c=UsageChart();s=Sample(40,0);c.update(s,0,.016)
  self.assertFalse(c.update(s,6,.016));self.assertEqual(c.values[-1],40)

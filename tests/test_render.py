import unittest,datetime
from pathlib import Path
from rio_monitor.render import Renderer
from rio_monitor.model import Sample
class RenderTests(unittest.TestCase):
 @unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/background.png').is_file(),'Private artwork unavailable')
 def test_missing_and_overflow(self):
  renderer=Renderer(Path(__file__).resolve().parents[1]/'assets')
  for value in (None,0,100,999999):
   samples={k:Sample(value,10) for k in ['cpu','gpu','temperature','ram_used','ram_total','upload','download']}
   frame=renderer.render(samples,now=10,wall=datetime.datetime(2026,10,22,14,30))
   self.assertEqual(frame.size,(480,480))
   self.assertEqual(frame.mode,'RGB')
 def test_real_counter_render(self):
  from rio_monitor.telemetry import Collector
  c=Collector();s=c.collect()
  self.assertIn('cpu',s);self.assertGreater(s['ram_total'].value,0)
  self.assertIsNone(s['download'].value)
  c.gpu.close()

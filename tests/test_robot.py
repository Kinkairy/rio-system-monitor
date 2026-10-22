import unittest,random,hashlib,json,math
from pathlib import Path
from PIL import Image
from rio_monitor.robot import RobotAnimator,bubble,expression
ASSETS=Path(__file__).resolve().parents[1]/'assets'
@unittest.skipUnless((ASSETS/'robot-turn-atlas.png').is_file(),'Private animation assets are required')
class RobotTests(unittest.TestCase):
 def test_original_assets_unchanged(self):
  meta=json.loads((ASSETS/'robot-turn.json').read_text())
  for name,digest in meta['source_sha256'].items():self.assertEqual(hashlib.sha256((ASSETS/name).read_bytes()).hexdigest(),digest)
 def test_atlas_and_transforms(self):
  r=RobotAnimator(ASSETS)
  self.assertEqual(len(r.tiles),62)
  for frame in r.meta['frames']:self.assertTrue(all(math.isfinite(x) for x in frame['face_transform']))
 def test_turn_anchors_and_loop(self):
  f=RobotAnimator.frame_index
  for t,i in [(0,0),(2,31),(3,61),(5,61),(6,30),(7,0),(8,0)]:self.assertEqual(f(t),i)
  self.assertGreaterEqual(len({f(1+i/30) for i in range(31)}),24)
  seq=[f(1+i/30) for i in range(30)]
  self.assertEqual(seq,sorted(seq))
 def test_dialogue_random_interval(self):
  r=RobotAnimator(ASSETS,random.Random(7));im=Image.new('RGB',(1254,1254))
  r.draw(im,10);self.assertTrue(28<=r.next_bubble<=50);self.assertIsNone(r.bubble_started)
  due=r.next_bubble;r.draw(im,due);self.assertEqual(r.bubble_started,due)
  self.assertTrue(21<=r.next_bubble-due<=43)
  r.draw(im,due+3.1);self.assertIsNone(r.bubble_started)
 def test_picture_dialogue_and_expressions(self):
  self.assertEqual(len({bubble(i*3+1).tobytes() for i in range(8)}),8)
  self.assertEqual(len({expression(i*3+1).tobytes() for i in range(8)}),8)
 def test_draw_stays_in_robot_region(self):
  im=Image.new('RGB',(1254,1254));r=RobotAnimator(ASSETS,random.Random(1));r.draw(im,0);r.draw(im,r.next_bubble+1)
  x0,y0,x1,y1=im.getbbox();self.assertGreaterEqual(x0,900);self.assertLessEqual(x1,1060);self.assertGreaterEqual(y0,365);self.assertLessEqual(y1,500)

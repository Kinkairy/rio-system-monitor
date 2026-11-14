import json,os,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
from rio_monitor.settings import Settings,load,save,config_path
from rio_monitor.storage import DisplaySession
from rio_monitor.display_protocols import LEGACY
from rio_monitor.lt168b_display import BENCH

class CalibrationTests(unittest.TestCase):
 def test_old_and_invalid_calibration_keep_preferences(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   p=config_path();p.parent.mkdir(parents=True)
   for offsets in (None,[],233,{'lt168b-rio-bench':True,'bad':360,'negative':-1,'float':2.5,'str':'233','':4}):
    p.write_text(json.dumps({'rotation':39,'language':'zh','rotation_offsets':offsets}))
    s=load();self.assertEqual((s.rotation,s.language,s.rotation_offsets),(39,'zh',{}))
   p.write_text('{"rotation":39}')
   self.assertEqual((load().rotation,load().rotation_offsets),(39,{}))
 def test_calibration_survives_reload_and_slider_change(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LOCALAPPDATA':d}):
   save(Settings(rotation=0,rotation_offsets={BENCH.protocol:233}))
   s=load();self.assertEqual(s.rotation,0);self.assertEqual(s.rotation_offsets,{BENCH.protocol:233})
   s.rotation=5;save(s);self.assertEqual(load().rotation_offsets,{BENCH.protocol:233})
   self.assertEqual(load().rotation,5)
 def test_defaults_do_not_share_a_dictionary(self):
  a,b=Settings(),Settings();a.rotation_offsets[BENCH.protocol]=233;self.assertEqual(b.rotation_offsets,{})
 def test_zero_preserves_current_233_pixels_and_protocol_switch(self):
  image=Image.new('RGB',(480,480))
  image.paste((230,10,90),(35,45,160,130));image.paste((30,200,70),(280,230,440,420))
  session=DisplaySession();sent=[]
  session.output=SimpleNamespace(error=None,capabilities=BENCH,submit=sent.append)
  offsets={BENCH.protocol:233}
  for relative in (0,5,127,359):
   session.submit(image,relative,offsets)
   self.assertEqual(sent[-1].tobytes(),image.rotate(-((233+relative)%360)).tobytes())
  self.assertIs(sent[2],image)  # 233+127 wraps to the original, with no sampling.
  session.output.capabilities=LEGACY
  session.submit(image,0,offsets);self.assertIs(sent[-1],image)
  session.submit(image,90,offsets);self.assertEqual(sent[-1].tobytes(),image.rotate(-90).tobytes())
  session.output.capabilities=BENCH  # Reconnection selects its own calibration again.
  session.submit(image,0,offsets);self.assertEqual(sent[-1].tobytes(),image.rotate(-233).tobytes())
 def test_combined_rotation_is_applied_once(self):
  frame=Mock();submit=Mock();session=DisplaySession()
  session.output=SimpleNamespace(error=None,capabilities=BENCH,submit=submit)
  session.submit(frame,5,{BENCH.protocol:233})
  frame.rotate.assert_called_once_with(-238);submit.assert_called_once_with(frame.rotate.return_value)
 def test_disconnected_or_failed_output_does_not_rotate(self):
  frame=Mock();session=DisplaySession();session.submit(frame,0,{BENCH.protocol:233})
  session.output=SimpleNamespace(error='offline',submit=Mock())
  session.submit(frame,0,{BENCH.protocol:233});frame.rotate.assert_not_called();session.output.submit.assert_not_called()

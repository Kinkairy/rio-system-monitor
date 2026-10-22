import unittest,struct,math
from rio_monitor.model import Sample,Spring
from rio_monitor.protocol import frame_command,validate_status,FrameSender,ProtocolError
class Tests(unittest.TestCase):
 def test_freshness(self):
  self.assertEqual(Sample(0,10).current(11),0)
  self.assertIsNone(Sample(7,10).current(16))
  self.assertIsNone(Sample(float('nan'),10).current(11))
  self.assertIsNone(Sample(1,10).current(9))
 def test_spring(self):
  s=Spring()
  for _ in range(240):s.update(100,1/60)
  self.assertAlmostEqual(s.value,100,places=2)
  self.assertTrue(math.isfinite(s.update(0,99)))
 def test_command(self):
  p=frame_command(bytes(480*480*2),42)
  self.assertEqual(len(p),31)
  self.assertEqual(p[:4],b'USBC')
  self.assertEqual(p[15],0xcd)
  self.assertEqual(p[20:22],b'\x06\x12')
  self.assertEqual(p[22:26],bytes(4))
  self.assertEqual(p[26:30],struct.pack('<HH',479,479))
 def test_status(self):
  validate_status(struct.pack('<4sIIB',b'USBS',1,0,0),1)
  for sig,tag,res,status in [(b'BAD!',1,0,0),(b'USBS',2,0,0),(b'USBS',1,1,0),(b'USBS',1,0,1)]:
   with self.assertRaises(ProtocolError):validate_status(struct.pack('<4sIIB',sig,tag,res,status),1)
 def test_fault_latches(self):
  class T:
   def write(self,ep,data):return 0
  f=FrameSender(T())
  with self.assertRaises(ProtocolError):f.send(bytes(480*480*2))
  self.assertTrue(f.faulted)
if __name__=='__main__':unittest.main()

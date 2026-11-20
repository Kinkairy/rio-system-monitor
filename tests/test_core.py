import unittest,struct,math
from rio_monitor.model import Sample, Spring, TemperatureDisplay
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
class TemperatureDisplayTests(unittest.TestCase):
    def test_short_jump_is_damped_and_sustained_heat_is_followed(self):
        display = TemperatureDisplay()
        self.assertEqual(display.update(Sample(53, 10), 10), 53)
        jumped = display.update(Sample(75, 11.5), 11.5)
        self.assertTrue(53 < jumped < 60)
        sustained = [display.update(Sample(75, at), at) for at in range(12, 28)]
        self.assertEqual(sustained, sorted(sustained))
        self.assertTrue(73 < sustained[-1] < 75)

    def test_repeated_frames_do_not_lerp_the_same_sample_again(self):
        display = TemperatureDisplay()
        display.update(Sample(53, 10), 10)
        sample = Sample(75, 11.5)
        value = display.update(sample, 11.5)
        for frame_time in (11.6, 11.9, 12, 12.4, 12.9):
            self.assertEqual(display.update(sample, frame_time), value)

    def test_stale_gap_and_sensor_change_start_with_a_fresh_sample(self):
        display = TemperatureDisplay()
        display.update(Sample(48, 10, 'CPU Package'), 10)
        self.assertEqual(display.update(Sample(70, 11, 'Windows'), 11), 70)
        self.assertIsNone(display.update(Sample(65, 12, 'Windows'), 18))
        self.assertEqual(display.update(Sample(56, 19, 'Windows'), 19), 56)
        self.assertEqual(display.update(Sample(71, 25, 'Windows'), 25), 71)
        self.assertIsNone(display.update(Sample(None, 26, 'Windows'), 26))
        self.assertEqual(display.update(Sample(52, 27, 'Windows'), 27), 52)


if __name__=='__main__':unittest.main()

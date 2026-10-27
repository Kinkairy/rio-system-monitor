import queue,struct,threading,unittest
from unittest.mock import Mock,patch
from PIL import Image
from rio_monitor.protocol import FrameSender,ProtocolError
from rio_monitor.output import ScreenOutput

class Clock:
 def __init__(self,events,stop_at_wait=False):self.now=0;self.stopped=False;self.events=events;self.stop_at_wait=stop_at_wait
 def is_set(self):return self.stopped
 def set(self):self.stopped=True
 def wait(self,n):
  self.events.append(('wait',n));self.now+=n
  if self.stop_at_wait:self.set()
  return self.stopped

class LiveInitializationTests(unittest.TestCase):
 def test_oem_query_is_cd03_in_with_five_bytes_and_checked_status(self):
  transport=Mock();transport.write.side_effect=lambda ep,data:len(data)
  transport.read.side_effect=[bytes.fromhex('e001e001ff'),bytes.fromhex('55534253010000000500000000')]
  self.assertEqual(FrameSender(transport).lcd_info(),(480,480,255))
  ep,command=transport.write.call_args.args
  self.assertEqual(ep,1);self.assertEqual(command,struct.pack('<4sIIBBB16s',b'USBC',1,5,128,0,16,bytes.fromhex('cd000000000300000000000000000000')))
  self.assertEqual(transport.read.call_args_list,[unittest.mock.call(129,5),unittest.mock.call(129,13)])
 def test_bad_query_reply_latches_and_forbids_any_frame(self):
  for data,status in [(b'bad',bytes(13)),(bytes.fromhex('e001e001ff'),bytes.fromhex('55534253020000000500000000')),(bytes.fromhex('e001e001ff'),bytes.fromhex('55534253010000000500000001')),(struct.pack('<HHB',240,240,0),bytes.fromhex('55534253010000000500000000'))]:
   transport=Mock();transport.write.side_effect=lambda ep,data:len(data);transport.read.side_effect=[data,status];sender=FrameSender(transport)
   with self.assertRaises(ProtocolError):sender.lcd_info()
   with self.assertRaises(ProtocolError):sender.send(bytes(460800))
   self.assertEqual(transport.write.call_count,1)
 def output(self,stop_at_wait=False,query_error=None):
  events=[];clock=Clock(events,stop_at_wait);out=ScreenOutput.__new__(ScreenOutput)
  out.frames=queue.Queue(1);out.stop=clock;out.finished=threading.Event();out.path='test';out.sent=0;out.error=None;out.submit(Image.new('RGB',(480,480)))
  sender=Mock()
  def query():
   events.append(('query',clock.now))
   if query_error:raise query_error
  sender.lcd_info.side_effect=query
  def send(raw):events.append(('frame',clock.now));clock.set()
  sender.send.side_effect=send
  with patch('rio_monitor.output.WinUSB') as usb,patch('rio_monitor.output.FrameSender',return_value=sender),patch('rio_monitor.output.time.monotonic',side_effect=lambda:clock.now):out.run()
  usb.return_value.close.assert_called_once();self.assertTrue(out.finished.is_set())
  return out,events,sender
 def test_first_frame_waits_for_one_second_after_query(self):
  out,events,sender=self.output();self.assertEqual(events[:2],[('query',0),('wait',1.0)]);self.assertIn(('frame',1.0),events);self.assertEqual(out.sent,1)
 def test_exit_during_initialization_sends_no_frame(self):
  out,events,sender=self.output(True);sender.send.assert_not_called();self.assertIsNone(out.error)
 def test_failed_initialization_sends_no_frame(self):
  out,events,sender=self.output(query_error=ProtocolError('bad reply'));sender.send.assert_not_called();self.assertEqual(out.error,'bad reply')

if __name__=='__main__':unittest.main()

import queue
import threading
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from rio_monitor.output import ScreenOutput


class ClockStop:
    def __init__(self):
        self.now=0.;self.stopped=False;self.waits=[];self.on_wait=None
    def is_set(self):return self.stopped
    def set(self):self.stopped=True
    def wait(self,delay):
        self.waits.append(delay)
        if self.on_wait:self.on_wait(delay)
        if not self.stopped:self.now+=delay
        return self.stopped


class OutputPacingTests(unittest.TestCase):
    def setUp(self):
        delay=patch.object(ScreenOutput,'initialization_delay',0);delay.start();self.addCleanup(delay.stop)

    def run_output(self,latencies=(0.,0.,0.),on_wait=None):
        clock=ClockStop();clock.on_wait=on_wait
        output=ScreenOutput.__new__(ScreenOutput)
        output.frames=queue.Queue(maxsize=1);output.stop=clock
        output.finished=threading.Event();output.path='mock';output.sent=0;output.error=None
        output.submit(Image.new('RGB',(480,480),'red'))
        starts=[];pixels=[]
        def send(payload):
            starts.append(clock.now);pixels.append(payload)
            clock.now+=latencies[len(starts)-1]
            if len(starts)==len(latencies):clock.set()
            else:output.submit(Image.new('RGB',(480,480),'red'))
        sender=Mock();sender.send.side_effect=send
        with patch('rio_monitor.output.WinUSB') as usb,patch('rio_monitor.output.FrameSender',return_value=sender),patch('rio_monitor.output.time.monotonic',side_effect=lambda:clock.now):
            output.run()
        self.assertIsNone(output.error);self.assertTrue(output.finished.is_set())
        usb.return_value.close.assert_called_once();usb.return_value.reset_pipes.assert_not_called()
        return output,clock,starts,pixels

    def test_full_frames_start_at_most_twelve_per_second(self):
        output,clock,starts,pixels=self.run_output()
        self.assertEqual(output.sent,3)
        for got,want in zip(starts,(0.,1/12,2/12)):self.assertAlmostEqual(got,want)
        self.assertTrue(all(p==bytes.fromhex('f800')*230400 for p in pixels))

    def test_slow_transfer_does_not_create_a_catchup_burst(self):
        _,_,starts,_=self.run_output((.2,0.,0.))
        self.assertEqual(starts[:2],[0.,.2]);self.assertAlmostEqual(starts[2],.2+1/12)

    def test_wait_uses_latest_frame_and_does_not_hold_an_old_one(self):
        clock=ClockStop();output=ScreenOutput.__new__(ScreenOutput)
        output.frames=queue.Queue(maxsize=1);output.stop=clock;output.finished=threading.Event()
        output.path='mock';output.sent=0;output.error=None
        output.submit(Image.new('RGB',(480,480),'red'));pixels=[]
        def send(payload):
            pixels.append(payload)
            if len(pixels)==1:output.submit(Image.new('RGB',(480,480),'red'))
            else:clock.set()
        def during_wait(delay):
            if delay:output.submit(Image.new('RGB',(480,480),'blue'))
        clock.on_wait=during_wait;sender=Mock();sender.send.side_effect=send
        with patch('rio_monitor.output.WinUSB'),patch('rio_monitor.output.FrameSender',return_value=sender),patch('rio_monitor.output.time.monotonic',side_effect=lambda:clock.now):output.run()
        self.assertIsNone(output.error)
        self.assertEqual(pixels,[bytes.fromhex('f800')*230400,bytes.fromhex('001f')*230400])

    def test_stop_during_pacing_wait_does_not_send_another_frame(self):
        clock=ClockStop();output=ScreenOutput.__new__(ScreenOutput)
        output.frames=queue.Queue(maxsize=1);output.stop=clock;output.finished=threading.Event()
        output.path='mock';output.sent=0;output.error=None
        output.submit(Image.new('RGB',(480,480)))
        clock.on_wait=lambda delay:clock.set() if delay else None
        sender=Mock();sender.send.side_effect=lambda p:output.submit(Image.new('RGB',(480,480)))
        with patch('rio_monitor.output.WinUSB') as usb,patch('rio_monitor.output.FrameSender',return_value=sender),patch('rio_monitor.output.time.monotonic',side_effect=lambda:clock.now):output.run()
        self.assertEqual(output.sent,1);self.assertTrue(output.finished.is_set());self.assertIsNone(output.error)
        usb.return_value.close.assert_called_once()

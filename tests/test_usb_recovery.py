"""USB failure paths use real protocol/worker code and never open hardware."""
import ctypes
import logging
import queue
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from rio_monitor import output, winusb
from rio_monitor.protocol import FrameSender, ProtocolError
from rio_monitor.storage import DisplaySession


class Transport:
    def __init__(self, name, events, fail=None, geometry=(480,480), status=0, revision=0x0200, stop=None):
        self.name=name;self.events=events;self.fail=fail;self.geometry=geometry
        self.status=status;self.revision=revision;self.stop=stop;self.kind=None;self.tag=0;self.length=0
    def event(self, stage):
        self.events.append((self.name,stage))
        if stage==self.fail:raise OSError(121,'simulated USB timeout')
    def write(self, ep, payload):
        if len(payload)==31 and payload.startswith(b'USBC'):
            _,self.tag,self.length,_,_,_,cdb=struct.unpack('<4sIIBBB16s',payload)
            self.kind='lcd_info' if cdb[5]==3 else 'frame'
            self.event(self.kind+'.command')
        else:self.event('frame.pixels')
        return len(payload)
    def read(self, ep, count):
        stage='lcd_info.reply' if count==5 else self.kind+'.status'
        self.event(stage)
        if count==5:return struct.pack('<HHB',*self.geometry,255)
        if self.kind=='frame' and self.stop:self.stop.set()
        return struct.pack('<4sIIB',b'USBS',self.tag,self.length,self.status)
    def device_descriptor(self):
        self.event('descriptor');data=bytearray(18);data[:2]=b'\x12\x01'
        struct.pack_into('<HHH',data,8,0x2a55,0x9990,self.revision)
        return bytes(data)
    def reset_pipes(self):self.event('reset')
    def close(self):self.event('close')


def worker():
    result=output.ScreenOutput.__new__(output.ScreenOutput)
    result.path='test-only';result.frames=queue.Queue(maxsize=1);result.stop=threading.Event()
    result.finished=threading.Event();result.error=None;result.sent=0
    result.submit(Image.new('RGB',(480,480),'red'))
    return result


class USBRecoveryTests(unittest.TestCase):
    def run_worker(self, first_options=None, second_options=None):
        result=worker();events=[]
        first=Transport('first',events,stop=result.stop,**(first_options or {}))
        second=Transport('second',events,stop=result.stop,**(second_options or {}))
        def open_transport(path):
            name='first' if not events else 'second';events.append((name,'open'))
            return first if name=='first' else second
        with patch.object(output,'WinUSB',side_effect=open_transport) as opened,patch.object(output.ScreenOutput,'initialization_delay',0):
            result.run()
        self.assertTrue(result.finished.is_set())
        return result,events,opened.call_count

    def test_query_timeout_never_bypasses_initialization_or_flushes_late_data(self):
        for stage in ('lcd_info.reply','lcd_info.status'):
            result,events,opens=self.run_worker({'fail':stage})
            self.assertIsNotNone(result.error);self.assertEqual(result.sent,0);self.assertEqual(opens,1)
            self.assertNotIn(('first','reset'),events)
            self.assertFalse(any(event=='frame.command' for _,event in events))
            self.assertEqual(events[-1],('first','close'))

    def test_normal_query_initialization_is_preserved(self):
        result,events,opens=self.run_worker()
        self.assertIsNone(result.error);self.assertEqual(result.sent,1);self.assertEqual(opens,1)
        self.assertLess(events.index(('first','lcd_info.status')),events.index(('first','frame.command')))
        self.assertNotIn(('first','reset'),events)

    def test_write_timeout_wrong_size_and_bad_status_send_no_frame(self):
        for options in ({'fail':'lcd_info.command'},{'geometry':(320,240)},{'status':1}):
            with self.subTest(options=options):
                result,events,opens=self.run_worker(options)
                self.assertIsNotNone(result.error);self.assertEqual(result.sent,0);self.assertEqual(opens,1)
                self.assertFalse(any(stage=='frame.command' for _,stage in events))
                self.assertEqual(events[-1],('first','close'))

    def test_delayed_query_read_recovers_on_original_handle(self):
        result=worker();events=[];transport=Transport('first',events,stop=result.stop)
        original=transport.read;delayed=[True]
        def read(ep,count):
            if delayed.pop() if delayed else False:raise OSError(121,'delayed query')
            return original(ep,count)
        transport.read=read
        with patch.object(output,'WinUSB',return_value=transport) as opened,patch.object(output.ScreenOutput,'initialization_delay',0):result.run()
        self.assertEqual(opened.call_count,1);self.assertEqual(result.sent,1);self.assertIsNone(result.error)
        self.assertEqual(events.count(('first','lcd_info.command')),1);self.assertNotIn(('first','reset'),events)

    def test_session_counts_only_a_complete_acknowledged_frame(self):
        events=[];release=threading.Event();reading=threading.Event();transport=Transport('test',events)
        original=transport.read
        def read(ep,count):
            if transport.kind=='frame':reading.set();release.wait(2)
            return original(ep,count)
        transport.read=read;session=DisplaySession(enumerator=lambda:['test-only'])
        with patch.object(output,'WinUSB',return_value=transport),patch.object(output.ScreenOutput,'initialization_delay',0):
            try:
                session.reconnect(0);session.submit(Image.new('RGB',(480,480)))
                self.assertTrue(reading.wait(1));self.assertEqual(session.snapshot()['usb_sent'],0)
                release.set()
                for _ in range(100):
                    if session.snapshot()['usb_sent']:break
                    threading.Event().wait(.005)
                self.assertEqual(session.snapshot()['usb_sent'],1);self.assertIsNone(session.snapshot()['usb_error'])
            finally:release.set();self.assertTrue(session.close())
        self.assertEqual(events.count(('test','close')),1)

    def test_timeout_uses_windows_error_code_instead_of_mapped_errno(self):
        error=OSError(22,'mapped Windows timeout');error.winerror=121
        transport=Transport('test',[])
        def read(ep,count):raise error
        transport.read=read
        with self.assertRaises(ProtocolError) as raised:FrameSender(transport).lcd_info()
        self.assertTrue(raised.exception.is_timeout)
        error.winerror=5
        with self.assertRaises(ProtocolError) as raised:FrameSender(transport).lcd_info()
        self.assertFalse(raised.exception.is_timeout)

    def test_protocol_failures_keep_distinct_stage_and_elapsed_time(self):
        for stage in ('lcd_info.command','lcd_info.reply','lcd_info.status','frame.command','frame.pixels','frame.status'):
            with self.subTest(stage=stage):
                sender=FrameSender(Transport('test',[],fail=stage))
                with self.assertRaises(ProtocolError) as raised:
                    if stage.startswith('lcd_info'):sender.lcd_info()
                    else:sender.send(bytes(460800))
                error=raised.exception
                self.assertEqual(error.stage,stage);self.assertGreaterEqual(error.elapsed_ms,0)
                self.assertTrue(error.is_timeout);self.assertIn(stage,str(error));self.assertIn('121',str(error))
                self.assertTrue(sender.faulted)
                with self.assertRaises(ProtocolError):sender.send(bytes(460800))

    def test_failed_winusb_count_is_preserved_as_unconfirmed_diagnostic_only(self):
        for api,method,count in (('WinUsb_WritePipe','write',460800),('WinUsb_ReadPipe','read',13)):
            with self.subTest(api=api):
                transport=winusb.WinUSB.__new__(winusb.WinUSB);transport.handle=object()
                def fail(handle,ep,buf,length,actual,overlapped):actual._obj.value=7;return False
                transport.u=SimpleNamespace(**{api:fail})
                with patch.object(ctypes,'get_last_error',return_value=121,create=True),patch.object(ctypes,'WinError',side_effect=lambda code:OSError(code,'simulated failure'),create=True):
                    with self.assertRaises(OSError) as raised:
                        getattr(transport,method)(1 if method=='write' else 0x81,bytes(count) if method=='write' else count)
                error=raised.exception
                self.assertEqual(error.usb_api,api);self.assertEqual(error.usb_requested,count)
                self.assertEqual(error.usb_reported,7)
                sender=FrameSender(SimpleNamespace(write=lambda *args:(_ for _ in ()).throw(error)))
                with self.assertRaises(ProtocolError) as contextual:sender.send(bytes(460800))
                self.assertIn('driver_count=7',str(contextual.exception));self.assertIn('unconfirmed',str(contextual.exception))

    def test_usb_log_is_bounded_and_setup_failure_does_not_stop_display(self):
        logger=logging.getLogger('rio_monitor.usb');old_handlers=logger.handlers[:];old_level=logger.level;old_propagate=logger.propagate
        logger.handlers=[]
        try:
            with tempfile.TemporaryDirectory() as td:
                self.assertTrue(output.configure_usb_logging(Path(td)))
                self.assertTrue(output.configure_usb_logging(Path(td)))
                self.assertEqual(len(logger.handlers),1)
                logger.handlers[0].maxBytes=200
                for _ in range(20):logger.warning('frame.status test timeout '+'x'*120)
                logger.handlers[0].flush()
                self.assertLessEqual(len(list(Path(td).glob('usb.log*'))),3)
                self.assertIn('frame.status',(Path(td)/'usb.log').read_text())
                for handler in logger.handlers[:]:handler.close();logger.removeHandler(handler)
            with patch.object(Path,'mkdir',side_effect=OSError('no access')):
                self.assertFalse(output.configure_usb_logging(Path('not-written')))
        finally:
            for handler in logger.handlers:handler.close()
            logger.handlers=old_handlers;logger.setLevel(old_level);logger.propagate=old_propagate

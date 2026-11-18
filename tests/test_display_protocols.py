import io
import struct
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from rio_monitor.model import Sample
from rio_monitor.display_protocols import (LEGACY, LEVETOP, Capabilities,
    LegacyProtocol, LevetopProtocol, UnsupportedDisplay, UncertainDisplayIO,
    capabilities_for, create_protocol, enumerate_paths, register_write,
    hid_reports, sample_commands, validate_ack)
from rio_monitor.output import ScreenOutput
from rio_monitor.storage import DisplaySession
from rio_monitor.resources import pack_resource

PATH=r'\\?\hid#vid_eeef&pid_1616#test#{guid}'
ACK=bytes.fromhex('5aa50410ff4c30')+bytes(57)


class DisplayProtocolTests(unittest.TestCase):
    def samples(self):
        now=time.monotonic()
        return {k:Sample(v,now) for k,v in [('cpu',34),('gpu',17),('ram_used',6),('ram_total',8)]}

    def test_captured_vendor_256_byte_command_and_all_four_reports_match(self):
        # Independent complete command observed from EMonitor, not generated here.
        raw=bytes.fromhex((Path(__file__).parent/'fixtures/levetop_emonitor_registers.hex').read_text())
        self.assertEqual(len(raw),256)
        encoded=register_write(0,raw[6:-2])
        self.assertEqual(encoded,raw)
        reports=hid_reports(encoded)
        self.assertEqual(len(reports),4)
        self.assertTrue(all(len(p)==65 and p[0]==0 for p in reports))
        self.assertEqual(b''.join(p[1:] for p in reports),raw)

    def test_ack_matches_captured_success_but_rejects_crc_failure_and_trailing_data(self):
        validate_ack(ACK)
        for data in [b'',ACK[:6],b'\0'+ACK,ACK[:4]+b'\0'+ACK[5:],ACK[:5]+b'xx'+ACK[7:],ACK[:7]+b'\x01']:
            with self.subTest(data=data),self.assertRaises(UncertainDisplayIO):validate_ack(data)

    def test_bad_ack_diagnostics_distinguish_nack_crc_and_padding_without_dumping_tail(self):
        cases = [
            (bytes.fromhex('5aa50410000c70'), 'command rejected'),
            (bytes.fromhex('5aa50410ff0000'), 'CRC mismatch'),
            (ACK + b'private-device-tail', 'Unexpected data after'),
            (b'bad', 'Malformed'),
        ]
        for reply, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(UncertainDisplayIO) as caught:
                validate_ack(reply)
            message = str(caught.exception)
            self.assertIn(reason, message)
            self.assertIn('length=' + str(len(reply)), message)
            self.assertIn('prefix=' + reply[:7].hex(), message)
            self.assertNotIn('private-device-tail', message)
            self.assertNotIn(b'private-device-tail'.hex(), message)
            self.assertTrue(caught.exception.requires_replug)

    def test_rejected_ack_faults_session_without_following_values_or_replay(self):
        dev=Mock();dev.write.side_effect=len
        dev.read.return_value=bytes.fromhex('5aa50410000c70')
        adapter=LevetopProtocol(lambda:dev);adapter.open(PATH)
        with self.assertRaisesRegex(UncertainDisplayIO,'command rejected'):
            adapter.send(self.samples())
        with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
        self.assertEqual(dev.write.call_count,1)
        self.assertEqual(dev.read.call_count,1)
        self.assertTrue(adapter.faulted);adapter.close()

    def test_protocol_cannot_encode_system_flash_or_unbounded_writes(self):
        for addr,data in [(0x7001,b'xx'),(-1,b'xx'),(0x5fff,b'xxxx'),(0,b'x'),(0,b''),(0,bytes(250))]:
            with self.subTest(addr=addr,size=len(data)),self.assertRaises(ValueError):register_write(addr,data)

    def test_samples_use_vendor_word_addresses_and_64bit_big_endian(self):
        commands=sample_commands(self.samples())
        self.assertEqual([(int.from_bytes(c[4:6],'big'),int.from_bytes(c[6:-2],'big')) for c in commands],[(0,34),(12,17),(32,75)])
        self.assertTrue(all(len(c)==16 for c in commands))
        reports=hid_reports(commands[0]);self.assertEqual(len(reports[0]),65)
        self.assertEqual(reports[0][17:],bytes(48))

    def test_missing_stale_and_invalid_values_are_not_replaced_with_zero(self):
        self.assertEqual(sample_commands({}),[])
        for value in [None,float('nan'),float('inf'),-1,101]:
            self.assertEqual(sample_commands({'cpu':Sample(value,10)},now=10),[])
        self.assertEqual(sample_commands({'cpu':Sample(50,0)},now=10),[])
        self.assertEqual(sample_commands({'ram_used':Sample(10,10),'ram_total':Sample(0,10)},now=10),[])

    def test_new_adapter_opens_only_target_identity_and_does_not_initialize_by_writing(self):
        dev=Mock();dev.read.return_value=[]
        adapter=LevetopProtocol(lambda:dev);adapter.open(PATH);adapter.initialize();adapter.close()
        dev.open_path.assert_called_once_with(PATH.encode());dev.write.assert_not_called();dev.close.assert_called_once()
        factory=Mock()
        with self.assertRaises(UnsupportedDisplay):LevetopProtocol(factory).open(r'\\?\hid#vid_e2b7&pid_7001#other')
        factory.assert_not_called()

    def test_stale_ack_on_connect_requires_replug_without_any_write(self):
        dev=Mock();dev.read.return_value=ACK
        adapter=LevetopProtocol(lambda:dev);adapter.open(PATH)
        with self.assertRaises(UncertainDisplayIO):adapter.initialize()
        with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
        dev.write.assert_not_called();adapter.close()

    def test_each_sample_waits_for_ack_and_no_missing_sample_is_counted(self):
        dev=Mock();dev.write.side_effect=len;dev.read.return_value=ACK
        adapter=LevetopProtocol(lambda:dev);adapter.open(PATH)
        self.assertFalse(adapter.send({}));dev.write.assert_not_called()
        self.assertTrue(adapter.send(self.samples()))
        self.assertEqual(dev.write.call_count,3);self.assertEqual(dev.read.call_count,3)
        adapter.close()

    def test_shutdown_finishes_current_ack_but_sends_no_further_values(self):
        cancelled=threading.Event();dev=Mock();dev.write.side_effect=len
        dev.read.side_effect=lambda *args:(cancelled.set() or ACK)
        adapter=LevetopProtocol(lambda:dev);adapter.open(PATH)
        self.assertFalse(adapter.send(self.samples(),cancelled=cancelled.is_set))
        self.assertEqual(dev.write.call_count,1);self.assertFalse(adapter.faulted);adapter.close()

    def test_no_ack_is_bounded_and_does_not_retry_out_or_send_following_values(self):
        dev=Mock();dev.write.side_effect=len;dev.read.return_value=[]
        adapter=LevetopProtocol(lambda:dev,clock=lambda:0);adapter.open(PATH)
        with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
        self.assertEqual(dev.read.call_count,10);self.assertEqual(dev.write.call_count,1)
        with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
        self.assertEqual(dev.write.call_count,1);adapter.close()

    def test_partial_or_failed_write_is_never_replayed(self):
        for result in [12,OSError('unplugged')]:
            dev=Mock();dev.write.side_effect=result if isinstance(result,Exception) else None;dev.write.return_value=result
            adapter=LevetopProtocol(lambda:dev);adapter.open(PATH)
            with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
            with self.assertRaises(UncertainDisplayIO):adapter.send(self.samples())
            self.assertEqual(dev.write.call_count,1);dev.read.assert_not_called();adapter.close()

    def test_new_model_negotiates_rio1_by_interface_and_validated_hello(self):
        import zlib
        from rio_monitor.display_protocols import RIO_FRAME_GUID
        from rio_monitor.lt168b_display import HELLO, LT168BBenchProtocol
        from rio_monitor.winusb import supported_identity
        path = r'\\?\USB#VID_4321&PID_BEEF#new-model#' + RIO_FRAME_GUID.upper()
        self.assertTrue(supported_identity(path))
        adapter = create_protocol(path)
        self.assertIsInstance(adapter, LT168BBenchProtocol)
        self.assertTrue(capabilities_for(path).frames)
        transport = Mock()
        adapter.transport_factory = lambda candidate: transport if candidate == path else None
        adapter.open(path)
        hello = HELLO.pack(b'RIO1', 1, 32, 480, 480, 32, 16, 7, 8218, 460800, 0)[:-4]
        transport.control.side_effect = [hello + struct.pack('<I', zlib.crc32(hello)), b'']
        adapter.initialize()
        self.assertTrue(adapter.ready)
        self.assertEqual(transport.control.call_args_list[0].args, (0xc1, 0x52, 0, 0, 32))
        transport.write.assert_not_called()
        adapter.close()

        transport.reset_mock()
        transport.control.side_effect = [b'unknown protocol']
        adapter.open(path)
        with self.assertRaises(UnsupportedDisplay):
            adapter.initialize()
        transport.reset_pipes.assert_not_called()
        transport.write.assert_not_called()
        adapter.close()
        for other in (path.replace('USB#', 'HID#'), path.replace(RIO_FRAME_GUID.upper(), '{other}')):
            self.assertFalse(supported_identity(other))
            with self.assertRaises(UnsupportedDisplay):
                capabilities_for(other)

    def test_registry_filters_other_devices_and_preserves_legacy_enumeration(self):
        hid=Mock();hid.enumerate.return_value=[dict(path=PATH.encode(),manufacturer_string='LEVETOP',usage_page=1,usage=0),dict(path=b'keyboard',manufacturer_string='LEVETOP',usage_page=1,usage=6)]
        with patch.dict(sys.modules,{'hid':hid}),patch('rio_monitor.winusb.enumerate_paths',return_value=['legacy']):
            self.assertEqual(enumerate_paths(),sorted(['legacy',PATH]))
        hid.enumerate.assert_called_once_with(0xeeef,0x1616)
        self.assertEqual(capabilities_for(PATH),LEVETOP)
        with self.assertRaises(UnsupportedDisplay):capabilities_for(PATH.replace('1616','16160'))
        self.assertIsInstance(create_protocol(PATH),LevetopProtocol)

    def test_same_output_worker_routes_samples_without_rendering_a_frame(self):
        sent=threading.Event();driver=Mock();driver.capabilities=LEVETOP
        driver.send.side_effect=lambda content,**kwargs:(sent.set() or True)
        output=ScreenOutput(PATH,driver=driver)
        try:
            self.assertFalse(output.needs_frame)
            output.submit(Image.new('RGB',(480,480)));driver.send.assert_not_called()
            samples=self.samples();output.submit_samples(samples)
            self.assertTrue(sent.wait(1))
            self.assertEqual(driver.send.call_args.args[0],samples)
        finally:self.assertTrue(output.close())
        self.assertEqual(output.sent,1);driver.close.assert_called_once()

    def test_common_session_routes_samples_and_refuses_flash_before_retiring_output(self):
        writer=Mock();writer.error=None;writer.capabilities=LEVETOP
        session=DisplaySession(enumerator=lambda:[PATH]);session.output=writer
        samples=self.samples();session.submit_samples(samples);writer.submit_samples.assert_called_once_with(samples)
        buffer=io.BytesIO();Image.new('RGB',(480,480)).save(buffer,'GIF')
        writer.requires_replug=False
        with patch('rio_monitor.storage.ResourceSender') as resource, self.assertRaisesRegex(RuntimeError,'stored media'):
            session.replace(pack_resource(buffer.getvalue()),lambda *args:None)
        resource.assert_not_called();writer.close.assert_not_called()
        self.assertIs(session.output,writer);self.assertEqual(session.mode,'monitor');self.assertFalse(session.resource_active)

    def test_multiple_protocol_devices_do_not_choose_an_arbitrary_screen(self):
        factory=Mock();session=DisplaySession(enumerator=lambda:['legacy',PATH],output_factory=factory)
        with self.assertRaisesRegex(RuntimeError,'exactly one'):session.connect()
        factory.assert_not_called()

    def test_future_frame_driver_can_use_other_geometry_without_another_worker(self):
        sent=threading.Event();driver=Mock();driver.capabilities=Capabilities('test',True,False,False,(320,240))
        driver.send.side_effect=lambda image,**kwargs:(sent.set() or True)
        with patch.object(ScreenOutput,'initialization_delay',0):
            output=ScreenOutput('test',driver=driver)
            try:
                output.submit(Image.new('RGB',(320,240)))
                self.assertTrue(sent.wait(1));self.assertEqual(driver.send.call_args.args[0].size,(320,240))
            finally:self.assertTrue(output.close())

if __name__=='__main__':unittest.main()

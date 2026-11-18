"""NUC native C receiver and USB metadata vs RIO's actual frame adapter."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zlib

from PIL import Image
from rio_monitor.display_protocols import UnsupportedDisplay, capabilities_for
from rio_monitor.lt168b_display import LT168BBenchProtocol, validate_hello, ACK, BENCH
from rio_monitor.lt168b_stream import encode_frame
from rio_monitor.display_protocols import LEGACY, LEVETOP
from rio_monitor.protocol import encode_rgb565
from rio_monitor.winusb import WinUSB, SetupPacket
from rio_monitor.output import ScreenOutput

ROOT = Path(__file__).resolve().parents[1]
PATH = r'\\?\usb#vid_ffff&pid_168b#bench'


class NativeTransport:
    def __init__(self, library):
        self.lib = library
        self.compression = False
        self.pixels = (ctypes.c_uint16 * 230400)()
        self.state = ctypes.create_string_buffer(library.rio_stream_size())
        self.writes = []
        self.controls = []
        self.response = b''
        self.fault = None
        self.closed = False
        self.ack_read = threading.Event()
        self.reset_pipes()

    def reset_pipes(self):
        self.lib.rio_stream_init(self.state, self.pixels)
        self.response = b''

    def control(self, kind, request, value, index, length):
        self.controls.append((kind, request, value, index, length))
        if request == 0x52:
            data = ctypes.create_string_buffer(32)
            self.lib.rio_usb_hello(data)
            raw = bytearray(data.raw)
            # This fixture represents the retained capability1/3 receiver.
            struct.pack_into('<I', raw, 16, 3 if self.compression else 1)
            struct.pack_into('<I', raw, 20, 1048)
            struct.pack_into('<I', raw, 28, zlib.crc32(raw[:28]))
            return b'wrong' if self.fault == 'hello' else bytes(raw)
        if request == 0x53:
            self.reset_pipes()
            return b''
        raise AssertionError('Unexpected control')

    def write(self, ep, data):
        assert ep == 1
        self.writes.append(data)
        if self.fault == 'timeout':
            raise TimeoutError('simulated OUT timeout')
        if self.fault == 'short':
            return len(data) - 1
        # Actual USB maximum packet size, including header/payload splits.
        for offset in range(0, len(data), 64):
            chunk = data[offset:offset+64]
            result = self.lib.rio_stream_feed(self.state, chunk, len(chunk))
            if result < 0:
                raise AssertionError('Native receiver rejected host frame')
            if result == 1:
                session = self.lib.test_stream_session(self.state)
                frame = self.lib.test_stream_frame(self.state)
                response = ctypes.create_string_buffer(24)
                completed = self.lib.rio_stream_completed(self.state)
                self.lib.rio_usb_ack(response, session, frame, completed, 0)
                self.response = response.raw
        return len(data)

    def read(self, ep, length):
        assert (ep, length) == (0x82, 24)
        data = self.response
        if self.fault == 'lost_ack':
            raise TimeoutError('simulated lost ACK after display completed')
        if self.fault == 'crc':
            return data[:-1] + bytes([data[-1] ^ 1])
        if self.fault == 'short_ack':
            return data[:12]
        fields = list(ACK.unpack(data))
        if self.fault == 'session': fields[3] += 1
        if self.fault == 'frame': fields[4] += 1
        if self.fault == 'count': fields[5] += 1
        if self.fault == 'rejected': fields[2] = 1
        data = ACK.pack(*fields)
        self.ack_read.set()
        return data[:-4] + struct.pack('<I', zlib.crc32(data[:-4]))

    def close(self):
        self.closed = True


class DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):
            raise unittest.SkipTest('Requires native C compiler')
        cls.temp = tempfile.TemporaryDirectory()
        so = Path(cls.temp.name) / 'rio.so'
        accessor = Path(cls.temp.name) / 'state.c'
        accessor.write_text('#include "rio_stream.h"\n'
                            'uint32_t test_stream_session(const rio_stream *s) { return s->session; }\n'
                            'uint32_t test_stream_frame(const rio_stream *s) { return s->frame; }\n')
        subprocess.run(['cc', '-std=c99', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                        str(ROOT/'firmware/lt168b/rio_usb.c'), str(ROOT/'firmware/lt168b/rio_stream.c'), str(ROOT/'firmware/lt168b/rio_lz4.c'),
                        '-I', str(ROOT/'firmware/lt168b'), str(accessor), '-o', str(so)], check=True)
        cls.lib = ctypes.CDLL(str(so))
        cls.lib.rio_stream_size.restype = ctypes.c_size_t
        cls.lib.rio_stream_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cls.lib.rio_stream_feed.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        cls.lib.rio_stream_completed.argtypes = [ctypes.c_void_p]
        cls.lib.rio_stream_completed.restype = ctypes.c_uint32
        for name in ('test_stream_session','test_stream_frame'):
            function = getattr(cls.lib,name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_uint32
        cls.lib.rio_usb_hello.argtypes = [ctypes.c_void_p]
        cls.lib.rio_usb_ack.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16]
        for name in ('rio_usb_descriptor', 'rio_usb_ms_descriptor'):
            getattr(cls.lib, name).restype = ctypes.c_void_p
        cls.lib.rio_usb_descriptor.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint16)]
        cls.lib.rio_usb_ms_descriptor.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_uint16)]

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.transport = NativeTransport(self.lib)
        self.adapter = LT168BBenchProtocol(lambda path: self.transport, lambda: 133)
        self.adapter.open(PATH)
        self.image = Image.new('RGB', (480, 480), '#28a561')

    def test_native_pixels_key_delta_and_unchanged(self):
        self.adapter.initialize()
        for number in range(3):
            if number == 1:
                self.image.putpixel((479, 479), (255, 0, 255))
            self.transport.writes.clear()
            self.assertTrue(self.adapter.send(self.image))
            expected = struct.unpack('>230400H', encode_rgb565(self.image))
            self.assertEqual(tuple(self.transport.pixels), expected)
            self.assertEqual(len(self.transport.writes), (8, 1, 1)[number])
            self.assertTrue(all(len(block) <= 65536 for block in self.transport.writes))

    def test_batched_wire_is_identical_and_native_pixels_match_pattern(self):
        self.adapter.initialize()
        previous = None
        for frame in range(1, 4):
            # Colour variation crosses every tile and USB boundary, not a uniform fill.
            image = Image.frombytes('RGB', (480,480), bytes((i*37+frame*11)%256 for i in range(480*480*3)))
            pixels = encode_rgb565(image)
            expected_wire = b''.join(encode_frame(pixels, session=133, frame=frame, acknowledged=previous))
            self.transport.writes.clear()
            self.assertTrue(self.adapter.send(image))
            self.assertEqual(b''.join(self.transport.writes), expected_wire)
            self.assertEqual(tuple(self.transport.pixels), struct.unpack('>230400H', pixels))
            self.assertEqual(len(self.transport.writes),8)
            previous = pixels

    def test_interrupted_batch_invalidates_base_without_retry_or_ack(self):
        self.adapter.initialize()
        original = self.transport.write
        calls = []
        def fail_second(ep,data):
            calls.append(len(data))
            if len(calls)==2:raise TimeoutError('partial frame interrupted')
            return original(ep,data)
        with patch.object(self.transport,'write',side_effect=fail_second):
            with self.assertRaises(TimeoutError):self.adapter.send(self.image)
        self.assertEqual(len(calls),2)
        self.assertFalse(self.transport.ack_read.is_set())
        self.assertFalse(self.adapter.ready)
        self.assertIsNone(self.adapter.base)
        self.adapter.initialize()
        self.assertTrue(self.adapter.send(self.image))
        self.assertEqual(tuple(self.transport.pixels),struct.unpack('>230400H',encode_rgb565(self.image)))

    def test_existing_screen_worker_uses_same_adapter_contract(self):
        output = ScreenOutput(PATH, driver=self.adapter)
        try:
            output.submit(self.image)
            self.assertTrue(self.transport.ack_read.wait(2), 'Worker did not receive frame ACK')
        finally:
            self.assertTrue(output.close())
        self.assertIsNone(output.error)
        self.assertEqual(output.sent, 1)
        self.assertTrue(self.transport.closed)
        self.assertEqual(tuple(self.transport.pixels), struct.unpack('>230400H', encode_rgb565(self.image)))

    def test_incompatible_hello_never_resets_or_writes(self):
        self.transport.fault = 'hello'
        with self.assertRaises(UnsupportedDisplay): self.adapter.initialize()
        self.assertEqual(len(self.transport.controls), 1)
        self.assertEqual(self.transport.writes, [])
        with self.assertRaises(OSError): self.adapter.send(self.image)

    def test_stock_identity_rejected_and_qualified_firmware_routed(self):
        with self.assertRaises(UnsupportedDisplay): self.adapter.open(r'usb#vid_eeef&pid_1616#stock')
        from rio_monitor.display_protocols import create_protocol
        self.assertEqual(capabilities_for(PATH), self.adapter.capabilities)
        self.assertIsInstance(create_protocol(PATH), LT168BBenchProtocol)

    def test_exact_discovery_identity_filter(self):
        from rio_monitor.winusb import supported_identity
        for path in (PATH, 'VID_FFFF&PID_168B', 'usb#vid_2a55&pid_9990#legacy'):
            self.assertTrue(supported_identity(path))
        for path in ('VID_FFFF&PID_168B0', 'VID_EEEF&PID_268A', 'VID_EEEF&PID_1616', 'VID_1234&PID_168B'):
            self.assertFalse(supported_identity(path))

    def test_automatic_session_reconnect_starts_new_keyframe(self):
        from rio_monitor.storage import DisplaySession
        transports=[]
        def make_adapter():
            transport=NativeTransport(self.lib);transports.append(transport)
            return LT168BBenchProtocol(lambda path:transport,lambda:100+len(transports))
        session=DisplaySession(enumerator=lambda:[PATH])
        with patch('rio_monitor.lt168b_display.LT168BBenchProtocol',side_effect=make_adapter):
            try:
                session.reconnect(now=0)
                session.submit(self.image)
                self.assertTrue(transports[0].ack_read.wait(3))
                transports[0].fault='timeout'
                session.submit(self.image)
                self.assertTrue(session.output.finished.wait(3))
                session.reconnect(now=1)
                session.reconnect(now=3)
                session.submit(self.image)
                self.assertTrue(transports[1].ack_read.wait(3))
                self.assertTrue(transports[0].closed)
                self.assertEqual(len(transports[1].writes),8)
                self.assertEqual(tuple(transports[1].pixels),struct.unpack('>230400H',encode_rgb565(self.image)))
            finally:self.assertTrue(session.close())

    def test_uncertain_io_requires_reset_and_full_frame(self):
        for fault in ('short', 'timeout', 'lost_ack', 'short_ack', 'crc', 'session', 'frame', 'count', 'rejected'):
            with self.subTest(fault=fault):
                self.adapter.initialize()
                self.adapter.send(self.image)
                self.transport.fault = fault
                with self.assertRaises(OSError): self.adapter.send(self.image)
                self.assertIsNone(self.adapter.base)
                before = len(self.transport.writes)
                with self.assertRaises(OSError): self.adapter.send(self.image)
                self.assertEqual(len(self.transport.writes), before)
                self.transport.fault = None
                self.adapter.initialize()
                self.transport.writes.clear()
                self.adapter.send(self.image)
                self.assertEqual(len(self.transport.writes), 8)

    def test_cancellation_before_and_during_transfer(self):
        self.adapter.initialize()
        self.assertFalse(self.adapter.send(self.image, lambda: True))
        self.assertTrue(self.adapter.ready)
        calls = iter((False, False, True))
        self.assertFalse(self.adapter.send(self.image, lambda: next(calls)))
        self.assertFalse(self.adapter.ready)
        self.assertIsNone(self.adapter.base)

    def test_compression_negotiation_and_lost_ack_force_new_key(self):
        from rio_monitor.lt168b_stream import HEADER, COMPRESSED_TILE
        self.transport.compression = True
        self.adapter.initialize()
        self.assertTrue(self.adapter.compression)
        self.adapter.send(self.image)
        self.assertLess(sum(map(len,self.transport.writes)),20000)
        self.assertEqual(tuple(self.transport.pixels),struct.unpack('>230400H',encode_rgb565(self.image)))
        self.transport.fault = 'lost_ack'
        self.image.putpixel((479,479),(255,0,255))
        with self.assertRaises(TimeoutError): self.adapter.send(self.image)
        self.assertIsNone(self.adapter.base)
        self.assertFalse(self.adapter.ready)
        self.transport.fault = None
        self.adapter.initialize()
        self.transport.writes.clear()
        self.adapter.send(self.image)
        wire=b''.join(self.transport.writes)
        self.assertEqual(HEADER.unpack(wire[:20])[2],1)
        self.assertEqual(tuple(self.transport.pixels),struct.unpack('>230400H',encode_rgb565(self.image)))

    def test_old_firmware_selects_exact_raw_protocol(self):
        self.adapter.initialize()
        self.assertFalse(self.adapter.compression)
        self.adapter.send(self.image)
        expected=b''.join(encode_frame(encode_rgb565(self.image),session=133,frame=1))
        self.assertEqual(b''.join(self.transport.writes),expected)

    def test_capability_crc_and_fields(self):
        data = self.transport.control(0xc1, 0x52, 0, 0, 32)
        validate_hello(data)
        for index in (0, 4, 6, 8, 10, 12, 14, 16, 20, 24, 28):
            bad = bytearray(data); bad[index] ^= 1
            with self.assertRaises(UnsupportedDisplay): validate_hello(bytes(bad))

    def test_usb_descriptors_lengths_endpoints_and_winusb(self):
        def descriptor(kind, index):
            size = ctypes.c_uint16()
            p = self.lib.rio_usb_descriptor(kind, index, ctypes.byref(size))
            return ctypes.string_at(p, size.value) if p else b''
        self.assertEqual(len(descriptor(1, 0)), 18)
        config = descriptor(2, 0)
        self.assertEqual(len(config), int.from_bytes(config[2:4], 'little'))
        self.assertEqual((config[20], config[27]), (1, 0x82))
        for index in (0, 1, 2, 0xee):
            data = descriptor(3, index)
            self.assertEqual(len(data), data[0])
        self.assertEqual(descriptor(3, 2)[2:].decode('utf-16le'), 'RIO LT168B Bench')
        self.assertEqual(descriptor(9, 0), b'')
        for index in (4, 5):
            size = ctypes.c_uint16()
            p = self.lib.rio_usb_ms_descriptor(index, ctypes.byref(size))
            data = ctypes.string_at(p, size.value)
            self.assertEqual(len(data), int.from_bytes(data[:4], 'little'))
            if index == 4: self.assertEqual(data[18:26], b'WINUSB\0\0')
            else:
                self.assertEqual(data[20:60].decode('utf-16le'), 'DeviceInterfaceGUID\0')
                self.assertEqual(len(data[64:]), int.from_bytes(data[60:64], 'little'))

    def test_winusb_control_is_limited_to_bench_handshake(self):
        usb = WinUSB.__new__(WinUSB)
        usb.handle = None
        usb.u = Mock()
        with self.assertRaises(ValueError): usb.control(0xc1, 0x52, 0, 0, 32)
        usb.endpoints = (1, 0x82)
        for arguments in ((0x41, 0x62, 0, 0, 32), (0xc1, 0x52, 1, 0, 32), (0xc1, 0x52, 0, 0, 65535)):
            with self.assertRaises(ValueError): usb.control(*arguments)
        self.assertEqual(ctypes.sizeof(SetupPacket), 8)
        self.assertEqual(usb.u.mock_calls, [])

    def test_winusb_reset_preserves_each_profile_endpoints(self):
        for endpoints in ((1, 0x81), (1, 0x82)):
            usb = WinUSB.__new__(WinUSB)
            usb.endpoints = endpoints
            usb.handle = 'fake'
            usb.u = Mock()
            usb.reset_pipes()
            self.assertEqual([call.args for call in usb.u.WinUsb_ResetPipe.call_args_list],
                             [('fake', endpoints[0]), ('fake', endpoints[1])])
            usb.u.WinUsb_FlushPipe.assert_called_once_with('fake', endpoints[1])


class PacingTests(unittest.TestCase):
    def test_slow_transport_sends_latest_animation_frame_after_ack(self):
        entered=threading.Event();release=threading.Event();second=threading.Event();colors=[]
        def send(image,cancelled):
            colors.append(image.getpixel((0,0)))
            if len(colors)==1:
                entered.set()
                if not release.wait(2):raise TimeoutError('test did not release frame')
            else:second.set()
            return True
        driver=Mock(capabilities=BENCH);driver.send.side_effect=send
        output=ScreenOutput(PATH,driver)
        try:
            output.submit(Image.new('RGB',(480,480),'red'))
            self.assertTrue(entered.wait(2))
            for color in ('green','blue'):
                # Mirrors the actual hidden-window render gate.
                self.assertTrue(output.needs_frame)
                if output.needs_frame:output.submit(Image.new('RGB',(480,480),color))
                self.assertEqual(output.frames.qsize(),1)
            release.set();self.assertTrue(second.wait(2))
            self.assertEqual(colors,[(255,0,0),(0,0,255)])
        finally:
            release.set();self.assertTrue(output.close())
        self.assertFalse(output.needs_frame)
        self.assertIsNone(output.error)

    def test_worker_uses_each_adapter_interval_and_still_obeys_backpressure(self):
        for capabilities,expected in ((BENCH,1/30),(LEGACY,1/12),(LEVETOP,.5)):
            for send_seconds in (0.,.1):
                with self.subTest(protocol=capabilities.protocol,send_seconds=send_seconds):
                    now=[0.];starts=[]
                    class Stop:
                        stopped=False
                        def is_set(self):return self.stopped
                        def wait(self,seconds):now[0]+=seconds;return self.stopped
                    stop=Stop()
                    def send(image,cancelled):
                        starts.append(now[0]);now[0]+=send_seconds
                        if len(starts)==6:stop.stopped=True
                        return True
                    driver=Mock(capabilities=capabilities)
                    driver.send.side_effect=send
                    worker=ScreenOutput.__new__(ScreenOutput)
                    worker.driver=driver;worker.path=PATH;worker.initialization_delay=0
                    worker.stop=stop;worker.finished=Mock();worker.frames=Mock()
                    worker.sent=0;worker.error=None;worker.requires_replug=False
                    with patch('rio_monitor.output.time.monotonic',side_effect=lambda:now[0]):worker.run()
                    self.assertIsNone(worker.error)
                    self.assertEqual(worker.sent,6)
                    self.assertEqual(len(starts),6)
                    for left,right in zip(starts,starts[1:]):self.assertAlmostEqual(right-left,max(expected,send_seconds))
                    driver.close.assert_called_once()


if __name__ == '__main__': unittest.main()

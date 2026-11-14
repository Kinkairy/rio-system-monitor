"""Portable C receiver vs independent Python/native RGB565 oracle; no USB."""
import ctypes
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from rio_monitor.lt168b_stream import encode_frame, packet, FRAME_BYTES, TILE

ROOT=pathlib.Path(__file__).resolve().parents[1]

class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which('cc')
        if not cc:raise unittest.SkipTest('Native C compiler required for receiver test')
        cls.tmp=tempfile.TemporaryDirectory()
        lib=pathlib.Path(cls.tmp.name)/'receiver.so'
        subprocess.run([cc,'-std=c99','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        '-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
                        str(ROOT/'firmware/lt168b/rio_stream.c'), str(ROOT/'firmware/lt168b/rio_lz4.c'),'-o',str(lib)],check=True)
        cls.lib=ctypes.CDLL(str(lib))
        cls.lib.rio_stream_size.restype=ctypes.c_size_t
        cls.lib.rio_stream_init.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        cls.lib.rio_stream_feed.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.rio_stream_completed.argtypes=[ctypes.c_void_p]
        cls.lib.rio_stream_completed.restype=ctypes.c_uint32
        cls.frame=bytes((i*29+i//97)%256 for i in range(FRAME_BYTES))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.state=ctypes.create_string_buffer(self.lib.rio_stream_size())
        self.storage=ctypes.create_string_buffer(b'\xa7'*(FRAME_BYTES+32),FRAME_BYTES+32)
        self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16)
    def tearDown(self):
        self.assertEqual(self.storage.raw[:16],b'\xa7'*16)
        self.assertEqual(self.storage.raw[-16:],b'\xa7'*16)
    def feed(self,data,chunk=64):
        answer=0
        for i in range(0,len(data),chunk):
            part=data[i:i+chunk]
            value=self.lib.rio_stream_feed(self.state,part,len(part))
            if value<0:return value
            answer=max(answer,value)
        return answer
    def send(self,pixels=None,seq=1,base=None,session=133):
        data=b''.join(encode_frame(self.frame if pixels is None else pixels,session=session,frame=seq,acknowledged=base))
        return self.feed(data)
    def expect_pixels(self,pixels):
        expected=struct.pack('='+str(FRAME_BYTES//2)+'H',*struct.unpack('>'+str(FRAME_BYTES//2)+'H',pixels))
        self.assertEqual(self.storage.raw[16:-16],expected)
    def test_keyframe_exact(self):
        self.assertEqual(self.send(),1);self.expect_pixels(self.frame)
    def test_delta_edges_exact(self):
        self.send();new=bytearray(self.frame)
        for at in (0,62,64,958,960,480*16*2,FRAME_BYTES-2):new[at:at+2]=b'\xf8\0'
        self.assertEqual(self.send(bytes(new),2,self.frame),1);self.expect_pixels(bytes(new))
    def test_unchanged(self):
        self.send();self.assertEqual(self.send(seq=2,base=self.frame),1);self.expect_pixels(self.frame)
    def test_no_baseline(self):self.assertEqual(self.send(seq=2,base=self.frame),-1)
    def test_wrong_session(self):
        self.send();self.assertEqual(self.send(seq=2,base=self.frame,session=134),-1)
    def test_stale_frame(self):
        self.send();self.assertEqual(self.send(seq=1,base=self.frame),-1)
    def test_missing_tile(self):
        packets=list(encode_frame(self.frame,session=133,frame=1))
        self.assertEqual(self.feed(b''.join(packets[:25]+packets[26:])),-1)
        self.assertEqual(self.lib.rio_stream_completed(self.state),0)
        self.assertEqual(self.send(seq=2),1);self.expect_pixels(self.frame)
    def test_duplicate_tile(self):
        packets=list(encode_frame(self.frame,session=133,frame=1))
        self.assertEqual(self.feed(packets[0]+packets[1]+packets[1]),-1)
    def test_bad_crc_no_tile_write(self):
        packets=list(encode_frame(self.frame,session=133,frame=1));self.feed(packets[0])
        corrupt=bytearray(packets[1]);corrupt[-1]^=1
        self.assertEqual(self.feed(bytes(corrupt)),-1)
        self.assertEqual(self.storage.raw,b'\xa7'*(FRAME_BYTES+32))
    def test_bad_header(self):
        data=bytearray(packet(1,133,1,450));data[6:8]=b'\xff\xff'
        self.assertEqual(self.feed(bytes(data)),-1)
    def test_outside_tile(self):
        self.feed(packet(1,133,1,450))
        self.assertEqual(self.feed(packet(TILE,133,1,450,bytes(1024))),-1)
    def test_disconnect_partial(self):
        packets=list(encode_frame(self.frame,session=133,frame=1))
        self.feed(packets[0]+packets[1][:100])
        self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16)
        self.assertEqual(self.send(session=134),1);self.expect_pixels(self.frame)
    def test_fragmentation(self):
        packets=list(encode_frame(self.frame,session=133,frame=1))
        # USB boundaries may split header, CRC or payload, or concatenate packets.
        for part in packets[:3]:self.assertEqual(self.feed(part,1),0)
        self.assertEqual(self.feed(b''.join(packets[3:]),4093),1);self.expect_pixels(self.frame)
    def test_input_bounds(self):
        for data in (b'',bytes(FRAME_BYTES-1),bytes(FRAME_BYTES+1)):
            with self.assertRaises(ValueError):list(encode_frame(data,session=1,frame=1))
        for session,frame in ((0,1),(1,0),(1,0x100000000)):
            with self.assertRaises(ValueError):list(encode_frame(self.frame,session=session,frame=frame))

if __name__=='__main__':unittest.main()

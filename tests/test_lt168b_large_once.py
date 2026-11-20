"""Reference accepted-input equivalence and receiver rejection boundaries."""
import ctypes,random,struct,subprocess,tempfile,unittest
from pathlib import Path
import lz4.block
import test_lt168b_decode_once as decode
from rio_monitor.lt168b_stream import packet

WRAPPER=r"""
#include "rio_stream.c"
int validate_tile(const uint8_t *p,unsigned n) {return valid_lz4_tile(p,n,1024);}
"""
def boundary_blocks():
    # Reference accepts zero offset and a shortcut ending with a zero-literal
    # token. Preserve this pinned decoder behavior instead of imposing new rules.
    return [b'\x0f\0\0'+b'\xff'*3+b'\xeb\x50abcde',
            b'\x8f'+bytes(8)+b'\x08\0'+b'\xff'*3+b'\xc8'+
            b'\xee'+bytes(14)+b'\x08\0\0']

class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name)
        src=d/'validator.c';src.write_text(WRAPPER);fw=decode.ROOT/'firmware/lt168b'
        subprocess.run(['cc','-std=gnu99','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-I',str(fw),str(src),
            str(fw/'rio_lz4.c'),'-o',str(d/'validator.so')],check=True)
        cls.lib=ctypes.CDLL(str(d/'validator.so'))
        cls.lib.validate_tile.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        cls.lib.LZ4_decompress_safe.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def compare(self,block):
        target=ctypes.create_string_buffer(b'\xa7'*1056,1056)
        got=self.lib.validate_tile(block,len(block))
        result=self.lib.LZ4_decompress_safe(block,ctypes.addressof(target)+16,len(block),1024)
        self.assertEqual(bool(got),result==1024,block.hex())
        self.assertEqual(target.raw[:16]+target.raw[-16:],b'\xa7'*32)
        return bool(got)
    def test_reference_compatibility_boundaries(self):
        for block in boundary_blocks():self.assertTrue(self.compare(block))
    def test_all_single_byte_boundary_mutations(self):
        for block in boundary_blocks():
            for i in range(len(block)):
                for v in range(256):self.compare(block[:i]+bytes([v])+block[i+1:])
            for n in range(len(block)):self.compare(block[:n])
    def test_literal_extension_and_wrong_output_sizes(self):
        for n in [0,1,4,5,12,14,15,16,254,255,256,1007,1011,1012,1018,1019,1020,1023,1024,1025,2048]:
            for raw in [bytes(n),bytes(i%251 for i in range(n))]:
                block=lz4.block.compress(raw,store_size=False)
                if len(block)<=1023:self.compare(block)
        for n in range(1024):self.compare(b'\xff'*n)

class ReceiverRejectionTests(decode.DecodeOnceTests):
    def test_invalid_large_staged_tile_rejected_before_end(self):
        good=b'\0'+lz4.block.compress(bytes(1024),store_size=False)
        for payload in [b'\0\0\0\0',b'\0'+good[1:-1],b'\0'+lz4.block.compress(bytes(1023),store_size=False),b'\0'+b'\xff'*100]:
            self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16);self.bind()
            old=self.storage.raw
            self.assertEqual(self.feed(packet(1,133,1,450)+packet(5,133,1,0,good),7),0)
            self.assertEqual(self.feed(packet(5,133,1,1,payload),1),-1)
            self.assertEqual(self.storage.raw,old)
            self.assertEqual(self.lib.rio_stream_completed(self.state),0)
            self.assertEqual(self.feed(packet(4,133,1,450)),-1)
    def test_invalid_overflow_tile_does_not_publish_prior_staging(self):
        good=b'\0'+lz4.block.compress(bytes(1024),store_size=False)
        self.lib.rio_stream_staging(self.state,ctypes.addressof(self.arena)+16,len(good)+2,
            ctypes.addressof(self.row)+16,self.sync,None)
        old=self.storage.raw
        self.assertEqual(self.feed(packet(1,133,1,450)+packet(5,133,1,0,good)),0)
        self.assertEqual(self.feed(packet(5,133,1,1,b'\0\0\0\0')),-1)
        self.assertEqual(self.storage.raw,old)
        self.assertEqual(self.lib.rio_stream_presentations(self.state),0)
        self.assertEqual(self.lib.rio_stream_fallbacks(self.state),0)
    def test_large_staging_decodes_at_commit_only(self):
        parts=self.parts(bytes(460800))
        self.assertEqual(self.feed(b''.join(parts[:-1]),17),0)
        self.assertEqual(self.work()[0],0)
        self.assertEqual(self.feed(parts[-1]),1)
        self.assertEqual(self.work()[0],450)
        self.expect_pixels(bytes(460800))

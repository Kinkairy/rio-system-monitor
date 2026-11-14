"""Independent LT168 SDK/datasheet register oracle, no hardware I/O."""
import ctypes,json,pathlib,struct,subprocess,tempfile,unittest,zlib
from rio_monitor.winusb import WinUSB
ROOT=pathlib.Path(__file__).resolve().parents[1]
HARNESS=r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static uint32_t ccr,acrg;static unsigned mode,reads,busy,started;
uint32_t cache_read32(uint32_t a) {
 ++reads;
 if(a==0x40190020u)return acrg;
 if(a!=0x40190000u)abort();
 if(started && (ccr&0x80000000u) && !mode && busy++>=2)ccr&=0x7fffffffu;
 return ccr;
}
void cache_write32(uint32_t a,uint32_t v) {
 printf("W %08x %08x\n",a,v);
 if(a==0x40190020u){acrg=v;return;}
 if(a==0x40190000u){ccr=v;started=1;return;}
 abort();
}
extern void rio_board_cache_init(void);
extern void rio_board_cache_status(uint32_t out[5]);
int main(int argc,char **argv) {
 uint32_t out[5];unsigned i;if(argc!=3)return 2;
 mode=(unsigned)strtoul(argv[1],0,10);ccr=(uint32_t)strtoul(argv[2],0,16);acrg=ccr^0x55u;
 rio_board_cache_init();rio_board_cache_status(out);
 printf("S");for(i=0;i<5;++i)printf(" %08x",out[i]);printf("\nR %u\n",reads);return 0;
}
"""
class CacheTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();d=pathlib.Path(cls.tmp.name)
  (d/'h.c').write_text(HARNESS);cls.exe=d/'cache'
  subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-fsanitize=undefined',
   '-fsanitize-undefined-trap-on-error','-DRIO_CACHE_TEST',str(d/'h.c'),
   str(ROOT/'firmware/lt168b/board_cache.c'),'-o',str(cls.exe)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,mode,seed):
  text=subprocess.run([str(self.exe),str(mode),f'{seed:x}'],check=True,timeout=3,capture_output=True,text=True).stdout
  lines=[s.split() for s in text.splitlines()]
  return ([(int(x[1],16),int(x[2],16)) for x in lines if x[0]=='W'],
          next([int(v,16) for v in x[1:]] for x in lines if x[0]=='S'),
          next(int(x[1]) for x in lines if x[0]=='R'))
 def test_sdk_sequence_invalidates_before_enabling_only_code_region(self):
  for seed in (0x30,0x05000031,0x80000000,0xffffffff):
   with self.subTest(seed=seed):
    writes,status,reads=self.run_case(0,seed)
    self.assertEqual(writes,[(0x40190020,0),(0x40190000,0x85000030),(0x40190020,8),(0x40190000,0x05000031)])
    self.assertEqual(status,[seed,seed^0x55,0x05000031,8,1]);self.assertLess(reads,16)
 def test_busy_timeout_is_bounded_and_never_enables_cacheable_regions(self):
  writes,status,reads=self.run_case(1,0x30)
  self.assertEqual(writes,[(0x40190020,0),(0x40190000,0x85000030)])
  self.assertEqual(status,[0x30,0x65,0x85000030,0,0]);self.assertLess(reads,100010)
  self.assertGreater(reads,2)

class ProfileTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();lib=pathlib.Path(cls.tmp.name)/'profile.so'
  subprocess.run(['cc','-std=c99','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
   '-fsanitize=undefined','-fsanitize-undefined-trap-on-error',str(ROOT/'firmware/lt168b/rio_usb.c'),'-o',str(lib)],check=True)
  cls.lib=ctypes.CDLL(str(lib));cls.lib.rio_usb_profile_request.argtypes=[ctypes.c_uint8,ctypes.c_uint8,ctypes.c_uint16,ctypes.c_uint16,ctypes.c_uint16,ctypes.c_void_p,ctypes.c_void_p]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_profile_exact_order_length_crc_and_guard_bytes(self):
  numbers=[0x30,0,0x05000031,8,1,200000000,0xffffffff,8,0,2,4,1,3]
  v=(ctypes.c_uint32*13)(*numbers);out=ctypes.create_string_buffer(b'\xa5'*80,80)
  self.assertEqual(self.lib.rio_usb_profile_request(0xc1,0x55,0,0,64,ctypes.addressof(out)+8,v),1)
  body=b'RIOP'+struct.pack('<HH13I',1,64,*numbers)
  self.assertEqual(out.raw,b'\xa5'*8+body+struct.pack('<I',zlib.crc32(body))+b'\xa5'*8)
 def test_other_requests_do_not_touch_output_or_dereference_values(self):
  cases=[(t,0x55,0,0,64) for t in range(256) if t!=0xc1]
  cases += [(0xc1,r,0,0,64) for r in range(256) if r!=0x55]
  cases += [(0xc1,0x55,1,0,64),(0xc1,0x55,0,1,64),(0xc1,0x55,0,0,63),(0xc1,0x55,0,0,65)]
  for args in cases:
   out=ctypes.create_string_buffer(b'\xa5'*64,64)
   self.assertEqual(self.lib.rio_usb_profile_request(*args,out,None),0);self.assertEqual(out.raw,b'\xa5'*64)
 def test_release_transport_excludes_benchmark_only_profile_request(self):
  w=WinUSB.__new__(WinUSB);w.endpoints=(1,0x81)
  for args in ((0x41,0x55,0,0,64),(0xc0,0x55,0,0,64),(0xc1,0x55,1,0,64),(0xc1,0x55,0,1,64),(0xc1,0x55,0,0,65)):
   with self.assertRaisesRegex(ValueError,'Unsupported'):w.control(*args)
  for endpoints in ((1,0x81),(1,0x82)):
   w.endpoints=endpoints
   with self.assertRaisesRegex(ValueError,'Unsupported'):w.control(0xc1,0x55,0,0,64)

if __name__=='__main__':unittest.main()

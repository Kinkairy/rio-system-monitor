"""Independent register/transaction oracle. All tests offline; no USB device."""
import ctypes
import pathlib
import struct
import subprocess
import tempfile
import unittest
import zlib
from unittest.mock import patch
from rio_monitor.lt168b_storage_probe import decode_reply, sfdp_density, collect, main

ROOT=pathlib.Path(__file__).resolve().parents[1]
HARNESS=r"""
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static uint32_t q[62],oldq[62],clockv,gpio,xip,oldclock,oldgpio,oldxip;
static unsigned mode,reads,txcount,rxcount,selected,selects;
static uint8_t tx[64];
void init(unsigned m,uint32_t seed) {
 unsigned i;mode=m;reads=txcount=rxcount=selected=selects=0;
 for(i=0;i<62;i++)q[i]=seed;
 q[2]=0;clockv=seed&0x3fffffff;gpio=(seed&~0x40020000u)|0x200;xip=seed;
 if(mode==4)gpio=(gpio|0x40020000u)&~0x200u;
 memcpy(oldq,q,sizeof(q));oldclock=clockv;oldgpio=gpio;oldxip=xip;
}
uint32_t flash_read32(uint32_t a) {
 reads++;
 if(a==0x4003000c)return clockv;
 if(a==0x40010020)return gpio;
 if(a==0x40010014)return xip;
 if(a==0x70000028) {
   if(mode==3)return 1;
   if(mode==1)return 0;
   if(mode==2 || (mode==5 && txcount>=10))return 4;
   return 12;
 }
 if(a==0x70000060)return (rxcount++*7u+3u)&255u;
 if(a>=0x70000000 && a<=0x700000f4 && !(a&3))return q[(a-0x70000000)/4];
 abort();
}
void flash_write32(uint32_t a,uint32_t v) {
 if(a==0x4003000c){clockv=v&0x3fffffff;return;}
 if(a==0x40010014){xip=v;return;}
 if(a==0x40010020){
  unsigned now=(v&0x40020000u)==0x40020000u && !(v&0x200u);
  if(now && !selected)selects++;
  selected=now;gpio=v;return;
 }
 if(a==0x70000060){if(!selected || txcount>=64)abort();tx[txcount++]=(uint8_t)v;return;}
 if(a>=0x70000000 && a<=0x700000f4 && !(a&3)){q[(a-0x70000000)/4]=v;return;}
 abort(); /* QSPI0/QSPI2/panel/backlight and arbitrary writes forbidden */
}
unsigned restored(void){return !memcmp(q,oldq,sizeof(q))&&clockv==oldclock&&gpio==oldgpio&&xip==oldxip;}
unsigned count_reads(void){return reads;}
unsigned count_selects(void){return selects;}
unsigned copy_tx(uint8_t *out){memcpy(out,tx,txcount);return txcount;}
"""

class ProbeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();d=pathlib.Path(cls.tmp.name)
  (d/'h.c').write_text(HARNESS)
  subprocess.run(['cc','-std=c99','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
   '-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DRIO_FLASH_TEST',
   str(d/'h.c'),str(ROOT/'firmware/lt168b/board_flash_probe.c'),str(ROOT/'firmware/lt168b/rio_usb.c'),'-o',str(d/'p.so')],check=True)
  cls.lib=ctypes.CDLL(str(d/'p.so'))
  cls.lib.init.argtypes=[ctypes.c_uint,ctypes.c_uint32]
  cls.lib.rio_flash_probe_request.argtypes=[ctypes.c_uint8,ctypes.c_uint8,ctypes.c_uint16,ctypes.c_uint16,ctypes.c_uint16,ctypes.c_void_p]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def call(self,op=0,offset=0,mode=0,seed=0,type_=0xc1,request=0x54,length=64):
  self.lib.init(mode,seed)
  out=ctypes.create_string_buffer(b'\xa5'*80,80)
  n=self.lib.rio_flash_probe_request(type_,request,op,offset,length,ctypes.addressof(out)+8)
  self.assertEqual(out.raw[:8]+out.raw[72:],b'\xa5'*16)
  self.assertTrue(self.lib.restored())
  tx=ctypes.create_string_buffer(64);size=self.lib.copy_tx(tx)
  return n,out.raw[8:72],tx.raw[:size]
 def test_exact_read_transactions_and_restore(self):
  cases=[(0,0,b'\x9f',8),(1,0,b'\x5a\0\0\0\0',44),
    (1,4095,b'\x5a\0\x0f\xff\0',1),(2,255,b'\x03\0\0\xff',44),
    (2,4095,b'\x03\0\x0f\xff',1)]
  for op,off,prefix,n in cases:
   for seed in (0,0xffffffff,0xa55a5aa5):
    with self.subTest(op=op,offset=off,seed=seed):
     length,out,tx=self.call(op,off,seed=seed)
     self.assertEqual(length,64);self.assertEqual(tx,prefix+b'\xff'*n)
     self.assertEqual(decode_reply(out,op,off),bytes(((i+len(prefix))*7+3)&255 for i in range(n)))
     self.assertEqual(self.lib.count_selects(),1)
 def test_invalid_requests_have_zero_io(self):
  cases=[dict(type_=t) for t in range(256) if t!=0xc1]
  cases += [dict(request=t) for t in range(256) if t!=0x54]
  cases += [dict(op=o) for o in (3,6,0x20,0x60,0xffff)]
  cases += [dict(offset=i) for i in (1,4096,65535)]
  cases += [dict(length=n) for n in (0,1,63,65,65535)]
  for kw in cases:
   with self.subTest(**kw):
    n,out,tx=self.call(**kw);self.assertEqual(n,0);self.assertEqual(tx,b'')
    self.assertEqual(self.lib.count_reads(),0);self.assertEqual(out,b'\xa5'*64)
 def test_timeout_and_busy_do_not_replay_or_leak_partial_data(self):
  for mode in (1,2,3,4,5):
   with self.subTest(mode=mode):
    n,out,tx=self.call(2,mode=mode)
    self.assertEqual(n,64);self.assertEqual(out[16:60],bytes(44))
    self.assertLess(self.lib.count_reads(),100100)
    self.assertEqual(tx,(b'\x03'+bytes(3)+b'\xff'*6) if mode==5 else (b'\x03' if mode==2 else b''))
    with self.assertRaises(OSError):decode_reply(out,2,0)
 def test_corrupt_short_stale_and_error_reply(self):
  _,good,_=self.call()
  for at in range(64):
   bad=bytearray(good);bad[at]^=1
   with self.assertRaises(ValueError):decode_reply(bytes(bad),0,0)
  for n in (0,63,65):
   with self.assertRaises(ValueError):decode_reply((good+b'x')[:n],0,0)
  for at in (6,8,10,12,13,24):
   bad=bytearray(good);bad[at]^=1;bad[60:]=struct.pack('<I',zlib.crc32(bad[:60]))
   with self.assertRaises((ValueError,OSError)):decode_reply(bad,0,0)
 def test_host_transport_rejects_write_or_out_of_bounds(self):
  from rio_monitor.winusb import WinUSB
  w=object.__new__(WinUSB);w.endpoints=(2,0x81)
  for args in ((0x41,0x54,0,0,64),(0xc1,0x54,6,0,64),(0xc1,0x54,0,1,64),(0xc1,0x54,1,4096,64),(0xc1,0x54,1,0,65)):
   with self.assertRaisesRegex(ValueError,'Unsupported'):w.control(*args)
  with self.assertRaisesRegex(ValueError,'bench profile'):w.control(0xc1,0x54,1,4095,64)
 def test_collect_stops_on_first_bad_packet_without_reset(self):
  lib=self.lib
  class Fake:
   def __init__(self):self.calls=[]
   def control(self,*args):
    self.calls.append(args)
    if args[1]==0x52:
     b=ctypes.create_string_buffer(32);lib.rio_usb_hello(b);return b.raw
    return bytes(64)
  t=Fake()
  with self.assertRaises(ValueError):collect(t)
  self.assertEqual(t.calls,[(0xc1,0x52,0,0,32),(0xc1,0x54,0,0,64)])
 def test_full_read_pipeline_uses_only_bounded_in_requests(self):
  from rio_monitor.lt168b_display import HELLO
  density=DensityTests().fixture();sfdp=bytes(density)+bytes(4096-len(density))
  resource=bytes(i%256 for i in range(4096))
  class Fake:
   def __init__(self,jedec):self.calls=[];self.jedec=jedec
   def control(self,*args):
    self.calls.append(args)
    if args[1]==0x52:
     b=HELLO.pack(b'RIO1',1,32,480,480,32,16,1,1048,460800,0)
     return b[:-4]+struct.pack('<I',zlib.crc32(b[:-4]))
    type_,req,op,off,length=args
    if (type_,req,length)!=(0xc1,0x54,64):raise AssertionError(args)
    payload=self.jedec if op==0 else (sfdp if op==1 else resource)[off:off+44]
    b=bytearray(64);b[:6]=b'RISP\x01'+bytes([op]);struct.pack_into('<HHH',b,6,0,off,len(payload));b[12]=1;b[16:16+len(payload)]=payload
    b[60:]=struct.pack('<I',zlib.crc32(b[:60]));return bytes(b)
  t=Fake(bytes.fromhex('ef40180000000000'));out=collect(t)
  self.assertEqual(out['sfdp_density_bytes'],16777216);self.assertIsNone(out['available_media_bytes'])
  self.assertEqual(bytes.fromhex(out['resource_header_hex']),resource)
  self.assertEqual(len(t.calls),190)
  for identity in ('0000000000000000','ffffffffffffffff','00efaa2100000000','efaa210000000000'):
   t=Fake(bytes.fromhex(identity));out=collect(t)
   self.assertEqual(len(t.calls),2);self.assertIsNone(out['sfdp_density_bytes'])
   self.assertEqual(out['identification'],'unqualified_identity_no_further_reads')
 def test_process_mutex_blocks_device_open(self):
  with tempfile.TemporaryDirectory() as d,patch('rio_monitor.settings.acquire_instance',return_value=None),patch('rio_monitor.display_protocols.enumerate_paths') as enum:
   path=pathlib.Path(d)/'report.json'
   self.assertEqual(main(['--journal',str(path)]),1);enum.assert_not_called()
   self.assertIn('Close RIO',path.read_text())
   with self.assertRaises(FileExistsError):main(['--journal',str(path)])

class DensityTests(unittest.TestCase):
 def fixture(self,density=0x07ffffff):
  d=bytearray(256);d[:8]=b'SFDP\x06\x01\x00\xff';d[8:16]=b'\0\x06\x01\x09\x30\0\0\xff'
  struct.pack_into('<I',d,0x34,density);return d
 def test_bit_density_not_free_media_space(self):
  self.assertEqual(sfdp_density(self.fixture()),16*1024*1024)
  self.assertEqual(sfdp_density(self.fixture(0x8000001b)),16*1024*1024)
 def test_unknown_and_malformed_are_not_assumed_16m(self):
  for data in (b'',b'\xff'*4096,b'\0'*4096,self.fixture()[:40],self.fixture(0xffffffff),self.fixture(0x80000002),self.fixture(7)):
   self.assertIsNone(sfdp_density(data))
  for at,value in ((0,0),(5,2),(6,255),(8,1),(10,2),(11,8),(12,250),(12,0),(15,0)):
   d=self.fixture();d[at]=value;self.assertIsNone(sfdp_density(d))

if __name__=='__main__':unittest.main()

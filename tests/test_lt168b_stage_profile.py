"""Diagnostic build through the actual receiver/SIE oracle, including wrap."""
import ctypes
from pathlib import Path
import subprocess,tempfile,unittest
import test_lt168b_decode_once as decode
import test_lt168b_usb_receive as usb

CLOCK = """
#include <stdint.h>
uint16_t profile_tick(void);
#define RIO_STAGE_PROFILE 1
#define RIO_PROFILE_TICK() profile_tick()
"""
TICK = """
static uint16_t counter=2;
uint16_t profile_tick(void) {return counter--;}
"""

class ProfilePixelTests(decode.DecodeOnceTests):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        directory=Path(cls.tmp.name)
        source=directory/'observe.c'
        source.write_text(CLOCK+TICK+decode.WRAPPER)
        binary=directory/'receiver.so'
        fw=decode.ROOT/'firmware/lt168b'
        subprocess.run(['cc','-std=gnu99','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-I',str(fw),str(source),
            str(fw/'rio_lz4.c'),'-o',str(binary)],check=True)
        cls.lib=ctypes.CDLL(str(binary))
        cls.lib.rio_stream_size.restype=ctypes.c_size_t
        cls.lib.rio_stream_init.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        cls.lib.rio_stream_feed.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.rio_stream_staging.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,
            ctypes.c_void_p,decode.presentation.SYNC,ctypes.c_void_p]
        for n in ('rio_stream_completed','rio_stream_presentations','rio_stream_fallbacks'):
            getattr(cls.lib,n).argtypes=[ctypes.c_void_p]
            getattr(cls.lib,n).restype=ctypes.c_uint32
        cls.lib.oracle_watch.argtypes=[ctypes.c_void_p]
        cls.lib.oracle_offset.argtypes=cls.lib.oracle_length.argtypes=[ctypes.c_uint]
        cls.frame=bytes((i*29+i//97)%256 for i in range(460800))

    def test_stage_counts_reset_and_wrap(self):
        stats=(ctypes.c_uint32*9).in_dll(self.lib,'rio_stage_ticks')
        for count in (207,208,450):
            self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16)
            self.bind()
            old=self.baseline()
            prior=list(stats)
            new=self.change_tiles(old,range(count))
            parts=self.parts(new,2,old)
            compressed=sum(p[5]==5 for p in parts)
            self.assertEqual(self.feed(b''.join(parts),13),1)
            self.expect_pixels(new)
            now=list(stats)
            self.assertEqual(now[7]-prior[7],compressed if count<=207 else 0)
            self.assertEqual(now[8]-prior[8],0 if count<=207 else compressed)
            self.assertEqual(now[0]-prior[0],len(parts))
            self.assertEqual(now[1]-prior[1],compressed if count<=207 else 0)
            self.assertEqual(now[2]-prior[2],0 if count<=207 else compressed)
        self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16)
        self.assertEqual(list(stats),[0]*9)

class ProfileUsbTests(usb.UsbReceiveTests):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.directory=Path(cls.tmp.name)
        header=usb.HEADER.replace('#endif',"typedef struct {uint16_t PMR,PCSR,reserved,PCNTR;} test_pit;\nextern test_pit test_pit_regs;\n#define PIT0 (&test_pit_regs)\n#endif")
        (cls.directory/'LT168.h').write_text(header)
        (cls.directory/'lt168_clock.h').write_text('#define SYS_CLOCK 200000000u\n')
        (cls.directory/'profile_clock.h').write_text(CLOCK)
        harness=usb.HARNESS.replace('static void fake_w1c(uint8_t mask);','test_pit test_pit_regs;\n'+TICK+'\nstatic void fake_w1c(uint8_t mask);')
        extra=r"""
 if(!strcmp(name,"profile")) {
  rio_board_usb_init(guarded_pixels+8);
  assert(PIT0->PCSR==0xa01 && PIT0->PMR==0xffff);
  set_configuration(1);
  for(i=0;i<9;++i)rio_stage_ticks[i]=100+i;
  for(i=0;i<5;++i) {
   memset(control_out,0,8);control_out[0]=0xc1;control_out[1]=0x56;control_out[6]=64;
   if(i==1)control_out[2]=1;
   if(i==2)control_out[4]=1;
   if(i==3)control_out[6]=63;
   if(i==4)control_out[0]=0x41;
   setup();
   if(i)assert(USB->U32_ENDPT0.EP_STALL);
   else {
    assert(!memcmp(control_in,"RIOP\1\0\100\0",8));
    assert(!memcmp(control_in+8,rio_stage_ticks,36));
    assert(stream.completed==0 && rio_stage_ticks[7]==107);
   }
  }
  reset_stream();for(i=0;i<9;++i)assert(!rio_stage_ticks[i]);
 } else
"""
        harness=harness.replace(' if(!strcmp(name,"overlap")) {',extra+' if(!strcmp(name,"overlap")) {')
        (cls.directory/'harness.c').write_text(harness)
        fw=usb.ROOT/'firmware/lt168b';cls.executable=cls.directory/'receiver'
        subprocess.run(['cc','-std=gnu99','-O2','-no-pie','-Wall','-Wextra','-Werror',
          '-Wno-pointer-to-int-cast','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
          '-include',str(cls.directory/'profile_clock.h'),'-I'+str(cls.directory),'-I'+str(fw),
          '-DBOARD_USB_SOURCE="'+str(fw/'board_usb.c')+'"',str(cls.directory/'harness.c'),
          str(fw/'rio_stream.c'),str(fw/'rio_usb.c'),str(fw/'rio_lz4.c'),'-o',str(cls.executable)],check=True)

    def test_profile_endpoint_is_readonly_and_bounded(self):self.case('profile')

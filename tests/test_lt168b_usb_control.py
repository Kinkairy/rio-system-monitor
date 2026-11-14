"""Control-transfer completion, reset and abort oracle; native only, no USB.

The default source is the retained firmware. RIO_USB_AUDIT_SOURCE may select an
explicit archived source for analysis; this never emits a flashable binary.
SIE bank/reset timing and DMA electrical behavior remain hardware evidence gaps.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_lt168b_usb_receive import HEADER

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "LT168.h"
#include "rio_stream.h"
test_usb test_usb_regs;
test_clock test_clock_regs;
test_rgb test_rgb_regs;
static void w1c(uint8_t);
static void bank_reset(void);
static int feed(rio_stream *,const uint8_t *,size_t);
#define RIO_USB_W1C(m) w1c(m)
#define RIO_USB_RESET_BANKS() bank_reset()
#define rio_stream_feed feed
#include BOARD_USB_SOURCE
#undef rio_stream_feed
void rio_board_delay_ms(unsigned n){(void)n;}
void rio_board_cache_status(uint32_t p[5]){memset(p,0,20);}
int rio_flash_probe_request(uint8_t a,uint8_t b,uint16_t c,uint16_t d,uint16_t n,uint8_t p[64]){(void)a;(void)b;(void)c;(void)d;(void)n;(void)p;return 0;}
typedef struct {unsigned ep,in,bank;} event;
static event fifo[4];
static unsigned queued,banks[3][2],in_transactions,out_transactions,feeds;
static uint16_t pixels[480*480];
static void refresh(void){
 if(queued){USB->U32_STAT.ENDP=fifo[0].ep;USB->U32_STAT.TX=fifo[0].in;USB->U32_STAT.ODD=fifo[0].bank;USB->U32_INT_STAT.TOKDNE=1;}
 else {USB->STAT=0;USB->U32_INT_STAT.TOKDNE=0;}
}
static void push(unsigned ep,unsigned in,unsigned bank){assert(queued<4);fifo[queued++]=(event){ep,in,bank};refresh();}
static void bank_reset(void){memset(banks,0,sizeof(banks));USB->U32_CTL.ODD_RST=0;}
static void w1c(uint8_t mask){
 /* Retained source explicitly writes ODD_RST immediately before token pop.
  * Audit source uses a reset hook. Both paths apply the documented bank reset. */
 if(USB->U32_CTL.ODD_RST)bank_reset();
 if((mask&8)&&queued){--queued;memmove(fifo,fifo+1,queued*sizeof(*fifo));}
 USB->INT_STAT&=~(uint32_t)mask;refresh();
}
static void drain(void){unsigned budget=32;while(queued){assert(budget--);rio_board_usb_poll();}}
static int feed(rio_stream *s,const uint8_t *p,size_t n){(void)s;(void)p;(void)n;++feeds;return 0;}
static void cold(void){
 memset(&test_usb_regs,0,sizeof(test_usb_regs));queued=feeds=in_transactions=out_transactions=0;
 bank_reset();display=pixels;reset_usb();USB->INT_STAT=0;
}
static int setup_host(uint8_t type,uint8_t req,uint16_t val,uint16_t idx,uint16_t len){
 unsigned bank=banks[0][0];uint8_t *p;
 if(USB->U32_CTL.TXSUSPEND||queued==4||!(USB->ENDPT0&8)||!(table[bank].stat&0x80))return 0;
 p=(uint8_t *)(uintptr_t)table[bank].address;
 p[0]=type;p[1]=req;p[2]=val;p[3]=val>>8;p[4]=idx;p[5]=idx>>8;p[6]=len;p[7]=len>>8;
 table[bank].count=8;table[bank].stat=(table[bank].stat&0x40)|(13u<<2);
 banks[0][0]^=1;USB->U32_CTL.TXSUSPEND=1;push(0,0,bank);return 1;
}
static int host_in(unsigned expected_pid,uint8_t *copy,unsigned *n,int acknowledge){
 unsigned bank=banks[0][1],slot=2+bank;
 if(USB->U32_CTL.TXSUSPEND||queued==4||!(USB->ENDPT0&4)||USB->U32_ENDPT0.EP_STALL||!(table[slot].stat&0x80))return 0;
 if(((table[slot].stat>>6)&1)!=expected_pid)return -1;
 *n=table[slot].count;assert(*n<=64);
 if(copy)memcpy(copy,(void *)(uintptr_t)table[slot].address,*n);
 if(acknowledge){table[slot].stat=(table[slot].stat&0x40)|(9u<<2);banks[0][1]^=1;push(0,1,bank);++in_transactions;}
 return 1;
}
static int status_out_host(void){
 unsigned bank=banks[0][0];
 if(USB->U32_CTL.TXSUSPEND||queued==4||!(table[bank].stat&0x80)||!(table[bank].stat&0x40))return 0;
 table[bank].count=0;table[bank].stat=0x40|4; banks[0][0]^=1;push(0,0,bank);++out_transactions;return 1;
}
/* Completion success is distinct from payload length. A missing zero-byte
 * status IN is a timeout, never a successful 0-byte response. */
static int finish_control(unsigned requested,unsigned expected,uint8_t *copy){
 unsigned total=0,n=999,pid=1,packets=0;
 if(USB->U32_ENDPT0.EP_STALL)return -2;
 if(!requested){
  if(host_in(1,0,&n,1)!=1||n!=0)return -1;
  drain();return 0;
 }
 do {
  if(host_in(pid,copy?copy+total:0,&n,1)!=1)return -1;
  pid^=1;total+=n;++packets;drain();
  if(packets>16)return -1;
 }while(n==64&&total<requested);
 if(total!=expected||!status_out_host())return -1;
 drain();return (int)total;
}
static int control_host(unsigned t,unsigned r,unsigned v,unsigned idx,unsigned len,unsigned expected,uint8_t *out){
 if(!setup_host(t,r,v,idx,len))return -1;
 drain();return finish_control(len,expected,out);
}
static void enumerate(void){
 uint8_t p[256];unsigned i;
 cold();assert(control_host(0x80,6,0x0100,0,8,8,p)==8);
 assert(setup_host(0,5,41,0,0));drain();assert(USB->ADDR==0);
 assert(finish_control(0,0,0)==0&&USB->ADDR==41);
 assert(control_host(0x80,6,0x0100,0,18,18,p)==18);
 assert(control_host(0x80,6,0x0200,0,9,9,p)==9);
 assert(control_host(0x80,6,0x0200,0,255,32,p)==32);
 assert(control_host(0,9,1,0,0,0,0)==0&&configuration==1);
 assert(control_host(0xc0,RIO_USB_MS_VENDOR,0,4,255,40,p)==40);
 assert(control_host(0xc1,RIO_USB_MS_VENDOR,0,5,255,142,p)==142);
 for(i=0;i<3;++i)assert(control_host(0xc1,0x52,0,0,32,32,p)==32&&!memcmp(p,"RIO1",4));
}
static int bulk_packet(unsigned pid){
 unsigned bank=banks[1][0],slot=4+bank;
 if(USB->U32_CTL.TXSUSPEND||queued==4||!(table[slot].stat&0x80))return 0;
 if(((table[slot].stat>>6)&1)!=pid)return -1;
 memset((void *)(uintptr_t)table[slot].address,0x5a,13);table[slot].count=13;
 table[slot].stat=(table[slot].stat&0x40)|4;banks[1][0]^=1;push(1,0,bank);return 1;
}
int main(int argc,char **argv){
 const char *name;uint8_t p[256];unsigned i,n,old,slot;assert(argc==2);name=argv[1];enumerate();
 if(!strcmp(name,"enumeration")){assert(USB->ADDR==41&&configuration==1);}
 else if(!strcmp(name,"winusb_init_sequence")){
  for(i=0;i<16;++i){
   assert(control_host(0xc1,0x52,0,0,32,32,p)==32);
   assert(control_host(2,1,0,1,0,0,0)==0);
   assert(control_host(2,1,0,0x82,0,0,0)==0);
   assert(control_host(0x41,0x53,0,0,0,0,0)==0);
   assert(bulk_packet(0)==1);drain();assert(bulk_packet(1)==1);drain();
  }assert(feeds==32);
 }
 else if(!strcmp(name,"missing_status_rejected")){
  assert(setup_host(0x41,0x53,0,0,0));drain();table[2].stat=table[3].stat=0;
  old=in_transactions;assert(finish_control(0,0,0)==-1&&in_transactions==old);
 }
 else if(!strcmp(name,"wrong_bank_rejected")){
  assert(setup_host(0x41,0x53,0,0,0));drain();slot=2+banks[0][1];
  table[slot^1]=table[slot];table[slot].stat=0;
  assert(finish_control(0,0,0)==-1);
 }
 else if(!strcmp(name,"wrong_data_pid_rejected")){
  assert(setup_host(0x41,0x53,0,0,0));drain();table[2+banks[0][1]].stat&=~0x40;
  assert(finish_control(0,0,0)==-1);
 }
 else if(!strcmp(name,"missing_data_rejected")){
  assert(setup_host(0xc1,0x52,0,0,32));drain();table[2].stat=table[3].stat=0;
  assert(finish_control(32,32,p)==-1);
 }
 else if(!strcmp(name,"zero_status_exactly_one")){
  for(i=0;i<8;++i){old=in_transactions;assert(control_host(0x41,0x53,0,0,0,0,0)==0);assert(in_transactions==old+1);assert(host_in(1,p,&n,1)==0);}
 }
 else if(!strcmp(name,"multi_packet_pid")){
  for(i=0;i<16;++i)assert(control_host(0xc1,RIO_USB_MS_VENDOR,0,5,255,142,p)==142);
 }
 else if(!strcmp(name,"aborted_setup")){
  assert(setup_host(0xc1,RIO_USB_MS_VENDOR,0,5,255));drain();
  assert(control_host(0xc1,0x52,0,0,32,32,p)==32&&!memcmp(p,"RIO1",4));
 }
 else if(!strcmp(name,"abort_after_first_packet")){
  assert(setup_host(0xc1,RIO_USB_MS_VENDOR,0,5,255));drain();assert(host_in(1,p,&n,1)==1&&n==64);drain();
  assert(control_host(0xc1,0x52,0,0,32,32,p)==32&&!memcmp(p,"RIO1",4));
 }
 else if(!strcmp(name,"in_ack_lost_retry")){
  uint8_t q[64];unsigned m;assert(setup_host(0xc1,0x52,0,0,32));drain();
  old=in_transactions;assert(host_in(1,p,&n,0)==1&&n==32&&in_transactions==old);
  assert(host_in(1,q,&m,1)==1&&m==n&&!memcmp(p,q,n));drain();assert(status_out_host());drain();
  assert(control_host(0x41,0x53,0,0,0,0,0)==0);
 }
 else if(!strcmp(name,"stall_then_setup")){
  assert(control_host(0xc1,0xff,0,0,1,1,p)==-2);
  assert(control_host(0xc1,0x52,0,0,32,32,p)==32);
 }
 else if(!strcmp(name,"status_out_delayed")){
  assert(setup_host(0xc1,0x52,0,0,32));drain();assert(host_in(1,p,&n,1)==1&&n==32);
  assert(status_out_host());assert(queued==2);drain();
  assert(control_host(0x41,0x53,0,0,0,0,0)==0);
 }
 else if(!strcmp(name,"bus_reset_during_control")){
  assert(setup_host(0,5,27,0,0));drain();assert(host_in(1,p,&n,1)==1&&n==0);
  USB->U32_INT_STAT.USB_RST=1;USB->U32_CTL.TXSUSPEND=0;bank_reset();rio_board_usb_poll();drain();
  assert(USB->ADDR==0&&!configuration&&!address_pending);
  assert(control_host(0x80,6,0x0100,0,18,18,p)==18);
 }
 else if(!strcmp(name,"unconfigure_reconfigure")){
  assert(control_host(0,9,0,0,0,0,0)==0&&!configuration);
  assert(control_host(0,9,1,0,0,0,0)==0&&configuration);
  assert(control_host(0xc1,0x52,0,0,32,32,p)==32&&bulk_packet(0)==1);drain();
 }
 else if(!strcmp(name,"short_and_zlp")){
  assert(setup_host(0xc1,0x52,0,0,32));drain();
  memset(p,0x37,64);table[2].stat=table[3].stat=0;reply(p,64,128);
  old=in_transactions;assert(finish_control(128,64,p)==64&&in_transactions==old+2);
 }

 else if(!strcmp(name,"abort_pending_address")){
  unsigned address=USB->ADDR;assert(setup_host(0,5,37,0,0));drain();assert(USB->ADDR==address);
  assert(control_host(0xc1,0x52,0,0,32,32,p)==32&&USB->ADDR==address&&!address_pending);
 }
 else if(!strcmp(name,"control_with_pending_bulk")){
  assert(bulk_packet(0)==1);assert(setup_host(0xc1,0x55,0,0,64));assert(queued==2);
  assert(bulk_packet(1)==0);drain();assert(finish_control(64,64,p)==64&&!memcmp(p,"RIOP",4));
  assert(bulk_packet(1)==1);drain();assert(feeds==2);
 }
 else if(!strcmp(name,"reset_pending_frame_ack")){
  ack_pending=1;arm(10,bulk_in,24,0x88);
  assert(control_host(0xc1,0x55,0,0,64,64,p)==64&&ack_pending);
  assert(control_host(0x41,0x53,0,0,0,0,0)==0&&!ack_pending&&!table[10].stat&&!table[11].stat);
  assert(bulk_packet(0)==1);drain();assert(feeds==1);
 }
 else if(!strcmp(name,"set_interface_restarts_stream")){
  assert(bulk_packet(0)==1);drain();
  assert(control_host(1,11,0,0,0,0,0)==0&&bulk_packet(0)==1);drain();assert(feeds==2);
 }
 else if(!strcmp(name,"bus_reset_full_fifo")){
  assert(setup_host(0,5,27,0,0));drain();assert(host_in(1,p,&n,1)==1);
  push(1,0,0);push(2,1,0);push(1,0,1);assert(queued==4);
  USB->U32_INT_STAT.USB_RST=1;USB->U32_CTL.TXSUSPEND=0;bank_reset();rio_board_usb_poll();drain();
  assert(!configuration&&!address_pending&&USB->ADDR==0);
  assert(control_host(0x80,6,0x0100,0,18,18,p)==18);
 }
 else assert(!"unknown case");
 printf("PASS %s in=%u out=%u feeds=%u\n",name,in_transactions,out_transactions,feeds);return 0;
}
"""

CASES=('enumeration','winusb_init_sequence','missing_status_rejected','wrong_bank_rejected',
       'wrong_data_pid_rejected','missing_data_rejected','zero_status_exactly_one',
       'multi_packet_pid','aborted_setup','abort_after_first_packet','in_ack_lost_retry',
       'stall_then_setup','status_out_delayed','bus_reset_during_control',
       'unconfigure_reconfigure','short_and_zlp','abort_pending_address',
       'control_with_pending_bulk','reset_pending_frame_ack','set_interface_restarts_stream',
       'bus_reset_full_fifo')

class UsbControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('cc')
        if not compiler:raise unittest.SkipTest('Native compiler required')
        cls.tmp=tempfile.TemporaryDirectory();directory=Path(cls.tmp.name)
        (directory/'LT168.h').write_text(HEADER)
        (directory/'lt168_clock.h').write_text('#define SYS_CLOCK 200000000u\n')
        (directory/'control.c').write_text(HARNESS)
        fw=ROOT/'firmware/lt168b';source=Path(os.environ.get('RIO_USB_AUDIT_SOURCE',str(fw/'board_usb.c')))
        cls.executable=directory/'control'
        subprocess.run([compiler,'-std=gnu99','-O2','-no-pie','-Wall','-Wextra','-Werror',
                        '-Wno-pointer-to-int-cast','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
                        '-I'+str(directory),'-I'+str(fw),'-DBOARD_USB_SOURCE="'+str(source)+'"',
                        str(directory/'control.c'),str(fw/'rio_stream.c'),str(fw/'rio_usb.c'),
                        str(fw/'rio_lz4.c'),'-o',str(cls.executable)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self,name):
        p=subprocess.run([str(self.executable),name],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertIn('PASS '+name,p.stdout)

for _name in CASES:
    setattr(UsbControlTests,'test_'+_name,lambda self,name=_name:self.run_case(name))

if __name__=='__main__':unittest.main()

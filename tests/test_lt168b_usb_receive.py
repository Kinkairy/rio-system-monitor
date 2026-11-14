"""Actual board USB receiver against a native SIE/event oracle; never USB I/O."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from rio_monitor.lt168b_stream import encode_frame

ROOT = Path(__file__).resolve().parents[1]

HEADER = r'''
#ifndef TEST_LT168_H
#define TEST_LT168_H
#include <stdint.h>
typedef struct {
 union {uint32_t INT_STAT; struct {unsigned USB_RST:1,ERROR:1,SOF_TOK:1,TOKDNE:1,SLEEP:1,RESUME:1,r0:1,STALL:1;} U32_INT_STAT;};
 union {uint32_t STAT; struct {unsigned r1:2,ODD:1,TX:1,ENDP:4;} U32_STAT;};
 union {uint32_t CTL; struct {unsigned USB_EN:1,ODD_RST:1,RESUME:1,HOST_MODE_EN:1,RESET:1,TXSUSPEND:1;} U32_CTL;};
 union {uint32_t ENDPT0; struct {unsigned HS:1,EP_STALL:1,TXEN:1,RXEN:1;} U32_ENDPT0;};
 uint32_t ENDPT1,ENDPT2,ENDPT3,ENDPT4,ENDPT5,ENDPT6,ENDPT7;
 uint32_t ADDR,ERR_STAT,ERR_ENB,INT_ENB,EBT_PAGE_01,EBT_PAGE_02,EBT_PAGE_03;
 struct {unsigned DP_HIGH:1;} U32_USBPHY_CTRL1;
 struct {unsigned DP_PU:1;} U32_USB_PHY_OBSERVE;
 struct {unsigned USB_SFT_RESET:1,USBPHYCLKEN:1;} U32_USB_RESMEN;
 struct {unsigned SEL_48_60M:1,PHY_PD:1,PHY_RESETb:1,PHY_OEN:1;} U32_USBPHY_CTRL3;
 struct {unsigned SUSP:1;} U32_USBPHY_CTRL2;
} test_usb;
typedef struct {uint32_t MSCR;} test_clock;
typedef struct {uint32_t NFTR;struct {unsigned PPVF:1;} U32_RCSR;} test_rgb;
extern test_usb test_usb_regs;
extern test_clock test_clock_regs;
extern test_rgb test_rgb_regs;
#define USB (&test_usb_regs)
#define CLOCK (&test_clock_regs)
#define RGB_CTL (&test_rgb_regs)
#define CLOCK_MSCR_MSCRTEST_MASK 0xc0000000u
#define CLOCK_MSCR_USB_MASK 0x00000040u
#endif
'''

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "LT168.h"
#include "rio_stream.h"
test_usb test_usb_regs;
test_clock test_clock_regs;
test_rgb test_rgb_regs;
static void fake_w1c(uint8_t mask);
static int measured_feed(rio_stream *,const uint8_t *,size_t);
#define RIO_USB_W1C(mask) fake_w1c(mask)
#define rio_stream_feed measured_feed
#include BOARD_USB_SOURCE
#undef rio_stream_feed

void rio_board_delay_ms(unsigned value) {(void)value;}
void rio_board_cache_status(uint32_t values[5]) {memset(values,0,5*sizeof(*values));}
int rio_flash_probe_request(uint8_t t,uint8_t r,uint16_t v,uint16_t i,uint16_t n,uint8_t p[64]) {
 (void)t;(void)r;(void)v;(void)i;(void)n;(void)p;return 0;
}
typedef struct {unsigned endpoint,input;} event;
static event events[8];
static unsigned event_count,token_pops,feed_calls;
static uint16_t guarded_pixels[480*480+16];
static uint8_t received[4096];
static size_t received_size;
static int forced_result,use_real_parser,inject_enabled,reset_during_feed;
static uint8_t injection[64];
static unsigned injection_size;
static const uint8_t *host_data;
static size_t host_size,host_offset;
static unsigned host_step,overlaps;

static void refresh_event(void) {
 if(event_count) {
  USB->U32_STAT.ENDP=events[0].endpoint;USB->U32_STAT.TX=events[0].input;
  USB->U32_INT_STAT.TOKDNE=1;
 } else {USB->STAT=0;USB->U32_INT_STAT.TOKDNE=0;}
}
static void push_event(unsigned endpoint,unsigned input) {
 assert(event_count<8);events[event_count++]=(event){endpoint,input};refresh_event();
}
static void fake_w1c(uint8_t mask) {
 if((mask&8) && event_count) {
  memmove(events,events+1,(--event_count)*sizeof(event));++token_pops;
 }
 USB->INT_STAT&=~(uint32_t)mask;
 refresh_event();
}
static int offer_out(const uint8_t *data,unsigned length) {
 uint8_t *destination;
 if(!(USB->ENDPT1&8u) || !(table[4].stat&0x80u)) return 0;
 assert(length<=64);
 destination=(uint8_t *)(uintptr_t)table[4].address;
 assert(destination==bulk_out[0] || destination==bulk_out[1]);
 memcpy(destination,data,length);table[4].count=(uint16_t)length;
 table[4].stat=(uint8_t)((table[4].stat&0x40u)|4u);
 push_event(1,0);return 1;
}
static int offer_host(void) {
 static const unsigned sizes[]={64,17,1,63,64,31};
 unsigned length=sizes[host_step%6];
 if(host_offset==host_size) return 0;
 if(length>host_size-host_offset)length=(unsigned)(host_size-host_offset);
 if(!offer_out(host_data+host_offset,length)) return 0;
 ++host_step;host_offset+=length;return 1;
}
static int measured_feed(rio_stream *state,const uint8_t *data,size_t length) {
 uint8_t saved[64];
 int result;
 assert(length<=64);
 /* A real completed token must have been consumed before rearming, and
  * the descriptor must now name a different buffer owned by the SIE. */
 assert(token_pops>=feed_calls+1);
 assert(table[4].stat&0x80u);
 assert(table[4].address!=(uint32_t)(uintptr_t)data);
 memcpy(saved,data,length);++feed_calls;
 if(inject_enabled) {inject_enabled=0;assert(offer_out(injection,injection_size));++overlaps;}
 if(use_real_parser && host_offset<host_size) {assert(offer_host());++overlaps;}
 if(reset_during_feed) {USB->U32_INT_STAT.USB_RST=1;reset_during_feed=0;}
 if(use_real_parser) result=rio_stream_feed(state,data,length);
 else {
  assert(received_size+length<=sizeof(received));
  memcpy(received+received_size,data,length);received_size+=length;result=forced_result;
 }
 assert(!memcmp(saved,data,length));
 return result;
}
static void init_case(void) {
 unsigned i;
 memset(&test_usb_regs,0,sizeof(test_usb_regs));event_count=token_pops=feed_calls=0;
 forced_result=use_real_parser=inject_enabled=reset_during_feed=0;
 received_size=host_size=host_offset=host_step=overlaps=0;
 for(i=0;i<480*480+16;++i)guarded_pixels[i]=0xa55a;
 display=guarded_pixels+8;reset_usb();event_count=0;USB->INT_STAT=0;
 set_configuration(1);
 /* Display timing is separately qualified. This oracle covers the unchanged
  * decoder/pixel path after real USB buffer ownership/event scheduling. */
 rio_stream_staging(&stream,staging,sizeof(staging),row,0,0);
 rio_stream_on_presented(&stream,0);
 assert((uintptr_t)table<UINT32_MAX && (uintptr_t)bulk_out<UINT32_MAX);
}
static void ack_complete(void) {
 assert(ack_pending && (table[10].stat&0x80u));table[10].stat=0;push_event(2,1);
}
static void check_guards(void) {
 unsigned i;for(i=0;i<8;++i)assert(guarded_pixels[i]==0xa55a && guarded_pixels[480*480+8+i]==0xa55a);
}
static void setup_reset(void) {
 memset(control_out,0,8);control_out[0]=0x41;control_out[1]=0x53;
 table[0].stat=13u<<2;push_event(0,0);rio_board_usb_poll();
}
static void run_case(const char *name) {
 uint8_t first[64],second[64];unsigned i;
 for(i=0;i<64;++i){first[i]=(uint8_t)i;second[i]=(uint8_t)(255-i);}
 init_case();
 if(!strcmp(name,"overlap")) {
  memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();
  assert(feed_calls==1 && event_count==1 && !(table[4].stat&0x80u));
  assert((table[4].stat&0x40u)==0x40u);
  rio_board_usb_poll();assert(feed_calls==2 && event_count==0);
  assert(received_size==128 && !memcmp(received,first,64) && !memcmp(received+64,second,64));
  assert((table[4].stat&0xc0u)==0x80u);
 } else if(!strcmp(name,"short_zero")) {
  assert(offer_out(first,0));rio_board_usb_poll();
  assert(offer_out(first,17));rio_board_usb_poll();
  assert(offer_out(second,64));rio_board_usb_poll();
  assert(feed_calls==3 && received_size==81 && !memcmp(received,first,17) && !memcmp(received+17,second,64));
 } else if(!strcmp(name,"ack_barrier")) {
  forced_result=1;memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();assert(ack_pending);
  rio_board_usb_poll();assert(rx_waiting && feed_calls==1 && !offer_out(first,64));
  forced_result=0;ack_complete();rio_board_usb_poll();
  assert(!ack_pending && !rx_waiting && feed_calls==2 && received_size==128);
 } else if(!strcmp(name,"ack_before_out_event")) {
  forced_result=1;assert(offer_out(first,64));rio_board_usb_poll();
  ack_complete();assert(offer_out(second,64));assert(event_count==2);
  forced_result=0;rio_board_usb_poll();assert(feed_calls==1 && !(table[4].stat&0x80u));
  rio_board_usb_poll();assert(feed_calls==2 && !memcmp(received+64,second,64));
 } else if(!strcmp(name,"stale_ack")) {
  forced_result=1;memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();rio_board_usb_poll();assert(rx_waiting);
  push_event(2,1);rio_board_usb_poll();assert(ack_pending && rx_waiting && feed_calls==1);
  forced_result=0;ack_complete();rio_board_usb_poll();assert(!ack_pending && feed_calls==2);
 } else if(!strcmp(name,"real_bad_crc")) {
  uint8_t packet[24]={0};use_real_parser=1;
  memcpy(packet,"RIO1",4);packet[4]=1;packet[5]=1;packet[8]=133;packet[12]=1;
  packet[16]=194;packet[17]=1; /*450 tiles, deliberately incorrect CRC.*/
  memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(packet,24));rio_board_usb_poll();assert(failed && ack_pending && ack[6]==1);
  rio_board_usb_poll();assert(feed_calls==1 && stream.completed==0);
  for(i=0;i<230400;++i)assert(display[i]==0xa55a);
 } else if(!strcmp(name,"parser_error")) {
  forced_result=-1;memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();assert(failed && ack_pending && ack[6]==1);
  rio_board_usb_poll();assert(feed_calls==1 && !offer_out(first,64));
  ack_complete();rio_board_usb_poll();assert(failed && !ack_pending && feed_calls==1);
  setup_reset();assert(!failed && !ack_pending && (table[4].stat&0x80u));
 } else if(!strcmp(name,"oversize")) {
  assert(offer_out(first,64));table[4].count=65;rio_board_usb_poll();
  assert(failed && ack_pending && !feed_calls && !(table[4].stat&0x80u));
 } else if(!strcmp(name,"stream_reset")) {
  forced_result=1;memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();rio_board_usb_poll();assert(rx_waiting);
  setup_reset();assert(!rx_waiting && !ack_pending && !failed && out_toggle==0);
  assert(!table[10].stat && (table[4].stat&0xc0u)==0x80u);
  forced_result=0;assert(offer_out(first,7));rio_board_usb_poll();assert(received_size==71);
 } else if(!strcmp(name,"bus_reset")) {
  assert(offer_out(first,64));USB->U32_INT_STAT.USB_RST=1;rio_board_usb_poll();
  assert(!configuration && !feed_calls && !table[4].stat && !rx_waiting);
 } else if(!strcmp(name,"stale_completion")) {
  uint32_t address=table[4].address;push_event(1,0);rio_board_usb_poll();
  assert(!feed_calls && !out_toggle && table[4].address==address && (table[4].stat&0x80u));
 } else if(!strcmp(name,"simultaneous_flags")) {
  assert(offer_out(first,64));USB->INT_STAT|=0x96u;rio_board_usb_poll();
  assert(feed_calls==1 && event_count==0 && USB->INT_STAT==0);
 } else if(!strcmp(name,"reset_during_parse")) {
  reset_during_feed=1;assert(offer_out(first,64));USB->INT_STAT|=0x12u;rio_board_usb_poll();
  assert(USB->U32_INT_STAT.USB_RST && feed_calls==1);
  rio_board_usb_poll();assert(!configuration && !table[4].stat && !rx_waiting);
 } else if(!strcmp(name,"control_during_prefetch")) {
  uint32_t address;memcpy(injection,second,64);injection_size=64;inject_enabled=1;
  assert(offer_out(first,64));rio_board_usb_poll();
  /* Consume pending data first, then interleave a supported control read. */
  rio_board_usb_poll();address=table[4].address;
  memset(control_out,0,8);control_out[0]=0x80;control_out[1]=8;control_out[6]=1;
  table[0].stat=13u<<2;push_event(0,0);rio_board_usb_poll();
  assert(table[4].address==address && (table[4].stat&0x80u) && feed_calls==2);
  assert(control_in[0]==1 && table[2].count==1);
 } else assert(!"unknown test");
 check_guards();printf("PASS %s\n",name);
}
static uint32_t read_u32(FILE *f) {
 uint8_t p[4];assert(fread(p,1,4,f)==4);return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void run_corpus(const char *path) {
 FILE *f=fopen(path,"rb");uint32_t frames,frame;uint64_t pixels=0;unsigned total_overlaps=0,total_calls=0;
 assert(f);frames=read_u32(f);init_case();use_real_parser=1;
 for(frame=0;frame<frames;++frame) {
  uint32_t length=read_u32(f);uint8_t *wire=malloc(length),*expected=malloc(460800);unsigned i,budget=200000;
  assert(wire && expected && length>0);assert(fread(wire,1,length,f)==length);assert(fread(expected,1,460800,f)==460800);
  host_data=wire;host_size=length;host_offset=0;host_step=0;assert(offer_host());
  while(event_count) {assert(budget--);rio_board_usb_poll();assert(!failed);}
  assert(host_offset==host_size && ack_pending && !rx_waiting);
  assert(stream.completed==frame+1 && ack[6]==0);
  for(i=0;i<230400;++i)assert(display[i]==(uint16_t)(((uint16_t)expected[2*i]<<8)|expected[2*i+1]));
  pixels+=230400;check_guards();ack_complete();rio_board_usb_poll();assert(!ack_pending);
  free(wire);free(expected);
 }
 total_overlaps=overlaps;total_calls=feed_calls;assert(fgetc(f)==EOF);fclose(f);
 printf("{\"frames\":%u,\"exact_pixels\":%llu,\"packet_feeds\":%u,\"overlapping_arrivals\":%u}\n",frames,(unsigned long long)pixels,total_calls,total_overlaps);
}
int main(int argc,char **argv) {
 assert(argc==2 || argc==3);
 if(argc==3 && !strcmp(argv[1],"corpus"))run_corpus(argv[2]);else run_case(argv[1]);
 return 0;
}
'''


class UsbReceiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler:
            raise unittest.SkipTest('Native C compiler required')
        cls.tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.tmp.name)
        (cls.directory / 'LT168.h').write_text(HEADER)
        (cls.directory / 'lt168_clock.h').write_text('#define SYS_CLOCK 200000000u\n')
        (cls.directory / 'harness.c').write_text(HARNESS)
        firmware = ROOT / 'firmware/lt168b'
        cls.executable = cls.directory / 'receiver'
        subprocess.run([compiler, '-std=gnu99', '-O2', '-no-pie', '-Wall', '-Wextra', '-Werror',
                        '-Wno-pointer-to-int-cast', '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                        '-I' + str(cls.directory), '-I' + str(firmware),
                        '-DBOARD_USB_SOURCE="' + str(firmware / 'board_usb.c') + '"',
                        str(cls.directory / 'harness.c'), str(firmware / 'rio_stream.c'),
                        str(firmware / 'rio_usb.c'), str(firmware / 'rio_lz4.c'), '-o', str(cls.executable)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def case(self, name):
        result = subprocess.run([str(self.executable), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS ' + name, result.stdout)

    def test_overlapping_arrival_keeps_both_packets(self): self.case('overlap')
    def test_short_and_zero_length_packets(self): self.case('short_zero')
    def test_prefetch_waits_for_frame_ack(self): self.case('ack_barrier')
    def test_ack_never_rearms_over_completed_data(self): self.case('ack_before_out_event')
    def test_stale_ack_cannot_release_waiting_packet(self): self.case('stale_ack')
    def test_real_crc_failure_drops_prefetch_without_pixels(self): self.case('real_bad_crc')
    def test_parser_error_requires_reset(self): self.case('parser_error')
    def test_oversized_packet_rejected(self): self.case('oversize')
    def test_stream_reset_drops_prefetched_state(self): self.case('stream_reset')
    def test_bus_reset_preempts_pending_data(self): self.case('bus_reset')
    def test_stale_event_preserves_owned_buffer(self): self.case('stale_completion')
    def test_w1c_preserves_other_pending_events(self): self.case('simultaneous_flags')
    def test_reset_arriving_during_parse_survives(self): self.case('reset_during_parse')
    def test_control_request_preserves_bulk_owner(self): self.case('control_during_prefetch')

    @classmethod
    def corpus(cls, frames):
        path = cls.directory / 'wire-corpus.bin'
        previous = None
        with path.open('wb') as target:
            target.write(struct.pack('<I', len(frames)))
            for index, pixels in enumerate(frames, 1):
                wire = b''.join(encode_frame(pixels, session=133, frame=index, acknowledged=previous, compression=True))
                target.write(struct.pack('<I', len(wire)))
                target.write(wire)
                target.write(pixels)
                previous = pixels
        result = subprocess.run([str(cls.executable), 'corpus', str(path)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_real_decoder_pixels_through_overlapping_receiver(self):
        first = bytes((i * 29 + i // 97) % 256 for i in range(460800))
        second = bytearray(first)
        second[:2000] = b'\xf8\0' * 1000
        answer = self.corpus([first, bytes(second), bytes(second)])
        self.assertEqual(answer['frames'], 3)
        self.assertEqual(answer['exact_pixels'], 3 * 480 * 480)
        self.assertGreater(answer['overlapping_arrivals'], 100)


if __name__ == '__main__':
    unittest.main()

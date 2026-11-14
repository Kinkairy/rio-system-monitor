/* Explicit diagnostic only. Official LT168B SDK exFlash=QSPI1.
 * No write-enable, erase, program, status write or flash mode-switch command.
 * Restores MMIO configuration; QSPI0 executable flash and QSPI2 untouched. */
#include "rio_usb.h"
#include <string.h>
#ifdef RIO_FLASH_TEST
extern uint32_t flash_read32(uint32_t address);
extern void flash_write32(uint32_t address,uint32_t value);
#else
static uint32_t flash_read32(uint32_t a) {return *(volatile uint32_t *)a;}
static void flash_write32(uint32_t a,uint32_t v) {*(volatile uint32_t *)a=v;}
#endif
#define Q 0x70000000u
#define GPIO 0x40010020u
#define XIP 0x40010014u
#define CLOCK 0x4003000cu
#define CS 0x200u
/* Exact SDK register offsets, no DMA or interrupt ownership. */
static const uint8_t offsets[]={0,4,8,16,20,24,28,44,76,240,244};
static uint32_t saved[11],clock_saved,gpio_saved,xip_saved,budget;
static void clock_set(uint32_t v) {
    v&=0x3fffffffu;
    flash_write32(CLOCK,v|0x40000000u);
    flash_write32(CLOCK,v|0x80000000u);
    flash_write32(CLOCK,v|0xc0000000u);
    flash_write32(CLOCK,v);
}
static int wait_bit(uint32_t mask,uint32_t expected) {
    while(budget) { --budget; if((flash_read32(Q+40)&mask)==expected)return 1; }
    return 0;
}
static int byte(uint8_t tx,uint8_t *rx) {
    if(!wait_bit(4,4))return 0; /* TFE */
    flash_write32(Q+96,tx);
    if(!wait_bit(8,8))return 0; /* RFNE */
    *rx=(uint8_t)flash_read32(Q+96);
    return 1;
}
static int begin(void) {
    unsigned i;
    clock_saved=flash_read32(CLOCK); clock_set(clock_saved&~0x04000000u);
    budget=100000u;
    if(!wait_bit(1,0)) {clock_set(clock_saved);return 0;}
    gpio_saved=flash_read32(GPIO); xip_saved=flash_read32(XIP);
    /* Do not take over an explicitly asserted software chip select. */
    if((gpio_saved&0x40020000u)==0x40020000u && !(gpio_saved&CS)) {
        clock_set(clock_saved);return 0;
    }
    for(i=0;i<11;++i)saved[i]=flash_read32(Q+offsets[i]);
    flash_write32(Q+8,0);
    /* Set CS high before switching it to GPIO control. */
    flash_write32(GPIO,gpio_saved|CS);
    flash_write32(GPIO,gpio_saved|0x42020200u);
    flash_write32(XIP,xip_saved&~0x10000u);
    flash_write32(Q,7); /* Motorola mode0,8bit,standard duplex */
    flash_write32(Q+4,0); flash_write32(Q+16,1);
    flash_write32(Q+20,64); /* conservative SCK divider */
    flash_write32(Q+24,0);flash_write32(Q+28,0);
    flash_write32(Q+44,0);flash_write32(Q+76,0);
    flash_write32(Q+240,0x10000u);flash_write32(Q+244,0x218u);
    flash_write32(Q+8,1);
    flash_write32(GPIO,(gpio_saved|0x42020200u)&~CS);
    return 1;
}
static void end(void) {
    unsigned i;
    flash_write32(GPIO,gpio_saved|0x42020200u);
    flash_write32(Q+8,0);
    for(i=0;i<11;++i)if(offsets[i]!=8)flash_write32(Q+offsets[i],saved[i]);
    flash_write32(XIP,xip_saved);
    flash_write32(GPIO,gpio_saved);
    flash_write32(Q+8,saved[2]);
    clock_set(clock_saved);
}
static unsigned query(unsigned op,unsigned offset,uint8_t *data,unsigned n) {
    uint8_t ignored;unsigned i,ok=1;
    if(!begin())return 2;
    if(op==0)ok=byte(0x9f,&ignored);
    else {
        ok=byte(op==1?0x5a:0x03,&ignored);
        if(ok)ok=byte(0,&ignored);
        if(ok)ok=byte((uint8_t)(offset>>8),&ignored);
        if(ok)ok=byte((uint8_t)offset,&ignored);
        if(ok && op==1)ok=byte(0,&ignored);
    }
    for(i=0;ok && i<n;++i)ok=byte(0xff,data+i);
    if(ok)ok=wait_bit(1,0);
    end();
    if(!ok)memset(data,0,n);
    return ok?0:1;
}
static void put16(uint8_t *p,unsigned v) {p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
int rio_flash_probe_request(uint8_t type,uint8_t request,uint16_t op,
                           uint16_t offset,uint16_t length,uint8_t out[64]) {
    unsigned n,status,i;uint32_t crc;
    if(type!=0xc1 || request!=0x54 || length!=64 || op>2 || offset>=4096 ||
       (op==0 && offset))return 0;
    n=op==0?8:(4096u-offset<44?4096u-offset:44);
    memset(out,0,64);memcpy(out,"RISP",4);out[4]=1;out[5]=(uint8_t)op;
    put16(out+8,offset);put16(out+10,n);out[12]=1; /* QSPI1 */
    status=query(op,offset,out+16,n);put16(out+6,status);
    crc=rio_usb_crc32(out,60);
    for(i=0;i<4;++i)out[60+i]=(uint8_t)(crc>>(8*i));
    return 64;
}

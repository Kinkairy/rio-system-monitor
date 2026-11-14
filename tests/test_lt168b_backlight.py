"""MMIO oracle from eM133 original60040340, not the firmware under test.

Recovered512B SHA b77b9ac5d3029978a06d071aaf9ad78a14c33893b8529dcae5c70e2d2585517a.
Stock input period is deliberately replaced by1024 for the bench; compare525
and the eight store operations below come from original instructions.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BacklightTests(unittest.TestCase):
    def test_stock_channel_and_unrelated_bits(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)
            harness=directory/'trace.c'
            harness.write_text(r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static uint32_t regs[28];
static unsigned index32(uint32_t a) {
    switch(a) {
    case 0x400e0004:case 0x400e0008:case 0x400e0030:
    case 0x400e0034:case 0x400e006c:return (a-0x400e0000)/4;
    default:abort();
    }
}
uint32_t backlight_read32(uint32_t a) {return regs[index32(a)];}
void backlight_write32(uint32_t a,uint32_t v) {
    regs[index32(a)]=v;printf("32 %x %x\n",a,v);
}
void backlight_write8(uint32_t a,uint8_t v) {
    if(a!=0x400e0001)abort();
    regs[0]=(regs[0]&~0xff00u)|((uint32_t)v<<8);
    printf("8 %x %x\n",a,v);
}
extern void rio_board_backlight_init(void);
int main(int argc,char **argv) {
    unsigned i;
    if(argc!=2)return 2;
    for(i=0;i<28;i++)regs[i]=(uint32_t)strtoul(argv[1],0,16);
    rio_board_backlight_init();
    printf("P %x %x\n",0x400e0000,regs[0]);return 0;
}
''')
            exe=directory/'trace'
            subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
                '-DRIO_BACKLIGHT_TEST',str(ROOT/'firmware/lt168b/board_backlight.c'),
                str(harness),'-o',str(exe)],check=True)
            for seed in (0,0xffffffff,0xa55a5aa5):
                with self.subTest(seed=seed):
                    lines=subprocess.check_output([str(exe),f'{seed:x}'],text=True).splitlines()
                    actual=[(k,int(a,16),int(v,16)) for k,a,v in (line.split() for line in lines)]
                    # Original instruction store addresses/order/masks. CH3EN
                    # is the last store; no writes to GPIO/flash/other PWM bases.
                    self.assertEqual(actual,[
                        ('32',0x400e0004,(seed&0xffff8fff)|0x2000),
                        ('8',0x400e0001,0),
                        ('32',0x400e0008,seed|0x08000000),
                        ('32',0x400e0030,1024),
                        ('32',0x400e0034,525),
                        ('32',0x400e006c,seed|0x80000),
                        ('32',0x400e006c,(seed|0x80000)&0xfffffff7),
                        ('32',0x400e0008,seed|0x09000000),
                        ('P',0x400e0000,seed&0xffff00ff),
                    ])

if __name__=='__main__':unittest.main()

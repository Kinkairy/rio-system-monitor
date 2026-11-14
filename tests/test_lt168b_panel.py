"""Validate actual GPIO waveform against recovered stock panel call trace."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def test_panel_gpio_waveform_matches_stock(tmp_path):
    harness = tmp_path / 'panel_trace.c'
    harness.write_text(r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static uint8_t regs[4]={0x50,0x50,0x50,0x50};
static uint16_t r34;
static int index8(uint32_t a) {
    switch(a) {case 0x400f0001:return 0;case 0x400f0007:return 1;
    case 0x40100001:return 2;case 0x40100007:return 3;default:abort();}
}
uint8_t panel_read8(uint32_t a) {return regs[index8(a)];}
void panel_write8(uint32_t a,uint8_t v) {
    regs[index8(a)]=v;printf("8 %x %x\n",a,v);
}
uint16_t panel_read16(uint32_t a) {if(a!=0x40120034)abort();return r34;}
void panel_write16(uint32_t a,uint16_t v) {
    if(a!=0x40120034 && a!=0x4012001e)abort();
    if(a==0x40120034)r34=v;printf("16 %x %x\n",a,v);
}
void rio_board_delay_ms(unsigned ms) {printf("D 0 %x\n",ms);}
extern void rio_board_panel_init(void);
int main(void) {rio_board_panel_init();return 0;}
''')
    exe=tmp_path/'panel_trace'
    subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',
                    '-Wno-misleading-indentation','-fsanitize=undefined',
                    '-fsanitize-undefined-trap-on-error','-DRIO_PANEL_TEST',
                    str(ROOT/'firmware/lt168b/board_panel.c'),str(harness),'-o',str(exe)],check=True)
    output=subprocess.check_output([str(exe)],text=True)
    writes=[(k,int(a,16),int(v,16)) for k,a,v in (line.split() for line in output.splitlines())]
    # Independent stock GPIO function6003C0E0, with seeded unrelated bits.
    assert writes[:20] == [
        ('16',0x40120034,v) for v in (0,0x4000,0x8000,0xc000,0xc0f7,0xc0ff)
    ] + [('8',0x400f0001,0x10),('8',0x400f0001,0x90),('8',0x400f0007,0xd0)] + [
        ('16',0x4012001e,v) for v in (0,1,2,3,0x403)
    ] + [('8',0x40100001,0x51),('8',0x40100007,0x51)] + [
        ('8',0x400f0001,v) for v in (0x91,0x93,0x97,0x9f)
    ]
    assert writes[20:25] == [('8',0x400f0007,v) for v in (0xd4,0xdc,0xdd,0xdf,0xdf)]
    observed=[]; old=0xdf; bits=None
    for k,a,v in writes[25:]:
        if k=='D':
            assert bits is None
            observed.append(('delay_ms',v));continue
        assert k=='8' and a==0x400f0007
        assert v&0xf0==0xd0  # Do not disturb button/input/backlight bits.
        if (old^v)&8: observed.append(('reset_high' if v&8 else 'reset_low',None))
        if old&4 and not v&4:
            assert bits is None;bits=[]
        if bits is not None and not old&2 and v&2: bits.append(v&1)
        if not old&4 and v&4:
            assert bits is not None and len(bits)==9
            byte=0
            for b in bits[1:]:byte=(byte<<1)|b
            observed.append(('data' if bits[0] else 'command',byte));bits=None
        old=v
    assert bits is None and old&0xe==0xe
    stock=json.loads((ROOT/'tests/fixtures/lt168b_em133_panel.json').read_text())
    # First gpio+reset_high occur in the25 writes checked separately above.
    expected=[(e['kind'],e.get('value')) for e in stock['events'][2:]]
    assert observed==expected
    assert sum(k=='command' for k,v in observed)==37


class PanelTests(unittest.TestCase):
    def test_stock_waveform(self):
        with tempfile.TemporaryDirectory() as directory:
            test_panel_gpio_waveform_matches_stock(Path(directory))

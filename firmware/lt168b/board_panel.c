/* eM133-V3 panel profile, recovered from this board's stock application.
 * Trace provenance: tests/fixtures/lt168b_em133_panel.json; stock6003C188.
 * GPIO: EPORT0.0 SDA, .1 CLK, .2 CS, .3 RESET. Never drives boot pin .6.
 * Register setup also preserves the stock EPORT0.7/EPORT1.0 outputs.
 * This is panel initialization only; no flash controller access. */
#include <stdint.h>
#ifdef RIO_PANEL_TEST
extern uint8_t panel_read8(uint32_t address);
extern void panel_write8(uint32_t address, uint8_t value);
extern uint16_t panel_read16(uint32_t address);
extern void panel_write16(uint32_t address, uint16_t value);
#else
static uint8_t panel_read8(uint32_t a) { return *(volatile uint8_t *)a; }
static void panel_write8(uint32_t a, uint8_t v) { *(volatile uint8_t *)a=v; }
static uint16_t panel_read16(uint32_t a) { return *(volatile uint16_t *)a; }
static void panel_write16(uint32_t a, uint16_t v) { *(volatile uint16_t *)a=v; }
#endif
extern void rio_board_delay_ms(unsigned ms);
#define E0_DIR 0x400f0001u
#define E0_OUT 0x400f0007u
#define E1_DIR 0x40100001u
#define E1_OUT 0x40100007u
static void pin(uint8_t mask, unsigned high) {
    uint8_t value=panel_read8(E0_OUT);
    panel_write8(E0_OUT,high?(value|mask):(value & (uint8_t)~mask));
}
static void gpio_start(void) {
    panel_write16(0x40120034u,0);
    panel_write16(0x40120034u,0x4000);
    panel_write16(0x40120034u,0x8000);
    panel_write16(0x40120034u,0xc000);
    panel_write16(0x40120034u,0xc0f7);
    panel_write16(0x40120034u,panel_read16(0x40120034u)|0xc0ff);
    panel_write8(E0_DIR,panel_read8(E0_DIR)&0xbf);
    panel_write8(E0_DIR,panel_read8(E0_DIR)|0x80);
    panel_write8(E0_OUT,panel_read8(E0_OUT)|0x80);
    panel_write16(0x4012001eu,0);
    panel_write16(0x4012001eu,1);
    panel_write16(0x4012001eu,2);
    panel_write16(0x4012001eu,3);
    panel_write16(0x4012001eu,0x403);
    panel_write8(E1_DIR,panel_read8(E1_DIR)|1);
    panel_write8(E1_OUT,panel_read8(E1_OUT)|1);
    panel_write8(E0_DIR,panel_read8(E0_DIR)|1);
    panel_write8(E0_DIR,panel_read8(E0_DIR)|2);
    panel_write8(E0_DIR,panel_read8(E0_DIR)|4);
    panel_write8(E0_DIR,panel_read8(E0_DIR)|8);
    pin(4,1); pin(8,1); pin(1,1); pin(2,1);
}
static void send9(unsigned data, uint8_t value) {
    unsigned i;
    pin(4,0); pin(1,data); pin(2,0); pin(2,1);
    for(i=0;i<8;++i) {
        pin(1,value&0x80); value=(uint8_t)(value<<1);
        pin(2,0); pin(2,1);
    }
    pin(4,1);
}
static const uint8_t sequence[][2] = {
    {3, 0},
    {2, 10},
    {4, 0},
    {2, 10},
    {3, 0},
    {2, 120},
    {2, 120},
    {0, 255},
    {1, 119},
    {1, 1},
    {1, 0},
    {1, 0},
    {1, 16},
    {0, 192},
    {1, 59},
    {1, 0},
    {0, 193},
    {1, 11},
    {1, 2},
    {0, 194},
    {1, 7},
    {1, 2},
    {0, 204},
    {1, 16},
    {0, 176},
    {1, 0},
    {1, 17},
    {1, 22},
    {1, 14},
    {1, 17},
    {1, 6},
    {1, 5},
    {1, 9},
    {1, 8},
    {1, 33},
    {1, 6},
    {1, 19},
    {1, 16},
    {1, 41},
    {1, 49},
    {1, 24},
    {0, 177},
    {1, 0},
    {1, 17},
    {1, 22},
    {1, 14},
    {1, 17},
    {1, 7},
    {1, 5},
    {1, 9},
    {1, 9},
    {1, 33},
    {1, 5},
    {1, 19},
    {1, 17},
    {1, 42},
    {1, 49},
    {1, 24},
    {0, 255},
    {1, 119},
    {1, 1},
    {1, 0},
    {1, 0},
    {1, 17},
    {0, 176},
    {1, 109},
    {0, 177},
    {1, 55},
    {0, 178},
    {1, 129},
    {0, 179},
    {1, 128},
    {0, 181},
    {1, 67},
    {0, 183},
    {1, 133},
    {0, 184},
    {1, 32},
    {0, 193},
    {1, 120},
    {0, 194},
    {1, 120},
    {0, 208},
    {1, 136},
    {0, 224},
    {1, 0},
    {1, 0},
    {1, 2},
    {0, 225},
    {1, 3},
    {1, 160},
    {1, 0},
    {1, 0},
    {1, 4},
    {1, 160},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 32},
    {1, 32},
    {0, 226},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {0, 227},
    {1, 0},
    {1, 0},
    {1, 17},
    {1, 0},
    {0, 228},
    {1, 34},
    {1, 0},
    {0, 229},
    {1, 5},
    {1, 236},
    {1, 160},
    {1, 160},
    {1, 7},
    {1, 238},
    {1, 160},
    {1, 160},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {0, 230},
    {1, 0},
    {1, 0},
    {1, 17},
    {1, 0},
    {0, 231},
    {1, 34},
    {1, 0},
    {0, 232},
    {1, 6},
    {1, 237},
    {1, 160},
    {1, 160},
    {1, 8},
    {1, 239},
    {1, 160},
    {1, 160},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {1, 0},
    {0, 235},
    {1, 0},
    {1, 0},
    {1, 64},
    {1, 64},
    {1, 0},
    {1, 0},
    {1, 0},
    {0, 237},
    {1, 255},
    {1, 255},
    {1, 255},
    {1, 186},
    {1, 10},
    {1, 191},
    {1, 69},
    {1, 255},
    {1, 255},
    {1, 84},
    {1, 251},
    {1, 160},
    {1, 171},
    {1, 255},
    {1, 255},
    {1, 255},
    {0, 239},
    {1, 16},
    {1, 13},
    {1, 4},
    {1, 8},
    {1, 63},
    {1, 31},
    {0, 255},
    {1, 119},
    {1, 1},
    {1, 0},
    {1, 0},
    {1, 19},
    {0, 239},
    {1, 8},
    {0, 255},
    {1, 119},
    {1, 1},
    {1, 0},
    {1, 0},
    {1, 0},
    {0, 17},
    {2, 120},
    {0, 41},
    {0, 54},
    {1, 8},
    {0, 58},
    {1, 119},
    {2, 20},
};
void rio_board_panel_init(void) {
    unsigned i;
    gpio_start();
    for(i=0;i<sizeof(sequence)/sizeof(sequence[0]);++i) {
        unsigned op=sequence[i][0], value=sequence[i][1];
        if(op<2) send9(op,(uint8_t)value);
        else if(op==2) rio_board_delay_ms(value);
        else pin(8,op==3);
    }
}

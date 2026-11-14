/* eM133-V3 stock60040340 PWM route, recovered from unchanged app tail.
 * Original period is runtime-selected. Bench uses1024 with stock compare525,
 * approximately half duty; this is not an inferred original brightness.
 * No shared GPIO changes, stock-code calls or flash access. */
#include <stdint.h>
#ifdef RIO_BACKLIGHT_TEST
extern uint32_t backlight_read32(uint32_t address);
extern void backlight_write32(uint32_t address,uint32_t value);
extern void backlight_write8(uint32_t address,uint8_t value);
#define RD(a) backlight_read32(a)
#define WR(a,v) backlight_write32(a,v)
#define WR8(a,v) backlight_write8(a,v)
#else
#define RD(a) (*(volatile uint32_t *)(a))
#define WR(a,v) (*(volatile uint32_t *)(a)=(v))
#define WR8(a,v) (*(volatile uint8_t *)(a)=(v))
#endif

void rio_board_backlight_init(void) {
    WR(0x400e0004u,(RD(0x400e0004u)&~0x7000u)|0x2000u);
    WR8(0x400e0001u,0);
    WR(0x400e0008u,RD(0x400e0008u)|0x08000000u);
    WR(0x400e0030u,1024u);
    WR(0x400e0034u,525u);
    WR(0x400e006cu,RD(0x400e006cu)|0x00080000u);
    WR(0x400e006cu,RD(0x400e006cu)&~0x00000008u);
    WR(0x400e0008u,RD(0x400e0008u)|0x01000000u);
}

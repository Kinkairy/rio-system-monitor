/* LT168 SDK User/main.c Cache_Init and datasheet v2.2 pp131/136/141.
 * Only immutable code flash Region1 is cacheable; USB/SRAM/display bypass it.
 * No flash programming, GPIO, timer, panel or backlight register access. */
#include "board_cache.h"
#ifdef RIO_CACHE_TEST
extern uint32_t cache_read32(uint32_t address);
extern void cache_write32(uint32_t address,uint32_t value);
#else
static uint32_t cache_read32(uint32_t a) {return *(volatile uint32_t *)a;}
static void cache_write32(uint32_t a,uint32_t v) {*(volatile uint32_t *)a=v;}
#endif
#define CCR 0x40190000u
#define ACRG 0x40190020u
static uint32_t boot_ccr,boot_acrg,initialized;
void rio_board_cache_init(void) {
    unsigned remaining=100000u;
    boot_ccr=cache_read32(CCR);boot_acrg=cache_read32(ACRG);initialized=0;
    cache_write32(ACRG,0);
    cache_write32(CCR,0x85000030u); /* disable; invalidate both ways; GO */
    while(cache_read32(CCR)&0x80000000u) {
        if (!--remaining) return; /* bypass remains in force on failure */
    }
    cache_write32(ACRG,0x8u); /* Region1 code, write-through, no data regions */
    cache_write32(CCR,cache_read32(CCR)|1u);
    initialized=1;
}
void rio_board_cache_status(uint32_t out[5]) {
    out[0]=boot_ccr;out[1]=boot_acrg;
    out[2]=cache_read32(CCR);out[3]=cache_read32(ACRG);out[4]=initialized;
}

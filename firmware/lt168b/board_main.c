/* eM133 bench candidate: stock panel GPIO/sequence and RGB mode recovered.
 * Still requires explicit flash approval and physical display qualification.
 * Official SDK register headers/clock/startup are external build inputs. */
#include "LT168.h"
#include "lt168_clock.h"
#include "rio_stream.h"
#include "board_cache.h"

extern void rio_board_panel_init(void);
extern void rio_board_backlight_init(void);
extern void rio_board_usb_init(uint16_t *pixels);
extern void rio_board_usb_poll(void);
static uint16_t framebuffer[RIO_PIXELS]
    __attribute__((section(".framebuffer"),aligned(4)));

/* Conservative minimum delay at200MHz: >=200000 single-cycle nops/ms,
 * plus loop overhead. Initialization only, not a frame timing source. */
void rio_board_delay_ms(unsigned ms) {
    while(ms--) { volatile unsigned i; for(i=0;i<200000u;++i) __asm__("nop"); }
}
static void display_start(void) {
    /* Active resource confirms timing; stock60012590 proves CLK_POL1/DIV6.
     * Stock code overrides the misleading theme-only polarity metadata.
     * Display RAM is always at 0x00840000; reserve all 512 KiB in linkmap. */
    OPTION->U16_CCR.CCRTEST=1; OPTION->U16_CCR.CCRTEST=2;
    OPTION->U16_CCR.CCRTEST=3; OPTION->U16_CCR.RGBEN=1;
    RGB_CTL->U32_RCSR.RGBE=0;
    RGB_CTL->U32_THDF.HDISP=480; RGB_CTL->U32_THDF.HFP=160;
    RGB_CTL->U32_TVDF.VDISP=480; RGB_CTL->U32_TVDF.VFP=12;
    RGB_CTL->U32_THPB.HBP=140; RGB_CTL->U32_THPB.HPW=20;
    RGB_CTL->U32_TVPB.VBP=20; RGB_CTL->U32_TVPB.VS=3;
    RGB_CTL->U32_RCSR.CLK_POL=1; RGB_CTL->U32_RCSR.HS_POL=1;
    RGB_CTL->U32_RCSR.VS_POL=1; RGB_CTL->U32_RCSR.DE_POL=1;
    RGB_CTL->U32_RCSR.DIV_NUM=6; /* Exact stock register value. */
    RGB_CTL->U32_RCSR.DRC=0; RGB_CTL->U32_RCSR.BEPO=0;
    RGB_CTL->U32_MSADDR.MADDR_START=0;
    RGB_CTL->U32_MEADDR.MADDR_END=RIO_PIXELS/2-1;
    RGB_CTL->U32_RCSR.RGBE=1;

}
int main(void) {
    unsigned x,y;
    EIC->IER=0; WDT->WCR=0;
    /* Stock6003B5A0: memory/clock option setup before200MHz PLL. */
    {
        volatile uint32_t *option=(volatile uint32_t *)0x4012001cu;
        *option=(*option & ~0x3000u)|0x1000u;
        *option=(*option & ~0x3000u)|0x2000u;
        *option|=0x3000u;
        *option|=3u; *option|=0x800u; *option|=0x100u; *option|=0x400u;
        *option&=~0x3000u;
    }
    Clock_Init(200);
    rio_board_cache_init();
    for(y=0;y<480;++y) for(x=0;x<480;++x)
        framebuffer[y*480+x]=(((x/32)^(y/32))&1)?0x07e0:0x001f;
    rio_board_panel_init();
    display_start();
    rio_board_backlight_init();
    rio_board_usb_init(framebuffer);
    for(;;) rio_board_usb_poll(); /* Polled USB: no borrowed ISR ABI. */
}

/* LT168B USB full-speed bulk receiver. EBT layout, PHY sequencing and token
 * bits follow the official SDK. Two software RX buffers alternate on the
 * existing EVEN descriptor: USB may fill one while the parser owns the other.
 * One prefetched packet can wait behind a frame ACK. No flash/write API. */
#include "LT168.h"
#include "lt168_clock.h"
#include "rio_stream.h"
#include "rio_profile.h"
#include "rio_usb.h"
#include "board_cache.h"
#include <string.h>

/* INT_STAT is write-one-to-clear. Never read/modify/write a bitfield here:
 * another token or reset flag must survive acknowledgement of this event.
 * The native controller oracle supplies only the MMIO write semantics. */
#ifndef RIO_USB_W1C
#define RIO_USB_W1C(mask) (USB->INT_STAT=(uint8_t)(mask))
#endif

typedef struct {
    volatile uint8_t stat, reserved;
    volatile uint16_t count;
    volatile uint32_t address;
} buffer_descriptor;
typedef char descriptor_must_be_8_bytes[sizeof(buffer_descriptor)==8?1:-1];
static buffer_descriptor table[32] __attribute__((aligned(512)));
static uint8_t control_out[64],control_in[64],bulk_out[2][64],bulk_in[64];
static uint8_t control_reply[64],ack[24];
static const uint8_t *control_source;
static uint16_t control_remaining;
static uint8_t control_toggle,bulk_toggle,out_toggle,configuration,pending_address;
static uint8_t address_pending,ack_pending,failed,control_zlp;
static uint8_t rx_buffer,rx_waiting,rx_wait_buffer;
static uint16_t rx_wait_length;
/* Explicit NOLOAD sections avoid embedding zero-filled arenas in app flash.
 * stream is memset on every USB/session reset; arena/scratch are written before use. */
static rio_stream stream __attribute__((section(".bss.rio_stream"),aligned(4)));
static uint8_t staging[208u*1024u] __attribute__((section(".frame_staging"),aligned(4)));
static uint16_t row[480u*16u] __attribute__((section(".frame_staging"),aligned(4)));

static uint32_t scan_start,scan_delta,scan_max,end_active,active_ends;
static int before_present(void *context) {
    unsigned budget=4000000u;
    PROFILE_START(wait_time);
    (void)context;
    /* Fresh falling PPVF edge, not an arbitrary point in a partially elapsed
     * blank. No RGBE/clock/backlight changes; bounded if the panel clock fails. */
    while (!RGB_CTL->U32_RCSR.PPVF) if (!--budget) return 0;
    while (RGB_CTL->U32_RCSR.PPVF) if (!--budget) return 0;
    PROFILE_END(5,wait_time);
    scan_start=RGB_CTL->NFTR;
    return 1;
}
static void after_present(void *context) {
    (void)context;
    scan_delta=RGB_CTL->NFTR-scan_start;
    if(scan_delta>scan_max)scan_max=scan_delta;
    end_active=RGB_CTL->U32_RCSR.PPVF;
    active_ends+=end_active;
}
static uint16_t *display;
extern void rio_board_delay_ms(unsigned ms);

static uint16_t read16(const uint8_t *p) { return (uint16_t)(p[0]|((uint16_t)p[1]<<8)); }
static void arm(unsigned entry,uint8_t *data,uint16_t count,uint8_t status) {
    table[entry].address=(uint32_t)data; table[entry].count=count;
    __asm__ volatile("" ::: "memory"); table[entry].stat=status;
}
static void receive_again(void) { arm(4,bulk_out[rx_buffer],64,(uint8_t)(0x88|(out_toggle?0x40:0))); }
static void control_next(void) {
    uint16_t n=control_remaining>64?64:control_remaining;
    if(n) { memcpy(control_in,control_source,n); control_source+=n; }
    control_remaining-=n;
    arm(2,control_in,n,(uint8_t)(0x88|(control_toggle?0x40:0)));
    control_toggle^=1;
}
static void reply(const uint8_t *p,uint16_t length,uint16_t requested) {
    if(length>requested) length=requested;
    control_source=p; control_remaining=length; control_toggle=1;
    control_zlp=(length<requested && !(length%64));
    control_next();
}
static void stall(void) { USB->U32_ENDPT0.EP_STALL=1; }
static void reset_stream(void) {
    rio_stream_init(&stream,display);
    rio_stream_staging(&stream,staging,sizeof(staging),row,before_present,0);
    rio_stream_on_presented(&stream,after_present);
    scan_start=scan_delta=scan_max=end_active=active_ends=0;
    failed=0; ack_pending=0; bulk_toggle=out_toggle=0;
    rx_buffer=rx_waiting=0; rx_wait_length=0;
    table[8].stat=0; table[9].stat=0; table[10].stat=0; table[11].stat=0;
    if(configuration) receive_again();
}
static void set_configuration(uint8_t value) {
    USB->ENDPT1=USB->ENDPT2=0;
    configuration=value;
    table[4].stat=table[5].stat=0;
    reset_stream();
    USB->ENDPT1=value?0x09:0; USB->ENDPT2=value?0x05:0;
}
static void reset_usb(void) {
    unsigned i;
    for(i=0;i<32;++i) { table[i].stat=0; table[i].count=0; table[i].address=0; }
    USB->ENDPT1=USB->ENDPT2=USB->ENDPT3=0;
    USB->ENDPT4=USB->ENDPT5=USB->ENDPT6=USB->ENDPT7=0;
    configuration=address_pending=control_zlp=0; control_remaining=0;
    reset_stream();
    arm(0,control_out,64,0xc8); arm(1,control_out,64,0xc8);
    table[2].address=table[3].address=(uint32_t)control_in;
    USB->ENDPT0=0x0d; USB->ADDR=0;
    USB->ERR_STAT=0xff; USB->ERR_ENB=0xff;
    RIO_USB_W1C(0xff); USB->INT_ENB=0xff;
}
static void setup(void) {
    uint8_t type=control_out[0],request=control_out[1];
    uint16_t value=read16(control_out+2),index=read16(control_out+4);
    uint16_t requested=read16(control_out+6),length=0;
    const uint8_t *p=0;
    control_remaining=control_zlp=address_pending=0;
    table[2].stat=0; USB->U32_ENDPT0.EP_STALL=0;
    if(type==0x80 && request==6) {
        p=rio_usb_descriptor((uint8_t)(value>>8),(uint8_t)value,&length);
        if(p) reply(p,length,requested); else stall();
    } else if(type==0 && request==5 && value<128 && !index && !requested) {
        pending_address=(uint8_t)value; address_pending=1; reply(0,0,0);
    } else if(type==0 && request==9 && value<=1 && !index && !requested) {
        set_configuration((uint8_t)value); reply(0,0,0);
    } else if(type==0x80 && request==8 && !value && !index && requested==1) {
        reply(&configuration,1,requested);
    } else if((type==0x80 || type==0x81 || type==0x82) && request==0 && !value && requested==2) {
        if((type==0x80 || type==0x81) && index) stall();
        else if(type==0x82 && index!=0 && index!=RIO_USB_OUT && index!=RIO_USB_IN) stall();
        else { control_reply[0]=control_reply[1]=0; reply(control_reply,2,requested); }
    } else if(type==0x81 && request==10 && !value && !index && requested==1 && configuration) {
        control_reply[0]=0; reply(control_reply,1,1);
    } else if(type==1 && request==11 && !value && !index && !requested && configuration) {
        set_configuration(1); reply(0,0,0);
    } else if((type==0xc0 || type==0xc1) && request==RIO_USB_MS_VENDOR && !value &&
              ((type==0xc0 && index==4) || (type==0xc1 && index==5))) {
        p=rio_usb_ms_descriptor(index,&length); reply(p,length,requested);
    } else if(type==0xc1 && request==RIO_USB_HELLO && !value && !index && configuration) {
        rio_usb_hello(control_reply); reply(control_reply,32,requested);
    } else if(type==0xc1 && request==0x55 && !value && !index && requested==64 && configuration) {
        uint32_t values[13];
        rio_board_cache_status(values);
        values[5]=SYS_CLOCK;values[6]=RGB_CTL->NFTR;
        values[7]=rio_stream_presentations(&stream);values[8]=rio_stream_fallbacks(&stream);
        values[9]=scan_delta;values[10]=scan_max;values[11]=end_active;values[12]=active_ends;
        if(rio_usb_profile_request(type,request,value,index,requested,control_reply,values))
            reply(control_reply,64,requested);
        else stall();
#ifdef RIO_STAGE_PROFILE
    } else if(type==0xc1 && request==0x56 && !value && !index && requested==64 && configuration) {
        uint32_t values[13];
        memcpy(values,rio_stage_ticks,sizeof(rio_stage_ticks));
        values[9]=SYS_CLOCK;values[10]=1024;values[11]=RIO_PROFILE_TICK();
        values[12]=stream.completed;
        rio_usb_profile_request(type,0x55,value,index,requested,control_reply,values);
        reply(control_reply,64,requested);
#endif
    } else if(type==0xc1 && request==0x54 && configuration) {
        if(rio_flash_probe_request(type,request,value,index,requested,control_reply))
            reply(control_reply,64,requested);
        else stall();
    } else if(type==0x41 && request==RIO_USB_RESET && !value && !index && !requested && configuration) {
        /* A new session requires a transport barrier. Temporarily disable both
         * pipes so no pending OUT bytes survive the reset control transfer. */
        set_configuration(1); reply(0,0,0);
    } else if(type==2 && request==1 && !value && !requested &&
              (index==RIO_USB_OUT || index==RIO_USB_IN) && configuration) {
        /* Clear halt also drops the stream baseline; caller must reset/keyframe. */
        set_configuration(1); reply(0,0,0);
    } else stall();
    arm(0,control_out,64,0xc8);
    USB->U32_CTL.TXSUSPEND=0;
}
static void receive_packet(unsigned buffer,unsigned length) {
    int result;
    if(length>64) result=-1;
    else {
        /* The current token has been popped, and its descriptor is CPU-owned.
         * Publish the OTHER buffer before the potentially expensive parser.
         * A completed prefetch stays CPU-owned until its own token is handled;
         * neither the ACK path nor a stale token may overwrite that buffer. */
        rx_buffer=(uint8_t)(buffer^1u);
        receive_again();
        PROFILE_START(feed_time);
        result=rio_stream_feed(&stream,bulk_out[buffer],length);
        PROFILE_END(6,feed_time);
    }
    if(result) {
        failed=(result<0); ack_pending=1;
        rio_usb_ack(ack,stream.session,stream.frame,stream.completed,failed?1:0);
        memcpy(bulk_in,ack,sizeof(ack));
        arm(10,bulk_in,sizeof(ack),(uint8_t)(0x88|(bulk_toggle?0x40:0)));
        bulk_toggle^=1;
    }
}
static void token(unsigned endpoint,unsigned input) {
    if(!endpoint) {
        if(input) {
            if(address_pending) { USB->ADDR=pending_address; address_pending=0; }
            else if(control_remaining) control_next();
            else if(control_zlp) { control_zlp=0; control_next(); }
        } else if(((table[0].stat>>2)&15)==13) setup();
        else arm(0,control_out,64,0xc8);
    } else if(endpoint==1 && !input && configuration) {
        unsigned buffer=rx_buffer;
        uint16_t length;
        /* A reset may leave a stale status entry. An armed descriptor is not
         * a completed packet and remains exclusively owned by the SIE. */
        if(table[4].stat&0x80u) return;
        length=table[4].count&0x03ffu;
        table[4].stat=0;
        if(failed) return;
        out_toggle^=1;
        if(ack_pending) {
            rx_waiting=1; rx_wait_buffer=(uint8_t)buffer; rx_wait_length=length;
            return;
        }
        receive_packet(buffer,length);
    } else if(endpoint==2 && input && ack_pending && !(table[10].stat&0x80u)) {
        ack_pending=0;
        if(!failed && rx_waiting) {
            unsigned buffer=rx_wait_buffer,length=rx_wait_length;
            rx_waiting=0;
            receive_packet(buffer,length);
        }
    }
}
void rio_board_usb_init(uint16_t *pixels) {
    uint32_t value;
    display=pixels;
#ifdef RIO_STAGE_PROFILE
    PIT0->PCSR=0;
    PIT0->PCSR=(10u<<8)|0x10u; /* /1024, overwrite, IRQ/DMA disabled */
    PIT0->PMR=0xffffu;
    PIT0->PCSR=(10u<<8)|1u; /* free running */
#endif
    value=CLOCK->MSCR&~CLOCK_MSCR_MSCRTEST_MASK;
    CLOCK->MSCR=value|(1u<<30); CLOCK->MSCR=value|(2u<<30);
    CLOCK->MSCR=value|(3u<<30); CLOCK->MSCR&=~CLOCK_MSCR_USB_MASK;
    USB->U32_USBPHY_CTRL1.DP_HIGH=0; USB->U32_USB_PHY_OBSERVE.DP_PU=0;
    USB->U32_USB_RESMEN.USB_SFT_RESET=1;
    USB->U32_USBPHY_CTRL3.SEL_48_60M=0; USB->U32_USBPHY_CTRL2.SUSP=0;
    USB->U32_USBPHY_CTRL3.PHY_PD=0; USB->U32_USBPHY_CTRL3.PHY_RESETb=1;
    rio_board_delay_ms(10); USB->U32_USBPHY_CTRL3.PHY_OEN=1;
    USB->U32_USB_RESMEN.USBPHYCLKEN=1;
    USB->EBT_PAGE_01=(uint8_t)((uint32_t)table>>8);
    USB->EBT_PAGE_02=(uint8_t)((uint32_t)table>>16);
    USB->EBT_PAGE_03=(uint8_t)((uint32_t)table>>24);
    reset_usb(); USB->U32_CTL.USB_EN=1; USB->U32_CTL.ODD_RST=0;
    USB->U32_USBPHY_CTRL1.DP_HIGH=1;
}
void rio_board_usb_poll(void) {
    if(USB->U32_INT_STAT.USB_RST) { reset_usb(); return; }
    if(USB->U32_INT_STAT.SOF_TOK) RIO_USB_W1C(0x04);
    if(USB->U32_INT_STAT.STALL) {
        USB->U32_ENDPT0.EP_STALL=0; RIO_USB_W1C(0x80);
    }
    if(USB->U32_INT_STAT.TOKDNE) {
        unsigned endpoint=USB->U32_STAT.ENDP,input=USB->U32_STAT.TX;
        USB->U32_CTL.ODD_RST=1;
        RIO_USB_W1C(0x08);
        token(endpoint,input);
    }
    if(USB->U32_INT_STAT.SLEEP) RIO_USB_W1C(0x10);
    if(USB->U32_INT_STAT.ERROR) { USB->ERR_STAT=0xff; RIO_USB_W1C(0x02); }
}

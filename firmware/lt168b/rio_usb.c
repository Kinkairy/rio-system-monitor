#include "rio_usb.h"
#include <string.h>

const uint8_t rio_usb_device[18] = {
    18,1,0,2,0,0,0,64, 0xff,0xff,0x8b,0x16,0,1,1,2,0,1
};
const uint8_t rio_usb_config[32] = {
    9,2,32,0,1,1,0,0x80,250,
    9,4,0,0,2,0xff,0,0,0,
    7,5,RIO_USB_OUT,2,64,0,0,
    7,5,RIO_USB_IN,2,64,0,0
};
static const uint8_t lang[] = {4,3,9,4};
static const uint8_t maker[] = {8,3,'R',0,'I',0,'O',0};
static const uint8_t product[] = {
    34,3,'R',0,'I',0,'O',0,' ',0,'L',0,'T',0,'1',0,'6',0,'8',0,'B',0,
    ' ',0,'B',0,'e',0,'n',0,'c',0,'h',0
};
static const uint8_t os_string[] = {
    18,3,'M',0,'S',0,'F',0,'T',0,'1',0,'0',0,'0',0,RIO_USB_MS_VENDOR,0
};
static const uint8_t compatible[] = {
    40,0,0,0,0,1,4,0,1,0,0,0,0,0,0,0,
    0,1,'W','I','N','U','S','B',0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
};
/* Microsoft OS 1.0 extended properties. One device-interface GUID. */
static const uint8_t properties[] = {
    142,0,0,0,0,1,5,0,1,0,
    132,0,0,0,1,0,0,0,40,0,
    'D',0,'e',0,'v',0,'i',0,'c',0,'e',0,'I',0,'n',0,'t',0,'e',0,
    'r',0,'f',0,'a',0,'c',0,'e',0,'G',0,'U',0,'I',0,'D',0,0,0,
    78,0,0,0,
    '{',0,'8',0,'4',0,'B',0,'2',0,'8',0,'6',0,'6',0,'3',0,'-',0,
    '9',0,'3',0,'8',0,'5',0,'-',0,'4',0,'0',0,'B',0,'2',0,'-',0,
    'B',0,'7',0,'0',0,'8',0,'-',0,'8',0,'7',0,'F',0,'D',0,'5',0,
    '8',0,'F',0,'C',0,'9',0,'0',0,'A',0,'1',0,'}',0,0,0
};
static void le16(uint8_t *p, uint16_t n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }
static void le32(uint8_t *p, uint32_t n) {
    unsigned i; for(i=0;i<4;++i) p[i]=(uint8_t)(n>>(8*i));
}
uint32_t rio_usb_crc32(const uint8_t *p, size_t n) {
    uint32_t c=0xffffffffu; unsigned bit;
    while(n--) { c^=*p++; for(bit=0;bit<8;++bit) c=(c>>1)^(0xedb88320u&(0u-(c&1u))); }
    return c^0xffffffffu;
}
const uint8_t *rio_usb_descriptor(uint8_t type,uint8_t index,uint16_t *n) {
    const uint8_t *p=0; *n=0;
    if(type==1 && index==0) { p=rio_usb_device; *n=sizeof(rio_usb_device); }
    else if(type==2 && index==0) { p=rio_usb_config; *n=sizeof(rio_usb_config); }
    else if(type==3) {
        if(index==0) p=lang;
        else if(index==1) p=maker;
        else if(index==2) p=product;
        else if(index==0xee) p=os_string;
        if(p) *n=p[0];
    }
    return p;
}
const uint8_t *rio_usb_ms_descriptor(uint16_t index,uint16_t *n) {
    *n=0;
    if(index==4) { *n=sizeof(compatible); return compatible; }
    if(index==5) { *n=sizeof(properties); return properties; }
    return 0;
}
void rio_usb_hello(uint8_t p[32]) {
    memcpy(p,"RIO1",4); le16(p+4,1); le16(p+6,32);
    le16(p+8,480); le16(p+10,480); le16(p+12,32); le16(p+14,16);
    le32(p+16,3); /* RGB565 BE + bounded LZ4/XOR tiles; one frame in flight */
    le32(p+20,1048); le32(p+24,460800); le32(p+28,rio_usb_crc32(p,28));
}
void rio_usb_ack(uint8_t p[24],uint32_t session,uint32_t frame,
                 uint32_t completed,uint16_t status) {
    memcpy(p,"RIOA",4); le16(p+4,1); le16(p+6,status);
    le32(p+8,session); le32(p+12,frame); le32(p+16,completed);
    le32(p+20,rio_usb_crc32(p,20));
}

int rio_usb_profile_request(uint8_t type,uint8_t request,uint16_t value,
                            uint16_t index,uint16_t length,uint8_t p[64],
                            const uint32_t values[13]) {
    unsigned i;
    if(type!=0xc1 || request!=0x55 || value || index || length!=64 || !p || !values) return 0;
    memcpy(p,"RIOP",4);le16(p+4,1);le16(p+6,64);
    for(i=0;i<13;++i) le32(p+8+i*4,values[i]);
    le32(p+60,rio_usb_crc32(p,60));return 1;
}

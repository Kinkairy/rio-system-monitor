#include "rio_stream.h"
#include "rio_profile.h"
#ifdef RIO_STAGE_PROFILE
uint32_t rio_stage_ticks[9];
#endif
#include <string.h>
#include "vendor/lz4/lz4.h"

static uint16_t le16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
/* Validate the exact1024-byte, no-dictionary acceptance of the pinned
 * LZ4_decompress_safe without producing bytes. Mirror its short-copy shortcut
 * as well as the normal tail restrictions: a format-only parser is stricter
 * than this decoder. Offset0 is retained for decoder compatibility; the actual
 * unchanged decoder still defines every output byte at presentation.
 * Input is bounded to8192 bytes by the packet layer; integer lengths cannot
 * overflow here. Never use this path when the current tile cannot be staged. */
static int valid_lz4_tile(const uint8_t *p,unsigned n,unsigned limit) {
    unsigned in=0,out=0;
    while(in<n) {
        unsigned token=p[in++],length=token>>4,offset,extra;
        if(length!=15 && in+16<n && out<=limit-32) {
            in+=length;out+=length;
            offset=le16(p+in);in+=2;
            length=token&15u;
            if(length!=15 && offset>=8 && offset<=out) {
                out+=length+4;continue;
            }
        } else {
            if(length==15) {
                if(in+15>=n)return 0;
                do {
                    extra=p[in++];length+=extra;
                    if(in+15>n)return 0;
                } while(extra==255);
            }
            if(length>n-in || length>limit-out)return 0;
            in+=length;out+=length;
            if(out>limit-12 || in+8>n)return in==n && out==limit;
            offset=le16(p+in);in+=2;
            length=token&15u;
        }
        if(length==15) {
            do {
                if(in>=n)return 0;
                extra=p[in++];length+=extra;
                if(in+4>n)return 0;
            } while(extra==255);
        }
        if(offset>out || length+4>limit-5-out)return 0;
        out+=length+4;
    }
    return 0;
}

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static uint32_t crc_step(uint32_t crc, const uint8_t *p, size_t n) {
    static const uint32_t table[16] = { 0x00000000u, 0x1db71064u, 0x3b6e20c8u, 0x26d930acu, 0x76dc4190u, 0x6b6b51f4u, 0x4db26158u, 0x5005713cu, 0xedb88320u, 0xf00f9344u, 0xd6d6a3e8u, 0xcb61b38cu, 0x9b64c2b0u, 0x86d3d2d4u, 0xa00ae278u, 0xbdbdf21cu };
    size_t i;
    for (i=0; i<n; ++i) {
        crc ^= p[i];
        crc=(crc>>4)^table[crc&15u];
        crc=(crc>>4)^table[crc&15u];
    }
    return crc;
}
static int reject(rio_stream *s) {
    s->active=0; s->valid=0; s->used=0; s->need=24;
    return -1;
}
void rio_stream_init(rio_stream *s, uint16_t *pixels) {
    memset(s,0,sizeof(*s)); s->pixels=pixels; s->need=24;
#ifdef RIO_STAGE_PROFILE
    memset(rio_stage_ticks,0,sizeof(rio_stage_ticks));
#endif
}
void rio_stream_on_presented(rio_stream *s, void (*callback)(void *)) {
    s->after_present=callback;
}
size_t rio_stream_size(void) { return sizeof(rio_stream); }
uint32_t rio_stream_completed(const rio_stream *s) { return s->completed; }
uint32_t rio_stream_presentations(const rio_stream *s) { return s->presentations; }
uint32_t rio_stream_fallbacks(const rio_stream *s) { return s->fallbacks; }

void rio_stream_staging(rio_stream *s, uint8_t *arena, size_t capacity,
                        uint16_t *row, int (*before_present)(void *), void *context) {
    s->staging=arena; s->capacity=capacity; s->row=row;
    s->before_present=before_present; s->present_context=context;
}
static uint32_t pixel_pair(const uint8_t *q) {
    uint32_t v;
    memcpy(&v,q,4);
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
    v=((v&0x00ff00ffu)<<8)|((v>>8)&0x00ff00ffu);
#endif
    return v;
}
static void resolve_tile(uint16_t *dst,unsigned stride,const uint16_t *base,
                         const uint8_t *q,unsigned predict,unsigned width) {
    unsigned j,k;
    /* CCore expands even four-byte memcpy to byte/stack traffic unless the
     * alignment is known. may_alias preserves C alias rules for pixel pairs. */
    typedef uint32_t pixel_word __attribute__((__may_alias__));
    if(!(((uintptr_t)dst|(uintptr_t)base|(uintptr_t)q)&3u)) {
        pixel_word *out=(pixel_word *)(void *)dst;
        const pixel_word *in=(const pixel_word *)(const void *)q;
        const pixel_word *old=(const pixel_word *)(const void *)base;
        for(j=0;j<16;++j) {
            for(k=0;k<width/2;++k) {
                uint32_t v=in[k];
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
                v=((v&0x00ff00ffu)<<8)|((v>>8)&0x00ff00ffu);
#endif
                out[k]=predict ? v^old[k] : v;
            }
            in+=width/2;out+=stride/2;old+=240;
        }
        return;
    }
    for(j=0;j<16;++j) for(k=0;k<width;k+=2) {
        uint32_t v=pixel_pair(q),old;
        q+=4;
        if(predict){memcpy(&old,base+j*480u+k,4);v^=old;}
        memcpy(dst+j*stride+k,&v,4);
    }
}
/* Populate only changed scratch regions, then publish them in scan order.
 * No read/copy of the old complete 16-row band, and no unchanged pixel writes. */
static int present(rio_stream *s) {
    unsigned band,i,j;
    if (!s->staged) return 0;
    if (s->before_present && !s->before_present(s->present_context)) return -1;
    for (band=0;band<30;++band) {
        unsigned first=band*15,mask=0;
        PROFILE_START(prepare_time);
        for(i=0;i<15;++i) if(s->seen[(first+i)/8] & (1u<<((first+i)%8)))mask|=1u<<i;
        if (!mask) continue;
        for(i=0;i<15;++i) if(mask&(1u<<i)) {
            unsigned tile=first+i,x=i*32,predict=0,columns=1;
            const uint8_t *p=s->staging+s->offsets[tile],*q=p+2;
            unsigned tag=le16(p),length=tag&0x3fffu;
            if((tag&0xc000u)==0xc000u) {
                for(j=0;j<16;++j)memcpy(s->row+j*480u+x,p+4+j*64u,64);
                continue;
            }
            if(tag&0x4000u){columns=*q++;--length;}
            if (!(tag&0x8000u)) {
                predict=q[0];
                PROFILE_START(decode_time);
                int result=LZ4_decompress_safe((const char *)q+1,(char *)s->decoded,
                                       (int)length-1,(int)columns*1024);
                PROFILE_END(2,decode_time);PROFILE_COUNT(8);
                if(result!=(int)columns*1024)return -1;
                q=s->decoded;
            }
            resolve_tile(s->row+x,480,s->pixels+band*7680u+x,q,predict,columns*32u);
            i+=columns-1;
        }
        PROFILE_END(3,prepare_time);
        PROFILE_START(copy_time);
        if(mask==0x7fffu) {
            memcpy(s->pixels+band*7680u,s->row,15360);
        } else for(j=0;j<16;++j) {
            i=0;
            while(i<15) {
                unsigned first_x;
                if(!(mask&(1u<<i))){++i;continue;}
                first_x=i++;
                while(i<15 && (mask&(1u<<i)))++i;
                memcpy(s->pixels+band*7680u+j*480u+first_x*32u,
                       s->row+j*480u+first_x*32u,(i-first_x)*64u);
            }
        }
        PROFILE_END(4,copy_time);
    }
    ++s->presentations;s->staged=0;
    if(s->after_present)s->after_present(s->present_context);
    return 0;
}

static int apply(rio_stream *s) {
    const uint8_t *p=s->packet;
    const uint16_t length=le16(p+6);
    const uint32_t session=le32(p+8), frame=le32(p+12), index=le32(p+16);
    const unsigned kind=p[5];
    PROFILE_START(crc_time);
    uint32_t crc=crc_step(0xffffffffu,p,20);
    crc=crc_step(crc,p+24,length)^0xffffffffu;
    PROFILE_END(0,crc_time);
    if (crc!=le32(p+20) || !session || !frame) return reject(s);
    if (kind==1 || kind==2) {
        if (s->active || length || index>RIO_TILE_COUNT) return reject(s);
        if (kind==1 && index!=RIO_TILE_COUNT) return reject(s);
        if (kind==2 && (!s->valid || session!=s->session ||
                       s->last_frame==0xffffffffu || frame!=s->last_frame+1u)) return reject(s);
        s->session=session; s->frame=frame; s->expected=(uint16_t)index;
        s->received=0; s->active=1; s->valid=0; s->delta=(uint8_t)(kind==2);
        s->staged=0; s->staging_active=(uint8_t)(s->staging && s->row);
        /* Only prepare frames whose entire declared tile set fits. This keeps
         * the prior-frame XOR baseline stable until validated END. A native
         * entry is a 4-byte tag/pad plus 1024 pixels bytes, always aligned. */
        s->stage_native=(uint8_t)(s->staging_active &&
            !((uintptr_t)s->staging&3u) && index<=s->capacity/1028u);
        memset(s->seen,0,sizeof(s->seen));
        return 0;
    }
    if (!s->active || session!=s->session || frame!=s->frame) return reject(s);
    if (kind==3 || kind==5 || kind==6) {
        unsigned x,y,j,k,predict=0,columns=1,bytes=length; const uint8_t *q=p+24;
        if(kind==6) {
            if(length<3 || !s->staging_active || s->stage_native ||
               (size_t)length+2>s->capacity-s->staged)return reject(s);
            columns=*q++;--bytes;
            if(columns<2 || columns>8 || index%15u+columns>15u)return reject(s);
        }
        if (index>=RIO_TILE_COUNT || columns>(unsigned)(s->expected-s->received))return reject(s);
        for(j=0;j<columns;++j) {
            unsigned at=index+j;
            if(s->seen[at/8] & (1u<<(at%8)))return reject(s);
        }
        if (kind==3) {
            if (length!=1024) return reject(s);
        } else {
            if (bytes<2 || q[0]>1 || (q[0] && !s->delta)) return reject(s);
            predict=q[0];
            if(s->staging_active && !s->stage_native &&
               (size_t)length+2<=s->capacity-s->staged) {
                if(!valid_lz4_tile(q+1,bytes-1,columns*1024u))return reject(s);
            } else {
                PROFILE_START(decode_time);
                int result=LZ4_decompress_safe((const char *)q+1,(char *)s->decoded,
                                             (int)length-1,(int)columns*1024);
                PROFILE_END(1,decode_time);PROFILE_COUNT(7);
                if(result!=1024)return reject(s);
                q=s->decoded;
            }
        }
        if (s->staging_active && !s->stage_native && (size_t)length+2>s->capacity-s->staged) {
            if (present(s)<0) return reject(s);
            s->staging_active=0; ++s->fallbacks;
            /* present() reused decoded; restore the current compressed tile. */
            if(kind==5) {
                PROFILE_START(decode_time);
                int result=LZ4_decompress_safe((const char *)p+25,
                         (char *)s->decoded,(int)bytes-1,1024);
                PROFILE_END(1,decode_time);PROFILE_COUNT(7);
                if(result!=1024)return reject(s);
            }
        }
        if (s->staging_active && s->stage_native) {
            uint8_t *at=s->staging+s->staged;
            s->offsets[index]=(uint32_t)s->staged;
            /* 0x4000 marks already-resolved native pixels; no second decode,
             * byte conversion or XOR is needed during presentation. */
            at[0]=0;at[1]=0xc4;at[2]=at[3]=0;
            resolve_tile((uint16_t *)(void *)(at+4),32,
                         s->pixels+(index/15u)*7680u+(index%15u)*32u,q,predict,32);
            s->staged+=1028u;
        } else if (s->staging_active) {
            unsigned tag=length|(kind==3 ? 0x8000u : kind==6 ? 0x4000u : 0);
            uint8_t *at=s->staging+s->staged;
            s->offsets[index]=(uint32_t)s->staged;
            at[0]=(uint8_t)tag;at[1]=(uint8_t)(tag>>8);
            memcpy(at+2,p+24,length);s->staged+=(size_t)length+2;
        } else {
            x=(index%15u)*32u; y=(index/15u)*16u;
            for (j=0;j<16;++j) for (k=0;k<32;++k) {
                uint16_t value=(uint16_t)(((uint16_t)q[0]<<8)|q[1]);
                unsigned at=(y+j)*480u+x+k;
                s->pixels[at]=predict ? (uint16_t)(s->pixels[at]^value) : value; q+=2;
            }
        }
        for(j=0;j<columns;++j){unsigned at=index+j;s->seen[at/8]|=(uint8_t)(1u<<(at%8));}
        s->received+=(uint16_t)columns;
        return 0;
    }
    if (kind==4) {
        if (length || index!=s->expected || s->received!=s->expected) return reject(s);
        if (s->staging_active && present(s)<0) return reject(s);
        s->active=0; s->valid=1; s->last_frame=frame; ++s->completed;
        return 1;
    }
    return reject(s);
}

int rio_stream_feed(rio_stream *s, const uint8_t *data, size_t length) {
    int completed=0;
    if (!s || !s->pixels || (!data && length)) return -1;
    while (length) {
        size_t take=(size_t)(s->need-s->used);
        int result;
        if (take>length) take=length;
        memcpy(s->packet+s->used,data,take); s->used+=(uint16_t)take;
        data+=take; length-=take;
        if (s->used!=s->need) continue;
        if (s->need==24) {
            uint16_t payload=le16(s->packet+6);
            if (memcmp(s->packet,"RIO1",4) || s->packet[4]!=1 || payload>(s->packet[5]==6 ? 8194 : 1024)) return reject(s);
            s->need=(uint16_t)(24+payload);
            if (payload) continue;
        }
        result=apply(s);
        if (result<0) return -1;
        if (result==1) completed=1;
        s->used=0; s->need=24;
    }
    return completed;
}

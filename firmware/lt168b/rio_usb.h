#ifndef RIO_LT168B_USB_H
#define RIO_LT168B_USB_H
#include <stddef.h>
#include <stdint.h>

/* Private bench identity only, not an allocated production VID/PID. Stock
 * EMonitor (EEEF:1616) must never be bound to this protocol. */
#define RIO_USB_VID 0xffffu
#define RIO_USB_PID 0x168bu
#define RIO_USB_HELLO 0x52u
#define RIO_USB_RESET 0x53u
#define RIO_USB_MS_VENDOR 0x20u
#define RIO_USB_OUT 0x01u
#define RIO_USB_IN 0x82u

extern const uint8_t rio_usb_device[18];
extern const uint8_t rio_usb_config[32];
/* Returns a stable descriptor, or NULL for an unsupported request. */
const uint8_t *rio_usb_descriptor(uint8_t type, uint8_t index, uint16_t *length);
const uint8_t *rio_usb_ms_descriptor(uint16_t index, uint16_t *length);
void rio_usb_hello(uint8_t out[32]);
void rio_usb_ack(uint8_t out[24], uint32_t session, uint32_t frame,
                 uint32_t completed, uint16_t status);
uint32_t rio_usb_crc32(const uint8_t *data, size_t length);
/* Fixed read-only storage identification. Invalid requests perform no MMIO. */
int rio_flash_probe_request(uint8_t type,uint8_t request,uint16_t op,
                           uint16_t offset,uint16_t length,uint8_t out[64]);
/* Fixed read-only presentation/cache diagnostic; values are board snapshots. */
int rio_usb_profile_request(uint8_t type,uint8_t request,uint16_t value,
                            uint16_t index,uint16_t length,uint8_t out[64],
                            const uint32_t values[13]);
#endif

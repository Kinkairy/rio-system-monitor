#ifndef RIO_LT168B_STREAM_H
#define RIO_LT168B_STREAM_H
#include <stddef.h>
#include <stdint.h>

/* Portable receiver core only. USB, clocks, LCD, boot entry are NOT supplied. */
#define RIO_PIXELS (480u * 480u)
#define RIO_TILE_COUNT 450u
#define RIO_PACKET_MAX 8218u /* header + count/predictor + up to8tiles */
typedef struct {
    uint16_t *pixels; /* caller-owned single native-endian RGB565 framebuffer */
    uint32_t session, frame, last_frame, completed;
    uint16_t expected, received, used, need;
    uint8_t active, valid, delta, seen[57];
    uint8_t decoded[8192]; /* bounded scratch, never an unvalidated framebuffer */
    uint8_t packet[RIO_PACKET_MAX];
    /* Board-owned arena: fitting frames store resolved native tiles, larger
     * frames store validated wire bytes; entries stay off scanout until present. */
    uint8_t *staging;
    uint16_t *row;
    size_t capacity, staged;
    uint32_t offsets[RIO_TILE_COUNT], presentations, fallbacks;
    int (*before_present)(void *);
    void *present_context;
    void (*after_present)(void *);
    uint8_t staging_active, stage_native;
} rio_stream;

/* Reset on USB disconnect; next accepted frame must be a full keyframe. */
void rio_stream_init(rio_stream *s, uint16_t *pixels);
/* -1 rejected (no ACK); 0 pending; 1 complete frame (ACK session/frame).
 * On rejection prior tiles may be visible. Send a new keyframe, not a delta.
 */
int rio_stream_feed(rio_stream *s, const uint8_t *data, size_t length);
/* Arena and 480*16 native RGB565 scratch remain owned by the caller.
 * Oversize frames retain the original progressive contract; ordinary RIO
 * monitor/music frames must fit (covered by the real-renderer corpus).
 * Callback failure rejects the frame before presentation, without an ACK.
 */
void rio_stream_staging(rio_stream *s, uint8_t *arena, size_t capacity,
                        uint16_t *row, int (*before_present)(void *), void *context);
void rio_stream_on_presented(rio_stream *s, void (*callback)(void *));
size_t rio_stream_size(void);
uint32_t rio_stream_completed(const rio_stream *s);
uint32_t rio_stream_presentations(const rio_stream *s);
uint32_t rio_stream_fallbacks(const rio_stream *s);
#endif

#ifndef RIO_BOARD_CACHE_H
#define RIO_BOARD_CACHE_H
#include <stdint.h>
void rio_board_cache_init(void);
/* boot CCR/ACRG, current CCR/ACRG, initialization success; read only. */
void rio_board_cache_status(uint32_t out[5]);
#endif

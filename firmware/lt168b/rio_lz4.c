/* Upstream v1.10.0 decoder; freestanding, unaligned-safe on CCore. */
#include <string.h>
#define LZ4_FREESTANDING 1
#define LZ4_memcpy memcpy
#define LZ4_memmove memmove
#define LZ4_memset memset
#define LZ4_FORCE_MEMORY_ACCESS 0
#define LZ4_FAST_DEC_LOOP 0
#include "vendor/lz4/lz4.c"

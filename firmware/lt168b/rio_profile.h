#ifndef RIO_STAGE_PROFILE_H
#define RIO_STAGE_PROFILE_H
#include <stdint.h>
/* Diagnostic-only PIT0: /1024, down counter, no interrupt or DMA. Individual
 * successful spans must stay below65536 ticks; this is not a frame wall clock. */
#ifdef RIO_STAGE_PROFILE
#ifndef RIO_PROFILE_TICK
#define RIO_PROFILE_TICK() (*(volatile uint16_t *)(uintptr_t)0x40040006u)
#endif
extern uint32_t rio_stage_ticks[9];
#define PROFILE_START(name) uint16_t name=RIO_PROFILE_TICK()
#define PROFILE_END(slot,name) (rio_stage_ticks[slot]+=(uint16_t)(name-RIO_PROFILE_TICK()))
#define PROFILE_COUNT(slot) (++rio_stage_ticks[slot])
#else
#define PROFILE_START(name) ((void)0)
#define PROFILE_END(slot,name) ((void)0)
#define PROFILE_COUNT(slot) ((void)0)
#endif
#endif

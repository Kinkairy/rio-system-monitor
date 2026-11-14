"""Actual decoder with independent LZ4-call and framebuffer-copy observation."""
import ctypes
from pathlib import Path
import random
import struct
import subprocess
import tempfile

import test_lt168b_presentation as presentation
from rio_monitor.lt168b_stream import FRAME_BYTES, packet

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "rio_stream.h"
#include "vendor/lz4/lz4.h"
static uintptr_t front;
static unsigned decodes,copies,offsets[10000],lengths[10000],front_reads;
void oracle_watch(void *p) {front=(uintptr_t)p;decodes=copies=front_reads=0;}
void oracle_clear(void) {decodes=copies=front_reads=0;}
unsigned oracle_decodes(void) {return decodes;}
unsigned oracle_copies(void) {return copies;}
unsigned oracle_offset(unsigned i) {assert(i<copies);return offsets[i];}
unsigned oracle_length(unsigned i) {assert(i<copies);return lengths[i];}
unsigned oracle_front_reads(void) {return front_reads;}
static int observed_decode(const char *src,char *dst,int n,int cap) {
    ++decodes;return LZ4_decompress_safe(src,dst,n,cap);
}
static void *observed_copy(void *dst,const void *src,size_t n) {
    uintptr_t d=(uintptr_t)dst,s=(uintptr_t)src;
    if(d>=front && d<front+460800u) {
        assert(n<=front+460800u-d && copies<10000u);
        offsets[copies]=(unsigned)(d-front);lengths[copies++]=(unsigned)n;
    }
    if(s>=front && s<front+460800u)front_reads+=(unsigned)n;
    return memcpy(dst,src,n);
}
#define LZ4_decompress_safe observed_decode
#define memcpy observed_copy
#include "rio_stream.c"
'''

class DecodeOnceTests(presentation.PresentationTests):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        source = Path(cls.tmp.name) / 'observe.c'
        source.write_text(WRAPPER)
        binary = Path(cls.tmp.name) / 'receiver.so'
        subprocess.run(['cc', '-std=c99', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                        '-I', str(ROOT / 'firmware/lt168b'), str(source),
                        str(ROOT / 'firmware/lt168b/rio_lz4.c'), '-o', str(binary)], check=True)
        cls.lib = ctypes.CDLL(str(binary))
        cls.lib.rio_stream_size.restype = ctypes.c_size_t
        cls.lib.rio_stream_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cls.lib.rio_stream_feed.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        cls.lib.rio_stream_staging.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                               ctypes.c_void_p, presentation.SYNC, ctypes.c_void_p]
        for name in ('rio_stream_completed', 'rio_stream_presentations', 'rio_stream_fallbacks'):
            getattr(cls.lib, name).argtypes = [ctypes.c_void_p]
            getattr(cls.lib, name).restype = ctypes.c_uint32
        cls.lib.oracle_watch.argtypes = [ctypes.c_void_p]
        cls.lib.oracle_offset.argtypes = cls.lib.oracle_length.argtypes = [ctypes.c_uint]
        cls.frame = bytes((i * 29 + i // 97) % 256 for i in range(FRAME_BYTES))

    def setUp(self):
        super().setUp()
        self.lib.oracle_watch(ctypes.addressof(self.storage) + 16)

    def work(self):
        calls = [(self.lib.oracle_offset(i), self.lib.oracle_length(i))
                 for i in range(self.lib.oracle_copies())]
        return self.lib.oracle_decodes(), calls

    @staticmethod
    def change_tiles(base, indices, noise=False):
        data = bytearray(base)
        randomizer = random.Random(747)
        for i in indices:
            for j in range(16):
                at = ((i // 15) * 16 + j) * 960 + (i % 15) * 64
                data[at:at+64] = randomizer.randbytes(64) if noise else bytes([0xf8, i % 255 + 1]) * 32
        return bytes(data)

    def assert_writes(self, indices):
        _, calls = self.work()
        expected = bytearray(FRAME_BYTES)
        actual = bytearray(FRAME_BYTES)
        for i in indices:
            for j in range(16):
                at = ((i // 15) * 16 + j) * 960 + (i % 15) * 64
                expected[at:at+64] = b'\x01' * 64
        for at, n in calls:
            self.assertFalse(any(actual[at:at+n]), 'overlapping framebuffer writes')
            actual[at:at+n] = b'\x01' * n
        self.assertEqual(actual, expected)
        self.assertEqual(calls, sorted(calls), 'publishing must follow scan order')

    def baseline(self, pixels=None):
        pixels = bytes(FRAME_BYTES) if pixels is None else pixels
        self.assertEqual(self.feed(b''.join(self.parts(pixels))), 1)
        self.expect_pixels(pixels)
        self.lib.oracle_clear()
        return pixels

    def test_native_sparse_decodes_once_and_copies_only_changed_tiles(self):
        old = self.baseline()
        indices = [0, 224, 449]
        new = self.change_tiles(old, indices)
        parts = self.parts(new, 2, old)
        compressed = sum(p[5] == 5 for p in parts)
        previous = self.storage.raw
        self.assertEqual(self.feed(b''.join(parts[:-1]), 13), 0)
        self.assertEqual(self.storage.raw, previous)
        self.assertEqual(self.work(), (compressed, []))
        self.assertEqual(self.feed(parts[-1], 1), 1)
        self.expect_pixels(new)
        self.assertEqual(self.work()[0], compressed)
        self.assert_writes(indices)
        self.assertEqual(self.lib.oracle_front_reads(), 0)

    def test_exact_arena_capacity_207_native_and_208_compressed(self):
        for count in (207, 208):
            with self.subTest(count=count):
                self.lib.rio_stream_init(self.state, ctypes.addressof(self.storage) + 16)
                self.bind()
                old = self.baseline()
                new = self.change_tiles(old, range(count))
                parts = self.parts(new, 2, old)
                compressed = sum(p[5] == 5 for p in parts)
                self.assertEqual(self.feed(b''.join(parts)), 1)
                self.expect_pixels(new)
                self.assertEqual(self.work()[0], compressed)
                self.assert_writes(range(count))

    def test_sparse_raw_and_compressed_tiles_shuffled(self):
        old = self.baseline()
        noisy = [0, 16, 224, 449]
        solid = [1, 29, 222]
        new = self.change_tiles(self.change_tiles(old, noisy, True), solid)
        parts = self.parts(new, 2, old)
        self.assertTrue(any(p[5] == 3 for p in parts))
        self.assertTrue(any(p[5] == 5 for p in parts))
        before = self.storage.raw
        self.assertEqual(self.feed(parts[0] + b''.join(reversed(parts[1:-1])), 1), 0)
        self.assertEqual(self.storage.raw, before)
        self.assertEqual(self.feed(parts[-1]), 1)
        self.expect_pixels(new)
        self.assert_writes(noisy + solid)

    def test_xor_prepared_against_stable_previous_frame(self):
        old = self.baseline(random.Random(819).randbytes(FRAME_BYTES))
        indices = [0, 1, 15, 224, 449]
        new = bytearray(old)
        for i in indices:
            for j in range(16):
                at = ((i // 15) * 16 + j) * 960 + (i % 15) * 64
                new[at:at+64] = bytes(b ^ 0x55 for b in new[at:at+64])
        parts = self.parts(bytes(new), 2, old)
        self.assertTrue(all(p[5] == 5 and p[24] == 1 for p in parts[1:-1]))
        self.assertEqual(self.feed(parts[0] + b''.join(reversed(parts[1:-1]))), 0)
        self.expect_pixels(old)
        self.assertEqual(self.feed(parts[-1]), 1)
        self.expect_pixels(new)
        self.assertEqual(self.work()[0], len(indices))
        self.assert_writes(indices)

    def test_unaligned_arena_uses_compressed_safe_path(self):
        self.lib.rio_stream_staging(self.state, ctypes.addressof(self.arena) + 17, 208 * 1024 - 1,
                                    ctypes.addressof(self.row) + 16, self.sync, None)
        old = self.baseline()
        new = self.change_tiles(old, [1, 16])
        parts = self.parts(new, 2, old)
        self.assertEqual(self.feed(b''.join(parts), 7), 1)
        self.expect_pixels(new)
        self.assertEqual(self.work()[0], sum(p[5] == 5 for p in parts))
        self.assert_writes([1, 16])

    def test_halfword_aligned_framebuffer_and_row(self):
        other = ctypes.create_string_buffer(b'\xa7' * (FRAME_BYTES + 36), FRAME_BYTES + 36)
        row = ctypes.create_string_buffer(b'\x6d' * (15360 + 36), 15360 + 36)
        self.lib.rio_stream_init(self.state, ctypes.addressof(other) + 18)
        self.lib.rio_stream_staging(self.state, ctypes.addressof(self.arena) + 16, 208 * 1024,
                                    ctypes.addressof(row) + 18, self.sync, None)
        self.lib.oracle_watch(ctypes.addressof(other) + 18)
        old = bytes(FRAME_BYTES)
        self.assertEqual(self.feed(b''.join(self.parts(old))), 1)
        self.lib.oracle_clear()
        new = self.change_tiles(old, [0, 16, 224, 449], True)
        self.assertEqual(self.feed(b''.join(self.parts(new, 2, old))), 1)
        expected = struct.pack('=230400H', *struct.unpack('>230400H', new))
        self.assertEqual(other.raw[18:-18], expected)
        self.assertEqual(other.raw[:18] + other.raw[-18:], b'\xa7' * 36)
        self.assertEqual(row.raw[:18] + row.raw[-18:], b'\x6d' * 36)
        self.assert_writes([0, 16, 224, 449])

    def test_full_band_and_adjacent_dirty_runs(self):
        old = self.baseline()
        indices = list(range(15)) + [16, 17, 18, 29, 449]
        new = self.change_tiles(old, indices)
        self.assertEqual(self.feed(b''.join(self.parts(new, 2, old))), 1)
        self.expect_pixels(new)
        self.assert_writes(indices)
        calls = self.work()[1]
        self.assertEqual(calls[0], (0, 15360))
        self.assertIn((15360 + 64, 192), calls)

    def test_native_late_crc_error_never_publishes_prepared_tiles(self):
        old = self.baseline()
        parts = self.parts(self.change_tiles(old, [0, 100, 449]), 2, old)
        self.assertEqual(self.feed(b''.join(parts[:3])), 0)
        bad = bytearray(parts[3]);bad[-1] ^= 1
        self.assertEqual(self.feed(bytes(bad)), -1)
        self.expect_pixels(old)
        self.assertEqual(self.work()[1], [])
        fresh = bytes([0x12, 0x34]) * (FRAME_BYTES // 2)
        self.assertEqual(self.feed(b''.join(self.parts(fresh, 3))), 1)
        self.expect_pixels(fresh)

    def test_native_reset_drops_prepared_data_and_requires_keyframe(self):
        old = self.baseline()
        new = self.change_tiles(old, [0, 100, 449])
        self.assertEqual(self.feed(b''.join(self.parts(new, 2, old)[:-1])), 0)
        self.lib.rio_stream_init(self.state, ctypes.addressof(self.storage) + 16)
        self.bind()
        self.expect_pixels(old)
        self.assertEqual(self.feed(b''.join(self.parts(new, 3, old))), -1)
        self.assertEqual(self.feed(b''.join(self.parts(new, 4))), 1)
        self.expect_pixels(new)

    def test_native_missing_duplicate_and_sync_failure_keep_previous_frame(self):
        for failure in ('missing', 'duplicate', 'sync'):
            with self.subTest(failure=failure):
                self.lib.rio_stream_init(self.state, ctypes.addressof(self.storage) + 16)
                self.bind();self.sync_allowed = True
                old = self.baseline()
                parts = self.parts(self.change_tiles(old, [0, 100, 449]), 2, old)
                if failure == 'missing': data = b''.join(parts[:2] + parts[3:])
                elif failure == 'duplicate': data = parts[0] + parts[1] + parts[1]
                else: self.sync_allowed = False;data = b''.join(parts)
                self.assertEqual(self.feed(data), -1)
                self.expect_pixels(old)
                self.assertEqual(self.work()[1], [])

if __name__ == '__main__':
    import unittest
    unittest.main()

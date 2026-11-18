"""Large staged-frame compression policy, unchanged pixel/protocol contracts."""
import random
import struct
import unittest
from unittest.mock import patch

import lz4.block
from rio_monitor.lt168b_stream import (COMPRESSED_TILE, FRAME_BYTES, HEADER,
                                      TILE, encode_frame)


def changed_frame(count, tile):
    data = bytearray(FRAME_BYTES)
    for index in range(count):
        for row in range(16):
            start = ((index // 15) * 16 + row) * 960 + index % 15 * 64
            data[start:start + 64] = tile[row * 64:(row + 1) * 64]
    return bytes(data)


class LargeCompressionTests(unittest.TestCase):
    def encode(self, frame):
        return list(encode_frame(frame, session=133, frame=2,
                                 acknowledged=bytes(FRAME_BYTES), compression=True))

    def test_native_staged_frames_never_request_high_compression(self):
        for count in (0, 1, 207):
            with self.subTest(count=count):
                with patch('lz4.block.compress', wraps=lz4.block.compress) as compress:
                    self.encode(changed_frame(count, b'\x12\x34' * 512))
                self.assertTrue(all(call.kwargs.get('mode') != 'high_compression'
                                    for call in compress.call_args_list))

    def test_large_complete_staging_uses_same_predictor_and_never_grows(self):
        rng = random.Random(517)
        words = [rng.randbytes(8) for _ in range(24)]
        tile = b''.join(rng.choice(words) for _ in range(128))
        frame = changed_frame(208, tile)
        original_compress = lz4.block.compress
        # The original encoder's default compressor is an independent
        # reference for the unchanged operation/predictor/size contracts.
        def default_only(source, **kwargs):
            return original_compress(source, store_size=False)
        with patch('lz4.block.compress', side_effect=default_only):
            baseline = self.encode(frame)
        with patch('lz4.block.compress', wraps=original_compress) as compress:
            candidate = self.encode(frame)
        self.assertTrue(any(call.kwargs.get('mode') == 'high_compression'
                            for call in compress.call_args_list))
        self.assertEqual(candidate[0], baseline[0])
        self.assertEqual(candidate[-1], baseline[-1])
        self.assertEqual(len(candidate), len(baseline))
        reconstructed = bytearray(FRAME_BYTES)
        for before, after in zip(baseline[1:-1], candidate[1:-1]):
            old_fields, fields = HEADER.unpack(before[:20]), HEADER.unpack(after[:20])
            self.assertEqual(old_fields[:3], fields[:3])
            self.assertEqual(old_fields[4:], fields[4:])
            self.assertLessEqual(len(after), len(before))
            if fields[2] == COMPRESSED_TILE:
                self.assertEqual(after[24], before[24])
                raw = lz4.block.decompress(after[25:], uncompressed_size=1024)
            else:
                self.assertEqual(fields[2], TILE)
                raw = after[24:]
            # Old frame is zero: absolute and XOR both resolve to raw.
            tile_index = fields[-1]
            for row in range(16):
                at = ((tile_index // 15) * 16 + row) * 960 + tile_index % 15 * 64
                reconstructed[at:at + 64] = raw[row * 64:(row + 1) * 64]
        self.assertEqual(bytes(reconstructed), frame)

    def test_original_staging_overflow_never_requests_high_compression(self):
        frame = random.Random(814).randbytes(FRAME_BYTES)
        with patch('lz4.block.compress', wraps=lz4.block.compress) as compress:
            parts = self.encode(frame)
        self.assertGreater(sum(len(p) - 24 + 2 for p in parts[1:-1]), 208 * 1024)
        self.assertTrue(all(call.kwargs.get('mode') != 'high_compression'
                            for call in compress.call_args_list))

    def test_noncompression_capability_stays_raw(self):
        with patch('lz4.block.compress', side_effect=AssertionError('unexpected codec')):
            parts = list(encode_frame(bytes(FRAME_BYTES), session=133, frame=1))
        self.assertEqual(len(parts), 452)
        self.assertTrue(all(p[5] == TILE for p in parts[1:-1]))

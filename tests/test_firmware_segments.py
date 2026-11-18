"""Release input is private; protocol and failure tests also run on synthetic images."""
import contextlib
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rio_monitor import firmware_segments as seg


class MemoryScreen:
    def __init__(self, package):
        gap = b"".join(hashlib.sha256(str(i).encode()).digest() * 128 for i in range(147))
        self.flash = bytearray(package.previous + gap + seg.BLANK + b"G" * seg.SECTOR)
        self.written = []
        self.started = False
        self.damage = None

    def identify(self):
        return seg.LOADER

    def checksum(self, end):
        return seg.crc(memoryview(self.flash)[:end])

    def write_image(self, image, acknowledged):
        self.written.append(image.window)
        start, end = image.window
        self.flash[start:end] = image.data
        if self.damage is not None:
            self.flash[self.damage] ^= 1
        acknowledged(len(image.data))

    def run(self):
        self.started = True


class SegmentedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = seg.Package(seg.Image(0, b"L" * seg.LOW_END),
                                  seg.Image(seg.BANK, b"A" * len(seg.BLANK)), b"P" * seg.LOW_END)

    def setUp(self):
        self.screen = MemoryScreen(self.package)
        baseline = {end: self.screen.checksum(end) for end in seg.CURRENT}
        self.events = []
        mock = patch.object(seg, "CURRENT", baseline)
        mock.start()
        self.addCleanup(mock.stop)

    def call(self, write=True):
        return seg.update(self.screen, self.package, write, self.events.append)

    def qualified(self):
        return patch.object(seg, "ERASE_RECORDS", {seg.LOADER: {self.package.application.window: "simulated-low",
                                                                self.package.animation.window: "simulated-high"}})

    def test_real_profile_requires_both_windows_before_any_write(self):
        with self.assertRaises(seg.EraseScopeUnknown):
            self.call()
        self.assertEqual(self.screen.written, [])
        self.assertTrue(self.screen.started)
        scope = next(e for e in self.events if e["stage"] == "erase_scope")
        self.assertEqual(scope["missing_windows"], [["0x600a0000", "0x601ed000"]])
        self.assertEqual(len(self.events[1]["gap_sector_crcs"]), 147)

    def test_read_only_checks_board_without_writes(self):
        self.assertEqual(self.call(False), "device_checked_scope_unproven")
        self.assertEqual(self.screen.written, [])

    def test_two_windows_asset_first_all_other_bytes_unchanged(self):
        original = bytes(self.screen.flash)
        with self.qualified():
            self.assertEqual(self.call(), "segments_verified_and_started")
        self.assertEqual(self.screen.written, [self.package.animation.window, self.package.application.window])
        self.assertEqual(self.screen.flash, self.package.application.data + original[seg.LOW_END:seg.BANK]
                         + self.package.animation.data + original[seg.BANK_END:])
        receipts = [e for e in self.events if "gap_sector_crcs" in e]
        self.assertEqual(len(receipts), 3)
        for record in receipts:
            self.assertEqual(record["gap_sector_crcs"], receipts[0]["gap_sector_crcs"])
            self.assertEqual(record["next_sector_crc"], receipts[0]["next_sector_crc"])
        self.assertTrue(self.screen.started)

    def test_protected_corruption_after_first_step_prevents_activation(self):
        for offset in (seg.LOW_END, seg.BANK - 1, seg.BANK_END, seg.BANK + seg.SECTOR):
            with self.subTest(offset=offset), self.qualified():
                self.screen = MemoryScreen(self.package)
                self.screen.damage = offset
                with self.assertRaisesRegex(OSError, "checksum"):
                    self.call()
                self.assertEqual(self.screen.written, [self.package.animation.window])
                self.assertFalse(self.screen.started)

    def test_partial_unknown_or_corrupt_original_does_not_mutate(self):
        for offset in (0, seg.LOW_END, seg.BANK - 1, seg.BANK + 17, seg.END_GUARD - 1):
            with self.subTest(offset=offset), self.qualified():
                self.screen = MemoryScreen(self.package)
                self.screen.flash[offset] ^= 1
                with self.assertRaises((ValueError, OSError)):
                    self.call()
                self.assertEqual(self.screen.written, [])
                self.assertFalse(self.screen.started)

    def test_completed_bank_resumes_without_rewriting_and_finishes_idempotently(self):
        self.screen.flash[seg.BANK:seg.BANK_END] = self.package.animation.data
        self.assertEqual(self.call(), "segments_verified_and_started")
        self.assertEqual(self.call(), "already_installed_and_verified")
        self.assertEqual(self.screen.written, [self.package.application.window])

    def test_wrong_loader_stops_before_flash_reads(self):
        self.screen.identify = lambda: (1, 2)
        self.screen.checksum = unittest.mock.Mock(side_effect=AssertionError)
        with self.assertRaisesRegex(ValueError, "bootloader"):
            self.call()
        self.assertEqual(self.screen.written, [])

    def test_tampered_package_is_rejected_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.zip"
            path.write_bytes(b"fake")
            with self.assertRaisesRegex(ValueError, "checksum"):
                seg.load_package(path)

    def test_real_wire_driver_refuses_unqualified_high_before_writing_any_bytes(self):
        port = unittest.mock.Mock()
        device = seg.RioLoader(port)
        device.loader = seg.LOADER
        with self.assertRaises(seg.EraseScopeUnknown):
            device.write_image(self.package.animation, lambda n: None)
        port.write.assert_not_called()


class WireScreen:
    """In-memory CDC emulator with the physical loader's response framing."""
    def __init__(self, backing):
        self.backing = backing
        self.calls = []
        self.queue = b""
        self.fail_ack = False
        self.short = False
        self.length_error = False
        self.bad_identity = False

    @property
    def in_waiting(self):
        return len(self.queue)

    def read(self, n):
        data = self.queue[:min(17,n)]
        self.queue = self.queue[len(data):]
        return data

    def flush(self):
        pass

    def write(self, packet):
        command = packet[0]
        self.calls.append((command, packet[1]))
        reply = bytearray(63)
        reply[0] = command
        if command == 0x4B:
            values = seg.IDENTITY_REPLY if packet[1] == 0x30 else (3284128312, 2108034405, *seg.LOADER)
            struct.pack_into("<4I", reply, 1, *values)
            if self.bad_identity:reply[13] ^= 1
            assert seg.crc(packet[:32]) == struct.unpack_from("<I", packet, 32)[0]
        elif command == 0x4E:
            end, = struct.unpack_from("<I", packet, 4)
            struct.pack_into("<II", reply, 1, self.backing.checksum(end), end + self.length_error)
            assert seg.crc(packet[:16]) == struct.unpack_from("<I", packet, 16)[0]
        elif command == 0x4C:
            start, length = struct.unpack_from("<II", packet, 1)
            assert seg.crc(packet[:9]) == struct.unpack_from("<I", packet, 9)[0]
            self.backing.written.append((start, start+length))
            self.backing.flash[start:start+length] = b"\xff" * length
        elif command == 0x4A:
            start, n = struct.unpack_from("<IH", packet, 2)
            assert seg.crc(packet[:-4]) == struct.unpack_from("<I", packet, len(packet)-4)[0]
            lo, hi = self.backing.written[-1]
            assert lo <= start < start+n <= hi and n == seg.CHUNK
            self.backing.flash[start:start+n] = packet[8:8+n]
            struct.pack_into("<I", reply, 2, start + self.fail_ack)
        elif command == 0x4F:
            self.backing.started = True
            return len(packet)
        else:
            raise AssertionError("Unexpected command")
        self.queue = bytes(reply)
        return len(packet) - self.short


@unittest.skipUnless(os.getenv("RIO_SEGMENT_PACKAGE"), "Private release ZIP required for wire-payload tests")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.package = seg.load_package(os.environ["RIO_SEGMENT_PACKAGE"])
        self.screen = MemoryScreen(self.package)
        self.port = WireScreen(self.screen)
        self.dev = seg.RioLoader(self.port)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(seg, "CURRENT", {n: self.screen.checksum(n) for n in seg.CURRENT}))

    def call(self):
        return seg.update(self.dev, self.package, True, lambda e: None)

    def add_simulated_qualification(self):
        self.stack.enter_context(patch.object(seg, "ERASE_RECORDS", {seg.LOADER: {self.package.animation.window: "test",
                                                                                self.package.application.window: "test"}}))

    def test_release_window_sizes_order_checks_and_checksums(self):
        self.assertEqual(self.package.describe()["protected_bytes"], 602112)
        old = bytes(self.screen.flash)
        self.add_simulated_qualification()
        self.assertEqual(self.call(), "segments_verified_and_started")
        self.assertEqual(self.port.calls.count((0x4A, 0x30)), 672)
        self.assertEqual(self.screen.written, [self.package.animation.window, self.package.application.window])
        self.assertEqual(self.screen.flash, self.package.application.data + old[seg.LOW_END:seg.BANK]
                         + self.package.animation.data + old[seg.BANK_END:])
        self.assertEqual(self.port.calls[-1], (0x4F, 0))

    def test_real_qualification_sends_only_identity_checksums_and_verified_run(self):
        with self.assertRaises(seg.EraseScopeUnknown):self.call()
        self.assertEqual(self.port.calls, [(0x4B, 0x30)] + [(0x4E, 0)]*len(seg.ENDS) + [(0x4F, 0)])

    def test_serial_faults_stop_without_start_or_retry(self):
        for fault, expected in (("short", OSError), ("bad_identity", ValueError), ("length_error", OSError), ("fail_ack", OSError)):
            with self.subTest(fault=fault):
                self.port = WireScreen(self.screen)
                self.dev = seg.RioLoader(self.port)
                setattr(self.port, fault, True)
                self.add_simulated_qualification()
                with self.assertRaises(expected):self.call()
                self.assertNotIn((0x4F, 0), self.port.calls)
                self.assertLessEqual(self.port.calls.count((0x4A, 0x30)), 1)

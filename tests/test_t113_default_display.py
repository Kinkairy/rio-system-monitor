from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rio_monitor import display_protocols, t113_display
from rio_monitor.firmware_update import FirmwareUpdate
from rio_monitor.storage import DisplaySession


class T113DefaultDisplayTests(unittest.TestCase):
    def test_normal_session_finds_and_selects_qualified_serial_screen(self):
        qualified = SimpleNamespace(
            vid=0x1234, pid=0x5678, serial_number="RIOWS21T1130001", device="COM9"
        )
        unrelated = SimpleNamespace(
            vid=0x1234, pid=0x5678, serial_number="stock-display", device="COM5"
        )
        paths = t113_display.qualified_paths([unrelated, qualified])
        with (
            patch("rio_monitor.winusb.enumerate_paths", return_value=[]),
            patch("rio_monitor.t113_display.enumerate_t113_paths", return_value=paths),
            patch.dict("sys.modules", {"hid": None}),
        ):
            path = DisplaySession().one_path()
        self.assertEqual(path, "rio-t113:COM9")
        self.assertEqual(display_protocols.capabilities_for(path), t113_display.T113)
        self.assertIsInstance(display_protocols.create_protocol(path), t113_display.T113Protocol)


    def test_current_or_unknown_receiver_only_gets_a_version_query(self):
        path = "rio-t113-update:COM9"
        target = 0x7C7B18F6
        for active, trial, reason in (
            (target, False, "already_current"),
            (0x12345678, False, "skipped"),
            (0xBC18466B, True, "skipped"),
        ):
            with self.subTest(active=active, trial=trial):
                with patch.object(t113_display, "firmware_exchange", return_value=(active, trial)) as exchange:
                    result = t113_display.install_firmware(
                        path, (b"unused", target), lambda: [path], Mock(), open_link=Mock()
                    )
                self.assertTrue(result[reason])
                self.assertEqual(result["after_crc32"], active)
                exchange.assert_called_once()
                self.assertEqual(exchange.call_args.args[1], t113_display.FW_INFO)

    def test_automatic_detection_defers_for_media_or_ambiguous_attachment(self):
        destination = "rio-t113-update:COM9"
        paths = [destination]
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / t113_display.WAVESHARE_FIRMWARE).touch()
            session = DisplaySession(enumerator=lambda: paths.copy())
            session.output = SimpleNamespace(path=destination, error=None, sent=0)
            firmware = FirmwareUpdate(session, folder, folder)

            self.assertFalse(firmware.detect())  # Display has not acknowledged a frame.
            session.output.sent = 1
            paths.append("rio-t113-media:COM8")
            self.assertFalse(firmware.detect())
            paths.pop()
            session.resource_active = True
            self.assertFalse(firmware.detect())
            self.assertIsNone(firmware.thread)

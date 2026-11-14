"""Protocol adapters for the single RIO display worker.

Adapters own wire format and capabilities, never collection, rendering or UI.
Stock LEVETOP uses register telemetry. Qualified RIO LT168B firmware accepts
full frames after its capability handshake; discovery never writes firmware.
"""
from dataclasses import dataclass
import math
import re
import struct
import time
from typing import Protocol


@dataclass(frozen=True)
class Capabilities:
    protocol: str
    frames: bool
    samples: bool
    stored_media: bool
    size: tuple | None = None
    interval: float = 1 / 12
    startup_delay: float = 0.0


LEGACY = Capabilities('rio-winusb', True, False, True, (480, 480), startup_delay=1.0)
LEVETOP = Capabilities('levetop-emonitor', False, True, False, None, .5)


class DisplayProtocol(Protocol):
    capabilities: Capabilities
    def open(self, path): ...
    def initialize(self): ...
    def send(self, content, cancelled=lambda: False) -> bool: ...
    def close(self): ...


class UnsupportedDisplay(RuntimeError):
    pass


class UncertainDisplayIO(OSError):
    # Untagged replies cannot safely be matched after an interrupted transfer.
    requires_replug = True


def device_id(path):
    match = re.search(r'vid_([0-9a-f]{4})&pid_([0-9a-f]{4})(?:[#&\\]|$)', str(path), re.I)
    return tuple(int(v, 16) for v in match.groups()) if match else None


def capabilities_for(path):
    identity = device_id(path)
    if identity == (0xffff, 0x168b):
        from .lt168b_display import BENCH
        return BENCH
    if identity == (0xEEEF, 0x1616):
        return LEVETOP
    if identity == (0x2A55, 0x9990):
        return LEGACY
    raise UnsupportedDisplay('No qualified protocol for this display')


class LegacyProtocol:
    capabilities = LEGACY

    def __init__(self, transport_factory, sender_factory):
        self.transport_factory = transport_factory
        self.sender_factory = sender_factory
        self.transport = None

    def open(self, path):
        self.transport = self.transport_factory(path)
        self.sender = self.sender_factory(self.transport)

    def initialize(self):
        self.sender.lcd_info()

    def send(self, image, cancelled=lambda: False):
        if cancelled():
            return False
        from .protocol import encode_rgb565
        if image.size != self.capabilities.size:
            raise ValueError('Expected a 480x480 frame')
        self.sender.send(encode_rgb565(image))
        return True

    def close(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None


def crc16(data):
    crc = 0xffff
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xa001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, 'little')


def register_write(address, data):
    data = bytes(data)
    # Only volatile widget RAM. System, bootloader and flash registers excluded.
    if not data or len(data) % 2 or len(data) > 248:
        raise ValueError('Expected 1..124 complete register words')
    if not isinstance(address, int) or address < 0 or address + len(data) // 2 > 0x6000:
        raise ValueError('Only widget RAM writes are supported')
    body = b'\x10' + struct.pack('>H', address) + data
    return b'\x5a\xa5' + bytes([len(body) + 2]) + body + crc16(body)


def hid_reports(command):
    # Report ID zero is on OUT; HIDAPI strips it from unnumbered IN reports.
    return tuple(b'\0' + command[i:i+64].ljust(64, b'\0') for i in range(0, len(command), 64))


def validate_ack(data):
    data = bytes(data)
    # A bounded protocol prefix is enough to diagnose status/CRC failures;
    # never dump arbitrary trailing device memory into the application log.
    detail = f'length={len(data)} prefix={data[:7].hex()} nonzero_tail={any(data[7:])}'
    if len(data) < 7 or data[:3] != b'\x5a\xa5\x04':
        reason = 'Malformed LEVETOP acknowledgement'
    elif crc16(data[3:5]) != data[5:7]:
        reason = 'LEVETOP acknowledgement CRC mismatch'
    elif data[3:5] != b'\x10\xff':
        reason = 'LEVETOP command rejected or unexpected response'
    elif any(data[7:]):
        reason = 'Unexpected data after LEVETOP acknowledgement'
    else:
        return
    raise UncertainDisplayIO(f'{reason}; {detail}')


def sample_commands(samples, now=None):
    now = time.monotonic() if now is None else now
    def current(key):
        sample = samples.get(key)
        return sample.current(now) if sample is not None else None
    values = [(0x0000, current('cpu')), (0x000c, current('gpu'))]
    used, total = current('ram_used'), current('ram_total')
    if used is not None and total is not None and 0 <= used <= total and total > 0:
        values.append((0x0020, 100 * used / total))
    # Vendor templates use uint64 big-endian percentages at these word addresses.
    # Missing/stale samples are omitted, never converted to synthetic zeroes.
    return [register_write(addr, struct.pack('>Q', int(value)))
            for addr, value in values
            if value is not None and math.isfinite(value) and 0 <= value <= 100]


class LevetopProtocol:
    capabilities = LEVETOP

    def __init__(self, device_factory=None, clock=time.monotonic):
        self.device_factory = device_factory
        self.clock = clock
        self.device = None
        self.faulted = False

    def open(self, path):
        if capabilities_for(path) != LEVETOP:
            raise UnsupportedDisplay('Not a qualified LEVETOP interface')
        if self.device_factory is None:
            import hid
            self.device_factory = hid.device
        self.device = self.device_factory()
        self.device.open_path(path.encode() if isinstance(path, str) else path)

    def initialize(self):
        # No brightness, time, reset, theme or firmware modification on connect.
        if self.device.read(64, 10):
            self.faulted = True
            raise UncertainDisplayIO('Pending HID reply; unplug before starting a new session')

    def send(self, samples, cancelled=lambda: False):
        if self.faulted:
            raise UncertainDisplayIO('LEVETOP session is faulted; no command replay')
        commands = sample_commands(samples)
        try:
            for command in commands:
                if cancelled():
                    return False
                for report in hid_reports(command):
                    if self.device.write(report) != len(report):
                        raise UncertainDisplayIO('Short HID write; delivery is uncertain')
                reply = b''
                deadline = self.clock() + 2
                for _ in range(10):
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        break
                    reply = self.device.read(64, max(1, min(200, int(remaining * 1000))))
                    if reply:
                        validate_ack(reply)
                        break
                else:
                    raise UncertainDisplayIO('HID acknowledgement timed out')
                if not reply:
                    raise UncertainDisplayIO('HID acknowledgement timed out')
        except Exception as exc:
            self.faulted = True
            if isinstance(exc, UncertainDisplayIO):
                raise
            raise UncertainDisplayIO(str(exc)) from exc
        return bool(commands)

    def close(self):
        if self.device is not None:
            self.device.close()
            self.device = None


def enumerate_paths():
    from .winusb import enumerate_paths as legacy_paths
    paths = list(legacy_paths())
    try:
        import hid
    except ModuleNotFoundError:
        return paths  # Existing WinUSB installations still work without HID extras.
    for device in hid.enumerate(0xEEEF, 0x1616):
        if (device.get('usage_page'), device.get('usage')) != (1, 0):
            continue
        if device.get('manufacturer_string') != 'LEVETOP':
            continue
        path = device['path']
        paths.append(path.decode() if isinstance(path, bytes) else path)
    return sorted(set(paths))


def create_protocol(path, legacy_transport_factory=None, legacy_sender_factory=None):
    if device_id(path) == (0xffff, 0x168b):
        from .lt168b_display import LT168BBenchProtocol
        return LT168BBenchProtocol()
    if device_id(path) == (0xEEEF, 0x1616):
        return LevetopProtocol()
    if legacy_transport_factory is None:
        from .winusb import WinUSB
        legacy_transport_factory = WinUSB
    if legacy_sender_factory is None:
        from .protocol import FrameSender
        legacy_sender_factory = FrameSender
    # WinUSB validates the exact legacy identity before opening any handle.
    return LegacyProtocol(legacy_transport_factory, legacy_sender_factory)

"""Full-frame adapter for the physically qualified RIO LT168B firmware.

The stock EMonitor firmware is incompatible. Require the bench identity AND
validated capability reply before resetting or sending any pixels.
"""
import secrets
import struct
import zlib

from .display_protocols import Capabilities, UnsupportedDisplay, device_id
from .lt168b_stream import encode_frame
from .protocol import encode_rgb565

BENCH = Capabilities('lt168b-rio-bench', True, False, False, (480, 480), interval=1/30)
HELLO = struct.Struct('<4sHHHHHHIIII')
ACK = struct.Struct('<4sHHIIII')


def validate_hello(data):
    if len(data) != HELLO.size:
        raise UnsupportedDisplay('Invalid capability length')
    fields = HELLO.unpack(data)
    expected = (b'RIO1', 1, 32, 480, 480, 32, 16, fields[7], 1048, 460800)
    if fields[7] not in (1, 3) or fields[:-1] != expected:
        raise UnsupportedDisplay('Device does not support the RIO full-frame protocol')
    if HELLO.unpack(data)[-1] != zlib.crc32(data[:-4]):
        raise UnsupportedDisplay('Corrupt full-frame capability reply')
    return bool(fields[7] & 2)


class LT168BBenchProtocol:
    capabilities = BENCH

    def __init__(self, transport_factory=None, session_factory=None):
        if transport_factory is None:
            from .winusb import WinUSB
            transport_factory = lambda path: WinUSB(path, profile='lt168b-bench')
        self.transport_factory = transport_factory
        self.session_factory = session_factory or (lambda: secrets.randbelow(0xffffffff) + 1)
        self.transport = None
        self.ready = False
        self.base = None
        self.frame = self.completed = 0

    def open(self, path):
        if device_id(path) != (0xffff, 0x168b):
            raise UnsupportedDisplay('Bench adapter cannot open stock display firmware')
        self.close()
        self.transport = self.transport_factory(path)

    def initialize(self):
        self.ready = False
        self.base = None
        if self.transport is None:
            raise OSError('Display is not open')
        self.compression = validate_hello(self.transport.control(0xc1, 0x52, 0, 0, 32))
        session = self.session_factory()
        if not 1 <= session <= 0xffffffff:
            raise ValueError('Invalid session identifier')
        # No failed transfer is replayed. A fresh transport/reset starts a new
        # session and requires a complete keyframe, even after a lost ACK.
        self.transport.reset_pipes()
        if self.transport.control(0x41, 0x53, 0, 0, 0) != b'':
            raise OSError('Invalid stream-reset response')
        self.session = session
        self.frame = self.completed = 0
        self.ready = True

    def send(self, image, cancelled=lambda: False):
        if not self.ready:
            raise OSError('Full-frame handshake required')
        if image.size != (480, 480):
            raise ValueError('Expected a 480x480 frame')
        if cancelled():
            return False
        pixels = encode_rgb565(image)
        sequence = self.frame + 1
        if sequence > 0xffffffff:
            self.ready = False
            self.base = None
            raise OSError('New stream session required')
        try:
            # Firmware parses a byte stream, independent of host write boundaries.
            # Batch one frame only; its validated ACK still gates the next frame.
            payload = b''.join(encode_frame(pixels, session=self.session, frame=sequence, acknowledged=self.base, compression=self.compression))
            for offset in range(0, len(payload), 64 * 1024):
                packet = payload[offset:offset + 64 * 1024]
                if cancelled():
                    self.ready = False
                    self.base = None
                    return False
                if self.transport.write(1, packet) != len(packet):
                    raise OSError('Short pixel write; frame completion is unknown')
            data = self.transport.read(0x82, ACK.size)
            if len(data) != ACK.size:
                raise OSError('Short frame acknowledgement')
            expected = (b'RIOA', 1, 0, self.session, sequence, self.completed + 1)
            if ACK.unpack(data)[:-1] != expected or ACK.unpack(data)[-1] != zlib.crc32(data[:-4]):
                raise OSError('Rejected, stale or corrupt frame acknowledgement')
        except Exception:
            self.ready = False
            self.base = None
            raise
        self.frame = sequence
        self.completed += 1
        self.base = pixels
        return True

    def close(self):
        self.ready = False
        self.base = None
        if self.transport is not None:
            transport, self.transport = self.transport, None
            transport.close()

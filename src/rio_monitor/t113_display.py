"""RIO1 transport for the T113 receiver. The caller supplies one qualified CDC link."""
from contextlib import closing
from dataclasses import replace
import os
import re
import struct
import time
import zlib

from .display_protocols import Capabilities, UnsupportedDisplay
from .lt168b_display import ACK, HELLO, LT168BBenchProtocol

RECORD = struct.Struct("<4sBBHI")
PUSH, HELLO_REQUEST, RESET_REQUEST = 1, 0x52, 0x53
MEDIA_BEGIN, MEDIA_DATA, MEDIA_COMMIT = 0x60, 0x61, 0x62
MEDIA_ACK = struct.Struct("<4sBBH")
CHUNK_LIMIT = 64 * 1024

USB_IDENTITY = (0x1234, 0x5678, "RIOWS21T1130001")
PATH_PREFIX = "rio-t113:"
USB_MEDIA_IDENTITY = (0x1234, 0x5678, "RIOWS21T1130002")
MEDIA_PREFIX = "rio-t113-media:"
USB_MOUNTED_IDENTITY = (0x1234, 0x5678, "RIOWS21T1130003")
MOUNTED_PREFIX = "rio-t113-mounted:"
USB_UPDATE_IDENTITY = (0x1234, 0x5678, "RIOWS21T1130004")
UPDATE_PREFIX = "rio-t113-update:"
T113 = Capabilities("rio-t113-cdc", True, False, False, (480, 480), interval=1/30)

T113_MEDIA = Capabilities("rio-t113-cdc", True, False, True, (480, 480), interval=1/30)
T113_MOUNTED = replace(T113_MEDIA, rotation_profile="waveshare-t113-2.1-a")


def is_t113_path(path):
    return isinstance(path, str) and re.fullmatch(r"rio-t113(?:-media|-mounted|-update)?:COM[1-9][0-9]*", path) is not None


def is_t113_media_path(path):
    return is_t113_path(path) and path.startswith((MEDIA_PREFIX, MOUNTED_PREFIX, UPDATE_PREFIX))


def is_t113_update_path(path):
    return is_t113_path(path) and path.startswith(UPDATE_PREFIX)


def t113_capabilities(path):
    if is_t113_path(path) and path.startswith((MOUNTED_PREFIX, UPDATE_PREFIX)):
        return T113_MOUNTED
    return T113_MEDIA if is_t113_media_path(path) else T113


def qualified_paths(ports):
    prefixes = {USB_IDENTITY: PATH_PREFIX, USB_MEDIA_IDENTITY: MEDIA_PREFIX,
                USB_MOUNTED_IDENTITY: MOUNTED_PREFIX, USB_UPDATE_IDENTITY: UPDATE_PREFIX}
    paths = []
    for port in ports:
        prefix = prefixes.get((port.vid, port.pid, port.serial_number))
        if prefix and is_t113_path(prefix + port.device):
            paths.append(prefix + port.device)
    return paths


def enumerate_t113_paths():
    if os.name != "nt":
        return []
    try:
        from serial.tools.list_ports import comports
        return qualified_paths(comports())
    except (ImportError, OSError):
        return []


def open_t113_serial(path):
    if path not in enumerate_t113_paths():
        raise UnsupportedDisplay("The RIO T113 receiver is no longer on this port")
    from serial import Serial
    return Serial(path.split(":", 1)[1], 115200, timeout=2, write_timeout=3)


class CdcTransport:
    def __init__(self, serial_link):
        self.link = serial_link

    def _request(self, command, data=b""):
        packet = RECORD.pack(b"RCDC", 1, command, 0, len(data)) + data
        if self.link.write(packet) != len(packet):
            raise OSError("Short RIO CDC write")

    def read(self, endpoint, length, *, timeout=3):
        if endpoint != 0x82:
            raise ValueError("Unexpected RIO endpoint")
        deadline = time.monotonic() + timeout
        result = bytearray()
        while len(result) < length:
            remaining = length - len(result)
            part = self.link.read(remaining)
            if (not part and timeout <= 3) or len(part) > remaining or time.monotonic() > deadline:
                raise OSError("Incomplete RIO CDC reply")
            result.extend(part)
        return bytes(result)

    def write(self, endpoint, data):
        if endpoint != 1 or not 0 < len(data) <= CHUNK_LIMIT:
            raise ValueError("Unexpected RIO CDC transfer")
        self._request(PUSH, data)
        return len(data)

    def control(self, request_type, request, value, index, length):
        if (request_type, request, value, index, length) == (0xc1, HELLO_REQUEST, 0, 0, HELLO.size):
            self._request(HELLO_REQUEST)
            return self.read(0x82, HELLO.size)
        if (request_type, request, value, index, length) == (0x41, RESET_REQUEST, 0, 0, 0):
            self._request(RESET_REQUEST)
            reply = self.read(0x82, ACK.size)
            fields = ACK.unpack(reply)
            if fields[:-1] != (b"RIOA", 1, 0, 0, 0, 0) or fields[-1] != zlib.crc32(reply[:-4]):
                raise OSError("Invalid RIO CDC reset acknowledgement")
            return b""
        raise ValueError("Unsupported RIO CDC control")

    def reset_pipes(self):
        # The stream baseline is reset by the acknowledged RIO reset request.
        if hasattr(self.link, "reset_input_buffer"):
            self.link.reset_input_buffer()

    def close(self):
        self.link.close()


class T113MediaSender:
    def __init__(self, transport):
        self.transport = transport

    def exchange(self, command, payload=b"", *, timeout=3):
        self.transport._request(command, payload)
        reply = self.transport.read(0x82, MEDIA_ACK.size, timeout=timeout)
        if MEDIA_ACK.unpack(reply) != (b"RIOM", 1, command, 0):
            raise OSError("T113 rejected screen content / 微雪屏拒绝写入内容")

    def upload(self, blob, progress, before_erase=None):
        # DisplaySession has already checked the existing GIF resource envelope.
        gif = blob[16:]
        self.transport.reset_pipes()
        self.exchange(MEDIA_BEGIN, struct.pack("<II", len(gif), zlib.crc32(gif)))
        for offset in range(0, len(gif), CHUNK_LIMIT):
            part = gif[offset:offset + CHUNK_LIMIT]
            self.exchange(MEDIA_DATA, part)
            progress("write", offset + len(part), len(gif) + 1)
        if before_erase:
            before_erase()
        self.exchange(MEDIA_COMMIT, timeout=25)
        progress("write", len(gif) + 1, len(gif) + 1)


FW_INFO, FW_BEGIN, FW_DATA, FW_APPLY, FW_CONFIRM = range(0x68, 0x6d)
FW_REPLY = struct.Struct("<4sBBHII")
FW_HEADER = struct.Struct("<8sII")
FW_MAX_BYTES = 750_000 + FW_HEADER.size + 64
WAVESHARE_FIRMWARE = "rio-waveshare-0.1.25.riofw"
# The built-in receiver on the 48 MiB USB-update image. Unknown or later
# versions must not be replaced by an old copy of the desktop program.
WAVESHARE_REPLACES = frozenset({0xBC18466B})


def read_firmware_package(path):
    with open(path, "rb") as stream:
        data = stream.read(FW_MAX_BYTES + 1)
    if not FW_HEADER.size + 64 + 64 <= len(data) <= FW_MAX_BYTES:
        raise ValueError("Invalid Waveshare firmware package / 微雪固件包大小不正确")
    magic, size, checksum = FW_HEADER.unpack_from(data)
    payload = data[FW_HEADER.size:-64]
    if magic != b"RIOT1131" or len(payload) != size or zlib.crc32(payload) != checksum:
        raise ValueError("Invalid Waveshare firmware package / 微雪固件包校验失败")
    return data, checksum


def firmware_exchange(transport, request, body=b"", *, timeout=3):
    transport._request(request, body)
    response = transport.read(0x82, FW_REPLY.size, timeout=timeout)
    magic, version, command, status, checksum, trial = FW_REPLY.unpack(response)
    if (magic, version, command) != (b"RIOF", 1, request) or trial not in (0, 1):
        raise OSError("Invalid Waveshare upgrade reply / 微雪固件回执异常")
    if status:
        raise ValueError("Waveshare rejected the firmware operation / 微雪屏拒绝固件更新")
    return checksum, bool(trial)


def install_firmware(path, package, paths, progress, *, open_link=None):
    if not is_t113_update_path(path) or paths() != [path]:
        raise RuntimeError("Connect one USB-update-enabled Waveshare screen / 请只连接一块支持 USB 更新的微雪屏")

    def link():
        connection = CdcTransport((open_link or open_t113_serial)(path))
        connection.reset_pipes()
        return closing(connection)

    data, expected = package
    with link() as port:
        before, trial = firmware_exchange(port, FW_INFO)
        if before == expected:
            if trial:
                firmware_exchange(port, FW_CONFIRM, struct.pack("<I", expected))
                if firmware_exchange(port, FW_INFO) != (expected, False):
                    raise OSError("Waveshare did not confirm the running firmware / 微雪屏未确认当前固件")
            return {"before_crc32": before, "after_crc32": expected, "already_current": not trial}
        if trial or before not in WAVESHARE_REPLACES:
            return {"before_crc32": before, "after_crc32": before, "skipped": True}
        firmware_exchange(port, FW_BEGIN, struct.pack("<I", len(data)))
        for offset in range(0, len(data), CHUNK_LIMIT):
            part = data[offset:offset + CHUNK_LIMIT]
            firmware_exchange(port, FW_DATA, part)
            progress((offset + len(part)) / len(data) * .9)
        try:
            firmware_exchange(port, FW_APPLY, timeout=15)
        except OSError:
            # The endpoint can disappear as the screen reboots. Verify its running bytes.
            pass
    progress(.95)
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        time.sleep(.35)
        try:
            if paths() != [path]:
                continue
            with link() as port:
                current, trial = firmware_exchange(port, FW_INFO)
                if current != expected:
                    continue
                if trial:
                    firmware_exchange(port, FW_CONFIRM, struct.pack("<I", expected))
                if firmware_exchange(port, FW_INFO) == (expected, False):
                    return {"before_crc32": before, "after_crc32": current, "already_current": False}
        except (OSError, ValueError):
            continue
    raise TimeoutError("Waveshare did not confirm the upgraded firmware / 微雪屏未确认新版固件")


class T113Protocol(LT168BBenchProtocol):
    capabilities = T113

    def __init__(self, qualified_path, open_link=None, session_factory=None):
        self.qualified_path = qualified_path
        self.capabilities = t113_capabilities(qualified_path)
        if open_link is None:
            open_link = open_t113_serial
        super().__init__(lambda path: CdcTransport(open_link(path)), session_factory)

    def open(self, path):
        if not path or path != self.qualified_path:
            raise UnsupportedDisplay("RIO T113 requires its verified USB serial endpoint")
        self.close()
        self.transport = self.transport_factory(path)

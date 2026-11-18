"""Install the released two-region eM133-V3 package through the RIO updater."""
import hashlib
import io
import json
import struct
import time
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

BOARD = "LT168B eM133-V3"
ORIGIN = 0x6000A000
SECTOR = 4096
CHUNK = 2048
LOW_END = 12288
BANK = 0x600A0000 - ORIGIN
BANK_END = 0x601ED000 - ORIGIN
END_GUARD = BANK_END + SECTOR
MANIFEST_SHA = "9fbdb13d747ed8577ed5571228ddaa64244d57109392e19e11043d60c7055d5f"
ARCHIVE_SHA = "d5c977a398268fb6d58d5806d3dabd0035929d289c8f356adbe8abd030a991b9"
LOADER = (0x23121401, 0xEEBA0081)
# This board's saved, pre-installation physical prefix checks also identify its
# populated gap and the sector after the bank. Never derive these from a ZIP.
CURRENT = {LOW_END: 1555631094, LOW_END + SECTOR: 2261009566, BANK: 2178131575,
           BANK_END: 275860302, END_GUARD: 2410230234}
IDENTIFY = bytes.fromhex("4b304c5468245713a5d228bce81700007f003000f60bb95c000000000000000082416bd500000000000000000000000000000000000000000000000000000000")
IDENTITY_REPLY = (2051279312, 3156791973, *LOADER)

# Exact [start, end) pairs observed in the qualified physical update records.
# The bootloader identity, range, and first following guard are bound to the
# record. Neither the external ZIP nor any CLI option can add an erase window.
ERASE_RECORDS = {
    LOADER: {(0, LOW_END): "1272e43761a2ca5aed4bd00c89a81ba7fdf49b1e78af31ea343c60f0e82a995a"},
}
GAP_ENDS = tuple(range(LOW_END + SECTOR, BANK + 1, SECTOR))
BANK_ENDS = (*range(BANK + 65536, BANK_END, 65536), BANK_END)
ENDS = (LOW_END, *GAP_ENDS, *BANK_ENDS, END_GUARD)
BLANK = b"\xff" * (BANK_END - BANK)


@dataclass(frozen=True)
class Image:
    offset: int
    data: bytes

    @property
    def window(self):
        return self.offset, self.offset + len(self.data)


@dataclass(frozen=True)
class Package:
    application: Image
    animation: Image
    previous: bytes

    def describe(self):
        return dict(board=BOARD, archive_sha256=ARCHIVE_SHA, manifest_sha256=MANIFEST_SHA,
                    sector_bytes=SECTOR, protected_bytes=BANK - LOW_END,
                    protected_sectors=len(GAP_ENDS),
                    protected_range=[hex(ORIGIN + LOW_END), hex(ORIGIN + BANK)],
                    installation_order=[{"begin": hex(ORIGIN + image.offset),
                                         "end_exclusive": hex(ORIGIN + image.window[1]),
                                         "bytes": len(image.data),
                                         "sha256": hashlib.sha256(image.data).hexdigest()}
                                        for image in (self.animation, self.application)])


def checked_member(archive, name, size):
    info = archive.getinfo(name)
    if info.file_size != size or info.flag_bits & 1:
        raise ValueError("Invalid package member: " + name)
    return archive.read(info)


def load_package(path):
    # Read once into bounded immutable storage. Only the reviewed release can
    # select firmware. Nothing from the ZIP is extracted to the filesystem.
    with Path(path).open("rb") as src:
        blob = src.read(4 * 1024 * 1024 + 1)
    if len(blob) > 4 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Segmented firmware package checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate firmware package member")
        raw = archive.read("manifest.json")
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
            raise ValueError("Unknown segmented firmware manifest")
        manifest = json.loads(raw)
        gap = [int(n, 16) - ORIGIN for n in manifest["untouched_gap"]]
        if (manifest["board"] != BOARD or manifest["firmware_region_sector_bytes"] != SECTOR
                or gap != [LOW_END, BANK] or len(manifest["images"]) != 2):
            raise ValueError("Wrong segmented screen or protected gap")

        def image(record, window):
            start, end = (int(record[k], 16) - ORIGIN for k in ("start_inclusive", "end_exclusive"))
            if (start, end) != window or record["bytes"] != end - start or start % SECTOR or end % SECTOR:
                raise ValueError("Invalid firmware erase window")
            data = checked_member(archive, record["file"], end - start)
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Firmware image digest mismatch")
            return Image(start, data)

        app = image(manifest["images"][0], (0, LOW_END))
        art = image(manifest["images"][1], (BANK, BANK_END))
        old = image(manifest["recovery"], (0, LOW_END))
        if hashlib.sha256(old.data).hexdigest() != manifest["required_previous_application_sha256"]:
            raise ValueError("Invalid recovery application")
        return Package(app, art, old.data)


def crc(data, previous=0):
    return zlib.crc32(data, previous ^ 0xFFFFFFFF) ^ 0xFFFFFFFF


def tail_crc(before, after, count):
    """Independent CRC of a suffix given raw CRCs of two cumulative prefixes."""
    return after ^ crc(bytes(count), before)


def signatures(prefixes):
    bounds = (LOW_END, *GAP_ENDS)
    gap = [tail_crc(prefixes[a], prefixes[b], b - a) for a, b in zip(bounds, bounds[1:])]
    return gap, tail_crc(prefixes[BANK_END], prefixes[END_GUARD], SECTOR)


def expected_prefixes(original, previous, app, bank_data):
    """Replace just the two images, carrying the measured intervening data."""
    old_crc, new_crc = crc(previous), crc(app)
    expected = {LOW_END: new_crc}
    for end in GAP_ENDS:
        expected[end] = original[end] ^ crc(bytes(end - LOW_END), old_crc ^ new_crc)
    last = BANK
    checksum = expected[BANK]
    for end in BANK_ENDS:
        checksum = crc(bank_data[last - BANK:end - BANK], checksum)
        expected[end] = checksum
        last = end
    expected[END_GUARD] = original[END_GUARD] ^ crc(bytes(SECTOR), original[BANK_END] ^ checksum)
    return expected


class EraseScopeUnknown(RuntimeError):
    pass


def verify_snapshot(actual, expected):
    for end in ENDS:
        if actual[end] != expected[end]:
            raise OSError("Flash checksum mismatch at exclusive end 0x%08x" % (ORIGIN + end))


def update(device, package, install, record, progress=lambda value: None):
    loader = device.identify()
    record(dict(stage="identified", version=hex(loader[0]), kind=hex(loader[1])))
    if loader != LOADER:
        raise ValueError("Unrecognized screen bootloader")

    def snapshot(stage):
        values = {end: device.checksum(end) for end in ENDS}
        gap, guard = signatures(values)
        record(dict(stage=stage, application_crc=values[LOW_END], bank_start_crc=values[BANK],
                    bank_end_crc=values[BANK_END], next_sector_crc=guard,
                    gap_crc=tail_crc(values[LOW_END], values[BANK], BANK - LOW_END),
                    gap_sector_crcs=gap, bank_prefix_crcs=[values[n] for n in BANK_ENDS]))
        return values

    current = snapshot("preflight")
    app_crc = current[LOW_END]
    if app_crc not in (crc(package.previous), crc(package.application.data)):
        raise ValueError("Unrecognized installed application")
    # Recover the saved application's prefix contribution without reading
    # any protected data. This also recognizes a fully completed bank after
    # a lost connection. A partially written bank is never automatically replayed.
    before = dict(current)
    before[LOW_END] = crc(package.previous)
    for end in GAP_ENDS:
        before[end] ^= crc(bytes(end - LOW_END), app_crc ^ before[LOW_END])
    for end in (LOW_END, LOW_END + SECTOR, BANK):
        if before[end] != CURRENT[end]:
            raise ValueError("Protected area differs from this board's saved checksum")
    before[BANK_END] = CURRENT[BANK_END]
    before[END_GUARD] = CURRENT[END_GUARD]
    installed_app = package.previous if app_crc == before[LOW_END] else package.application.data
    empty = expected_prefixes(before, package.previous, installed_app, BLANK)
    staged = expected_prefixes(before, package.previous, installed_app, package.animation.data)
    if all(current[n] == empty[n] for n in BANK_ENDS) and installed_app == package.previous:
        verify_snapshot(current, empty)
        order = (package.animation, package.application)
    else:
        verify_snapshot(current, staged)
        order = (package.application,) if installed_app == package.previous else ()
    if not order:
        device.run()
        record(dict(stage="installed_application_start_sent"))
        return "already_installed_and_verified"
    missing = [image.window for image in order if image.window not in ERASE_RECORDS.get(loader, {})]
    record(dict(stage="erase_scope", qualified=not missing, missing_windows=[
        [hex(ORIGIN + start), hex(ORIGIN + end)] for start, end in missing]))
    if not install or missing:
        # The trusted original application and both guards are intact. Exit the
        # temporary boot mode, even when a requested installation was declined.
        device.run()
        record(dict(stage="previous_application_start_sent"))
        if missing and install:
            raise EraseScopeUnknown("No physical erase-boundary record for the animation bank; existing application started")
        return "device_checked_scope_unproven" if missing else "device_checked_scope_qualified"

    # Both windows were checked before the first mutating command. Activate the
    # new application only after every bank block and protected sector passes.
    for step, image in enumerate(order):
        record(dict(stage="writing", offset=image.offset, length=len(image.data),
                    physical_record=ERASE_RECORDS[loader][image.window]))
        def acknowledged(count):
            progress((step + count / len(image.data)) / len(order))
            if count % 65536 == 0 or count == len(image.data):
                record(dict(stage="blocks_acknowledged", start=image.offset, bytes=count))
        device.write_image(image, acknowledged)
        low = package.previous if image is package.animation else package.application.data
        expected = expected_prefixes(before, package.previous, low, package.animation.data)
        verify_snapshot(snapshot("after_animation" if image is package.animation else "after_application"), expected)
    device.run()
    record(dict(stage="new_application_start_sent"))
    return "segments_verified_and_started"


class RioLoader:
    """RIO's CDC update transport restricted to the release's two exact images."""
    def __init__(self, port):
        self.port = port
        self.loader = None
        self.counts = dict(identify=0, checksums=0, program_mode=0, begin_range=0,
                           block_attempts=0, payload_bytes_attempted=0,
                           payload_bytes_acknowledged=0, application_start=0)

    def send(self, packet):
        if self.port.in_waiting:
            raise OSError("Unexpected pending bootloader data")
        operations = {0x4B: "identify" if packet[1] == 0x30 else "program_mode",
                      0x4E: "checksums", 0x4C: "begin_range", 0x4A: "block_attempts", 0x4F: "application_start"}
        self.counts[operations[packet[0]]] += 1
        if packet[0] == 0x4A:
            self.counts["payload_bytes_attempted"] += len(packet) - 12
        if self.port.write(packet) != len(packet):
            raise OSError("Short bootloader write")

    def exchange(self, packet):
        self.send(packet)
        reply = bytearray()
        deadline = time.monotonic() + 18
        while len(reply) < 63 and time.monotonic() < deadline:
            reply.extend(self.port.read(63 - len(reply)))
        if len(reply) != 63 or reply[0] != packet[0]:
            raise OSError("Invalid bootloader response")
        return reply

    def identify(self):
        fields = struct.unpack_from("<4I", self.exchange(IDENTIFY), 1)
        if fields != IDENTITY_REPLY:
            raise ValueError("Bootloader identity mismatch")
        self.loader = fields[2:]
        return self.loader

    def checksum(self, end):
        if end not in ENDS or self.loader != LOADER:
            raise ValueError("Unexpected checksum boundary or bootloader")
        packet = bytearray(64)
        packet[0] = 0x4E
        struct.pack_into("<I", packet, 4, end)
        struct.pack_into("<I", packet, 16, crc(packet[:16]))
        value, length = struct.unpack_from("<II", self.exchange(packet), 1)
        if length != end:
            raise OSError("Bootloader returned a different checksum length")
        return value

    def write_image(self, image, acknowledged):
        if image.window not in ERASE_RECORDS.get(self.loader, {}):
            raise EraseScopeUnknown("Unqualified flash erase window")
        # Pin content again at the wire boundary. The legacy begin_range
        # fields are relative to the application origin.
        from .firmware_release import BANK_SHA, HELPER_SHA, PLAYER_SHA
        expected_hashes = {(0, LOW_END): (PLAYER_SHA, HELPER_SHA),
                           (BANK, BANK_END): (BANK_SHA,)}
        if hashlib.sha256(image.data).hexdigest() not in expected_hashes.get(image.window, ()):
            raise ValueError("Unrecognized segment payload")
        length = len(image.data)
        mode = bytearray(IDENTIFY)
        mode[1] = 0x31
        struct.pack_into("<I", mode, 8, 0x1971168B)
        identity_crc = crc(mode[:12] + b"POTL")
        echo_crc = crc(mode[:12])
        struct.pack_into("<I", mode, 8, echo_crc)
        mode[17:20] = length.to_bytes(3, "little")
        struct.pack_into("<I", mode, 20, crc(image.data))
        struct.pack_into("<I", mode, 32, crc(mode[:32]))
        if struct.unpack_from("<4I", self.exchange(mode), 1) != (identity_crc, echo_crc, *self.loader):
            raise OSError("Programming mode identity mismatch")

        begin = bytearray(64)
        begin[0] = 0x4C
        struct.pack_into("<II", begin, 1, image.offset, length)
        struct.pack_into("<I", begin, 9, crc(begin[:9]))
        if self.exchange(begin)[1] != 0:
            raise OSError("Flash range rejected")
        for index in range(0, length, CHUNK):
            offset = image.offset + index
            block = struct.pack("<BBIH", 0x4A, 0x30, offset, CHUNK) + image.data[index:index + CHUNK]
            reply = self.exchange(block + struct.pack("<I", crc(block)))
            if reply[1] or struct.unpack_from("<I", reply, 2)[0] != offset:
                raise OSError("Incorrect flash block ACK at 0x%08x" % (ORIGIN + offset))
            self.counts["payload_bytes_acknowledged"] += CHUNK
            acknowledged(index + CHUNK)

    def run(self):
        self.send(b"\x4f" + bytes(63))
        self.port.flush()

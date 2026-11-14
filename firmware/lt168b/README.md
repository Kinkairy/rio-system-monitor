# LT168B receiver — rc0.1.20 baseline

Current accepted eM133-V3 baseline: 30780997a3baf2d0002462443c3922f4d54997f1b6e7929c8e80b15a15883a9a (12 KiB padded image). Owner confirmed normal display and music entry/exit after restoration, then designated rc0.1.20 as the sole monitor baseline. Normal RIO host rendering and animation are unchanged.

This source includes the accepted USB receiver, dirty-area copy and large-frame decode-once implementation. Failed later USB double-buffer candidates are excluded. The board retains one frame in flight; remaining transition stalls/tearing are not declared solved. The FFFF:168B identity remains a private bench identifier, not an allocated production VID/PID.

See [recovery](../../docs/recovery.md) for current inputs and restoration boundaries. Historical qualification notes below describe earlier experiments, not current approval or current recovery authority.

## Architecture

Existing RIO renderer → existing RGB565 encoder → existing `ScreenOutput`
with explicit `LT168BBenchProtocol` → WinUSB bulk → `rio_stream` → RGB RAM.
No second collector, UI or monitor implementation. No Fangcun changes.
The adapter is deliberately absent from automatic discovery until qualified.

Device identity FFFF:168B is an **unallocated private bench placeholder**, not
a production VID/PID allocation. One vendor interface, EP01 OUT and EP82 IN,
64-byte full-speed bulk packets; Microsoft OS 1.0 WinUSB descriptors supplied.
The bench WinUSB profile must be explicitly selected. Default legacy identity,
endpoints, discovery and protocol remain unchanged.

Capability request: bmRequestType=C1, bRequest=52, value/index=0, length=32.
Reply `<4sHHHHHHIIII>`: RIO1, version1, length32, 480,480,32,16,
flags1, maximum packet1048, framebuffer bytes460800, CRC32 of first28 bytes.
Flag1 defines big-endian RGB565 input, progressive tiles, one frame in flight.
Only after validating this exact capability reply may the host reset the stream
(41/53, value/index/length=0) and send pixels. Reset discards pending USB buffers,
parser state, frame count and baseline. No arbitrary vendor/control commands.

Pixel packet format is documented in `rio_stream.h` and `lt168b_stream.py`.
An END acknowledgement is 24 bytes `<4sHHIIII>`: RIOA, version1, status,
session, frame, completed-frame count, CRC32 of first20 bytes. Status0 is success,
status1 rejects. Only a matching success ACK advances the host baseline.
Any uncertain I/O invalidates the session; no automatic transfer replay.
The next initialized connection resets and sends a complete keyframe.

## Building

Canonical sources and native tests stay on NUC. The owner approved official
Windows compiler iterations only for this adaptation. Export a fixed snapshot
of this directory, then run `build.py --sdk <MCU SDK root> --toolchain <ccore-elf>
--output <new artifact directory>` using Python on Windows. It never opens USB.

External official inputs, excluded from Git:

- LT168B_MCU_SDK.rar: `User/startup.s`, `User/vector_table.c`,
  `MCU_drv/lt168_clock.c` and their original headers. Preserve vendor notices.
- CCore IDE setup_CCore_20180222.exe, extracted without installing the IDE:
  `app/tool-chain/ccore-elf` and the DLLs in `app/tool-chain/bin`.
  The latter directory is required by cc1, even when gcc --version works.
  Build script adds it to its subprocess PATH, not the system PATH.
- Use ASCII build-input paths; stage the SDK under an ASCII directory.

Output: ELF, BIN, linker map, section/size reports, build log, SHA256 input/output
manifest. Old compiler uses little-endian CCore C0 code. Vendor clock source has
an existing unused-variable warning and SCI header has an existing comment
warning; project C sources compile without warnings.

Linker checks reserve RAM 00800800..0083FFFF, framebuffer 00840000..008B07FF
(460800 bytes), and at least8KiB stack headroom. Application starts6000A000, verified by the recovered stock VBR setup and
the first scoped12KiB application write/readback.
Framebuffer is NOLOAD and must not be included in downloaded program bytes.
Board startup fills a blue/green checkerboard before accepting RIO frames.

## Verification and qualification gaps

NUC native C tests check bounds, malformed/fragmented packets, CRC, sessions,
missing/duplicate tiles and recovery. Adapter tests pass actual RIO RGB565
frames through native C at64-byte USB boundaries, inspect every pixel, check
USB/WinUSB descriptor lengths and ACK metadata, and exercise the existing
ScreenOutput worker. They do **not** emulate the USB controller, RGB peripheral
or physical panel. First native WinUSB enumeration and32-byte capability read
passed. Single buffering may visibly tear and needs physical evaluation.

## Actual board result and pending correction

Bottom-button power-on reaches native CDC EEEF:268A/COM6. Stock startup proves
app VBR6000A000. Exact recovered219-event panel sequence drives GPIO0 bits0..3;
stock RGB uses CLK_POL1/DIV6 and480x480 timing. No unidentified pad shorting.

Owner-authorized first12KiB flash57c5e5e0 passed write/CRC and next-sector guard;
WinUSB HELLO succeeded. Owner reported BLACK SCREEN. No full RIO frame sent.
This candidate is a failed physical test, not a qualified display release.

Read-only diagnosis found omitted stock60040340 backlight initialization:
PWM1 channel3, CSR3=2, CP1=0, continuous mode, output enabled, normal polarity.
`board_backlight.c` reproduces the recovered register masks/order. Stock period
was selected from runtime settings and is unknown; bench period1024 and stock
compare525 give roughly half duty. Native tests check the MMIO sequence and
preservation of unrelated channels. It runs after RGB initialization. A new
exact candidate/12KiB plan requires new one-shot approval before writing;
no automatic retry. Physical checkerboard then full RIO MAIN and sustained
updates remain outstanding. Do not infer LCD success from USB/protocol tests.

Original first12KiB backup SHA256:
`0ee16305f4965822abb4143e7f90a031467445cf9aa6fe5606d3cc3b3da513f2`.
This is scoped recovery only, not a full firmware backup; original restoration
is untested. Preserve bootloader/theme. No driver installation or installed RIO
replacement is performed by this code or build script. Detailed chronology and
artifact paths remain in root README / RIO-SCREEN-COMPAT-20261113.


### Read-only storage qualification candidate (2026-11-14)

Explicit configured-interface vendor IN54 (value0=JEDEC9F,1=SFDP5A,2=NOR-header03; index=offset0..4095; length64) is diagnostic only. No startup access or stored-media support. QSPI1 per official SDK exFlash mapping; QSPI0 program and QSPI2 memory untouched. Reply RISP/version1/op/status16/offset16/count16/bus1/reserved3/data44/CRC32; fields little endian, unused bytes zero. One polling budget, no retries, controller/clock/CS restored on timeout. No flash write or mode-switch opcode exists in this module. Host stops after unqualified ID or SFDP and never interprets raw density as free media space.

Run python -m rio_monitor.lt168b_storage_probe --journal NEW.json only with separately approved probe firmware and RIO closed; shared process mutex enforces ownership. Existing auto-upgrade package remains the previously accepted fd2ec0ca. Probe code/native tests do not establish physical capacity or upload/playback. Candidate application-only12KiB and explicit execution/recovery plans are private artifacts, not shipped by this change.

Bundled local video converter

The current RIO slim trial uses unmodified upstream FFmpeg 6.1.1, built for
Windows x64 with the existing conversion command unchanged. It keeps native
video decoders, decoder-only libaom AV1, zlib, local file/pipe input, the existing
input containers, GIF output, and the required video filters. SIMD/assembly and
runtime CPU detection remain enabled; size-over-speed optimization is disabled.
Unused audio/subtitle decoding, video/audio encoding, network, devices, and
hardware-acceleration backends are excluded. Only the GIF encoder is enabled.

RIO slim trial:
SHA-256: 5c342ee11ed7d24b1fe55fd4a3df06afa6e52f95af78674d5156b5db2ccee221
Size: 15030784 bytes.
Build configuration/version: FFMPEG-SLIM-LICENSE-NOTICE.txt.
libaom license/patent grant and zlib license: AOM-LICENSE.txt, AOM-PATENTS.txt,
ZLIB-LICENSE.txt. FFmpeg remains GPLv3; see COPYING.GPLv3.

The previous FFmpeg 6.1.1 essentials Windows x64 static GPLv3 build by gyan.dev
remains accepted for existing/recovery builds:
SHA-256: 04e1307997530f9cf2fe35cba2ca7e8875ca91da02f89d6c7243df819c94ad00
Its original build notice remains in FFMPEG-LICENSE-NOTICE.txt.
Provider: https://www.gyan.dev/ffmpeg/builds/

The importer accepts only these pinned converters and copies the notices into
the local ignored assets/media directory. The app invokes FFmpeg as a separate
local process and does not link its libraries. No component installer runs.

Rebuilding the slim variant
--------------------------
Use the existing Linux C builder with gcc, make, cmake, ninja, perl and
pkg-config. Extract these upstream archives beneath a work directory's sources/
folder. Do not store sources, toolchains or outputs in the program source Git.

FFmpeg n6.1.1:
https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n6.1.1
SHA-256: 7c1ebea95d815e49c1e60c7ee816410dec73a81b8ac002b276780d2f9048e598
libaom 3.8.2:
https://storage.googleapis.com/aom-releases/libaom-3.8.2.tar.gz
SHA-256: 98f7d6d7ddbf06d088735f5e51782df053fd1b08c553882c2924bd0b2021a202
zlib 1.3.1:
https://zlib.net/fossils/zlib-1.3.1.tar.gz
SHA-256: 9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23
NASM 2.16.03 (build tool):
https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/nasm-2.16.03.tar.xz
SHA-256: 1412a1c760bbd05db026b6c0d1657affd6631cd0a63cddb6f73cc6d4aa616148
llvm-mingw 20240619 UCRT Ubuntu 20.04 x86_64 (build tool):
https://github.com/mstorsjo/llvm-mingw/releases/download/20240619/llvm-mingw-20240619-ucrt-ubuntu-20.04-x86_64.tar.xz
SHA-256: 27d33157cc252c29ad6f777a96a0d94176fea1b534ff09b5071485def143b90e

Run tools/build_ffmpeg_slim.sh <work-directory> (JOBS defaults to 4).
Pass <work-directory>/out/ffmpeg.exe to the existing private-asset importer's
--ffmpeg argument. A rebuild's paths/toolchain can affect its hash; the hashes
above identify the exact tested inputs and converter, not arbitrary rebuilds.

The existing two media tests generate H.264 inputs using a full FFmpeg.
When testing a slim bundle, set RIO_TEST_FFMPEG_GENERATOR to a full FFmpeg path;
the conversion under test still uses the bundled slim binary.

Upstream source: https://github.com/FFmpeg/FFmpeg/tree/n6.1.1
Complete program EXEs may be published through the existing GitHub Releases
channel when authorized. Original artwork remains private; no binary or build
toolchain is added to the source repository by this trial.

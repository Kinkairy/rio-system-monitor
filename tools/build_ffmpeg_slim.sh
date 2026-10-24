#!/usr/bin/env bash
# Rebuild the RIO Windows converter from the pinned sources listed in the FFmpeg README.
# Usage: build_ffmpeg_slim.sh <work-directory-containing-sources>
set -euo pipefail
work=$(cd "${1:?work directory required}" && pwd)
sources="$work/sources"
prefix="$work/prefix"
jobs=${JOBS:-4}
export PATH="$work/host/bin:$sources/llvm-mingw-20240619-ucrt-ubuntu-20.04-x86_64/bin:$PATH"
mkdir -p "$work/build" "$work/out" "$prefix"

if [[ ! -x "$work/host/bin/nasm" ]]; then
    cd "$sources/nasm-2.16.03"
    CC=/usr/bin/gcc ./configure --prefix="$work/host"
    make -j"$jobs"
    make install
fi

cd "$sources/zlib-1.3.1"
CHOST=x86_64-w64-mingw32 CC=x86_64-w64-mingw32-gcc ./configure --static --prefix="$prefix"
make -j"$jobs"
make install

cmake -S "$sources/libaom-3.8.2" -B "$work/build/aom" -G Ninja \
    -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_SYSTEM_PROCESSOR=x86_64 \
    -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc \
    -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++ \
    -DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DAOM_TARGET_CPU=x86_64 -DCONFIG_AV1_ENCODER=0 -DCONFIG_AV1_DECODER=1 \
    -DENABLE_TESTS=0 -DENABLE_EXAMPLES=0 -DENABLE_TOOLS=0 -DENABLE_DOCS=0 \
    -DENABLE_NASM=ON -DBUILD_SHARED_LIBS=OFF
cmake --build "$work/build/aom" -j"$jobs"
cmake --install "$work/build/aom"

# Keep the native video group, excluding its legacy audio entries, plus the
# five video codecs registered later; libaom supplies software AV1 decoding.
ffsource="$sources/FFmpeg-n6.1.1"
video_decoders=$(sed '/\/\* audio codecs \*\//,$d' "$ffsource/libavcodec/allcodecs.c" |
    sed -n 's/^extern const FFCodec ff_\([a-zA-Z0-9_]*\)_decoder;.*/\1/p' |
    grep -Ev '^(comfortnoise|dvaudio|eightsvx_exp|eightsvx_fib|rka|s302m|speex)$' | paste -sd, -)
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
mkdir -p "$work/build/ffmpeg"
cd "$work/build/ffmpeg"
"$ffsource/configure" \
    --prefix="$prefix" --arch=x86_64 --target-os=mingw32 --enable-cross-compile \
    --cross-prefix=x86_64-w64-mingw32- \
    --cc=x86_64-w64-mingw32-gcc --cxx=x86_64-w64-mingw32-g++ \
    --enable-gpl --enable-version3 --enable-static --disable-shared \
    --disable-autodetect --disable-debug --disable-doc --disable-ffplay --disable-ffprobe \
    --disable-avdevice --disable-postproc --disable-swresample \
    --disable-network --disable-protocols --enable-protocol=file,pipe \
    --disable-decoders --enable-decoder="$video_decoders,bintext,hdr,idf,vnull,xbin,libaom_av1" \
    --disable-encoders --enable-encoder=gif \
    --disable-muxers --enable-muxer=gif \
    --disable-demuxers --enable-demuxer=mov,matroska,avi,asf,mpegps,mpegts,flv,gif,apng,webp_pipe \
    --disable-filters --enable-filter=fps,scale,pad,setsar,split,palettegen,paletteuse \
    --disable-hwaccels --disable-d3d11va --disable-dxva2 \
    --enable-libaom --enable-zlib --pkg-config=pkg-config --pkg-config-flags=--static \
    --extra-cflags="-I$prefix/include" --extra-ldflags="-L$prefix/lib -static"
make -j"$jobs" ffmpeg.exe
cp ffmpeg.exe "$work/out/ffmpeg.exe"
sha256sum "$work/out/ffmpeg.exe"

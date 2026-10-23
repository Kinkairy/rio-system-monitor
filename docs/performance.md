# Rendering efficiency checks

## 2026-10-23: unchanged-layout cache pass

Compared against cleanup commit `50f6195fc0b2e54e03fb9bfddc5adf1735db593b`.

- Cache the dim temperature gauge rather than rebuilding its pixel lookup result each frame.
- Cache the robot's fixed grid plate as a 133×133 tile, preserving the inclusive ellipse boundary.
- Create a GPU history chart only when its identifier first appears.
- Reuse the FFT Hann window, normalization and frequency-band masks for the current buffer length and sample rate. Keep only one plan; rebuild on either change.
- Compute current lyric layout/state once per rendered music frame.

No changes to approved artwork, animation timing, sample values, USB protocol, driver installation or persistent screen writes.

### Local checks

Linux cloud machine, same process and private assets, before/after renderers interleaved. Fixed wall time and seeded robot/sheen random sources; 90 monitor frames at 30 Hz including a GPU chart and a temperature transition to missing data. Warm-up: first 10 frames excluded from timing statistics. Output: 480×480.

| Check | Before | After |
| --- | ---: | ---: |
| Median monitor render duration | 42.623 ms | 34.725 ms |
| Median FFT analysis duration | 0.281 ms | 0.182 ms |

All 90 monitor outputs were pixel-identical. All 60 music outputs, including a track transition, were pixel-identical. FFT outputs matched exactly for 200 generated stereo buffers across 1024/2048/4096-sample input sizes. These are focused checks, not exhaustive visual coverage or a Windows/USB benchmark. Timing depends on the host and load; do not infer physical-screen FPS from it.

The local aggregate run discovered 156 tests: 139 passed, 16 skipped, and one existing Windows registry test could not run on Linux (`winreg` unavailable). The same registry limitation was present before changes. Windows CI is the separate platform check; private-art tests remain explicitly skipped there.

### Still to measure

Adaptive rendering when the settings window is hidden, temperature-history layer caching, and combining record layers before rotation remain future candidates. Do not reduce the preview's smoothness, change sampling semantics or alter USB acknowledgement/ownership guarantees without dedicated checks.

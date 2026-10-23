# Rendering efficiency checks

## PERF-20261023-CPU-MEMORY: CPU and memory follow-up

Owner request: reduce CPU and memory usage without unnecessary redesign. Base: `9379afadd50367d9426439d30d5f30516c3d150a`; the clean local checkout and previously delivered executable remain recoverable.

Planned scope: when the settings preview is hidden, render only when the existing latest-frame output queue has room. Keep the visible preview at its configured rate. Crop temperature-gauge buffers to their actual mask bounds and release the robot atlas after extracting its frames. Preserve pixels, time-based animation, sampling, USB commands and resource-write ownership.

Acceptance: compare frames against the exact base, exercise pending-output/visible-preview behavior, measure CPU and private memory in matching processes, run existing tests and the packaged startup check, and inspect the final diff. No source publication or replacement of the running application is included. AMF `project_show(rio-system-monitor)` returned `not_found`; this entry records the authorized local change, not a successful AMF registration.

### Results

Implemented only the planned scope. The gauge buffers now cover the mask's 1115×549 bounds instead of 1254×1254, and missing-temperature frames reuse the immutable dim gauge. The atlas is no longer retained after its 62 frames are extracted. Hidden rendering checks the existing one-frame queue; visible rendering keeps the configured rate.

Windows/Python 3.12.10/Pillow 11.3.0 comparison against the exact base: 120 frames were byte-identical, including 0/58/100/missing temperature, rolling digits, history, animation and sheen. Alternating-order median render time was 24.656 ms before and 18.546 ms after (24.8% lower). The existing suite plus one queue-demand regression passed: 157 tests, no skips, 17.796 seconds. Final source diff covers five production modules, two affected test files and this document.

Separate processes measured the real renderer, RGB565 encoder and output queue with a simulated sender taking 1/13 second per transfer. Each process warmed up for three seconds and was measured for eight seconds. This is a bounded render/output benchmark, not whole-application resource use or physical USB acceptance.

| Mode | CPU before/after (% of one logical CPU) | Private memory before/after | Render FPS before/after | Sent FPS before/after |
| --- | --- | --- | --- | --- |
| Preview visible | 81.25 / 65.57 | 66.82 / 55.07 MiB | 28.88 / 30.13 | 12.50 / 12.58 |
| Preview hidden | 84.94 / 28.96 | 66.45 / 55.21 MiB | 29.18 / 12.52 | 12.53 / 12.52 |

The hidden pipeline used 65.9% less CPU and 11.23 MiB less private memory while maintaining simulated output throughput. Visible-pipeline CPU fell 19.3% and private memory fell 11.75 MiB. Actual application savings depend on settings, device throughput and the other running components. No memory-leak or long-duration stability claim is made from this short measurement.

The Windows build and packaged self-test passed (exit 0, empty stderr, all assertions true); the captured settings window was visually checked. Delivered locally as `RIO-System-Monitor-9379afa-efficient.exe` (108646981 bytes), SHA-256 `b1d6f62478f082b79e330317f9a7f167ce402135b1356097436974485e9ad431`. Download copy matched the built executable. At this initial delivery, source changes remained local and the running application was not replaced. Physical device/user acceptance remains pending.

### Source submission

On 2026-10-23 the owner subsequently authorized committing and pushing this verified change to the public repository. The remote `main` still pointed to the exact base above. Submission scope is the five production modules, two affected test files and this performance document; the executable and private assets remain local. No production code changed after the recorded tests and build.

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

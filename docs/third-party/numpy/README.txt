RIO NumPy slim component: ROUND-SCREEN-NUMPY-SLIM-20261024

Same NumPy 2.5.4 array/PocketFFT implementation, no external BLAS/LAPACK.
Upstream sources are not patched. Unused matrix operations use upstream fallback.

Source: https://pypi.org/project/numpy/2.5.4/
Archive: numpy-2.5.4.tar.gz, 20866315 bytes
SHA256: 9a94cf751c9ad8ebaa835bcd3d40dacf8534ad086b88c38029b65123c7999d2a

Recipe: tools/Build-NumPySlim.ps1; Python 3.12, meson-python and Cython.
Compiler: Microsoft MSVC 19.44.35229 (VC Tools 14.44.35207 layout).
Windows SDK: 10.0.26100.0. Compiler matches the original NumPy wheel.
Official Microsoft VS2022 package catalog and signed compiler were used.
The compiler/SDK are build inputs, not distributed with the application.
CPU feature sets match original: baseline X86_V2, dispatch X86_V3.
No native-only CPU target, disabled SIMD or disabled threading.
BLAS/LAPACK: none; allow-noblas=true; buildtype=release; b_lto=true. Ninja compilation uses one job.

Upstream license-files are retained at their original relative paths.
The local wheel/runtime and full source/toolchain/logs remain outside Git.
Build once and reuse runtime for EXE builds; original venv stays intact.
End users do not need to install a compiler or NumPy.
Final result/validation: same root README change record.

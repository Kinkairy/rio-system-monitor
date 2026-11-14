# Current monitor recovery baseline

The owner designated **rc0.1.20** as the sole RIO monitor baseline on 2026-11-14. This designation applies to the monitor only; independent modules, Mini, Plus and NDSL retain their own baselines. Older Git tags and the root decision ledger remain historical evidence, not alternate active baselines.

- Main source: public tag `rc0.1.20` and the corresponding private monitor source commit.
- Firmware: `30780997a3baf2d0002462443c3922f4d54997f1b6e7929c8e80b15a15883a9a`, 12288 bytes, app range `0x6000a000..0x6000d000` exclusive. No bootloader, theme or other sectors are overwritten.
- The accepted firmware code image is 11876 bytes, SHA-256 `34b50eae0b5fda350e4cda49f5c0a1a6644861d1483e85184324e6e9366c79dd`; padding retains the previous application tail.
- Public distribution permits the original module downloads. The Downloads distribution has `disabled_downloads: ["fangcun"]` in its embedded manifest and rejects Fangcun initial downloads/updates; installed modules and saves are retained. These are two configurations of the same source baseline.
- Exact release artifact hashes and the local distribution identity are in their respective `SHA256SUMS.txt` and `RELEASE.json`.

Restore the host by exiting RIO normally, replacing only its executable with the matching baseline distribution, and restarting. Keep `%LOCALAPPDATA%/RIO-Monitor` intact; settings and module saves are private runtime data, never public release assets. The current live executable need not be replaced merely to create a release package.

The EXE's explicit screen upgrade flow carries the accepted firmware, verifies the exact stock eM133-V3 profile and guard CRC, then writes only 12 KiB. It never updates already-running custom firmware automatically. For a screen already on 30780, do not reflash merely to install this host release. A future restore from another candidate must prepare a new plan matched to that outgoing image and verify the preserved 4 KiB guard; old one-use trial journals cannot be replayed.

Private recovery inputs, exact firmware build manifest/ELF/image, accepted physical/readback evidence and current settings are retained in `/home/aiops/artifacts/rio-monitor-rc0120-20261114`; private original build assets, SDK and compiler stay outside public Git. The maintained regression tests and build/recovery tools remain in source.

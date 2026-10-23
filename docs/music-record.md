# Default record and replacement label

Private assets: Kinkairy/usb-round-screen/artwork/music-mode/default-record.png and record-label.png. Import with --music-art alongside the usual private source, startup-loop and FFmpeg inputs. Public source does not contain the artwork.

The supplied default record is always the bottom layer. Absent, invalid or oversized album images leave it visible in full. A valid 188px album cover overlays that same record, with the new 74px RIO center label above it; no separately drawn vinyl substitutes for the private bottom layer. All layers rotate together. Playback pause freezes rotation; song metadata and lyrics are not replaced merely because artwork is missing.

Tests cover valid, missing and invalid covers, replacing rather than obscuring the label, pause/resume and source-only checkouts without private art. Source-only checkouts use a neutral substitute, not the approved proprietary artwork. Deployment and live USB results are recorded separately from these tests.

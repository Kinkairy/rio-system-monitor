# Original-art robot animation

Uses the approved A-type left/front/right PNGs, unchanged (hashes in robot-turn.json), not the rejected replacement 3D model. An atlas stores 62 feature-registered in-between images for the two turn legs. Runtime selection is based on elapsed monotonic time; the fixed base does not move. Existing 30 fps renderer defaults remain and the Qt preview timer now targets the same cadence instead of 15 fps. USB throughput is hardware-dependent and not validated here.

Eight LED expressions are drawn on the face plane. Dialogue bubbles contain path-drawn pictures only: heart, present, bulb, magnifier, moon, droplet, dizzy spiral, flower. The dizzy expression uses spiral eyes. Bubbles appear after a random 18–40-second idle interval, remain for at most 3 seconds, and may overlap the robot frame without covering telemetry. Demonstration videos used faster timing only for review.

The intermediate images are image-based correspondence interpolation, not recovered original 3D geometry. Small texture/shading discrepancies can remain at intermediate angles. Original source art is retained unchanged. SciPy/NumPy were used offline for baking, not added as runtime dependencies. No hardware deployment or driver changes.

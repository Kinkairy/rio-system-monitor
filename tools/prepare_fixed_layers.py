"""Bake fixed display resources; source artwork stays outside the runtime bundle."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

from PIL import Image

SOURCE_ONLY = {
    'background.png', 'gauge-mask.png', 'ram-separator.png', 'layout.json',
    'robot-front.png', 'robot-left.png', 'robot-right.png', 'rio-brand.png',
    'music/default-record.png', 'music/record-label.png', 'private-manifest.json',
}


def prepare(assets, output):
    assets, output = Path(assets).resolve(), Path(output).resolve()
    if output.name != 'runtime-assets' or output == assets or output in assets.parents:
        raise ValueError('Use a separate runtime-assets build directory')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from rio_monitor.render import Renderer
    from rio_monitor.music.renderer import MusicRenderer
    from verify_private_assets import verify

    manifest = verify(assets)
    monitor, music = Renderer(assets), MusicRenderer(assets)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for source in assets.rglob('*'):
        if source.is_file() and source.relative_to(assets).as_posix() not in SOURCE_ONLY:
            target = output / source.relative_to(assets)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    baked = output / 'precomposed'
    baked.mkdir(exist_ok=True)
    background = monitor.background.copy()
    if monitor.robot_plate is not None:
        background.paste(monitor.robot_plate, (904, 385), monitor.robot_plate)
    images = {
        'monitor.png': background,
        'gauge-mask.png': monitor.gauge_mask,
        'gauge-colors.png': monitor.gauge_colors,
        'gauge-dim.png': monitor.gauge_dim,
        'history-fill.png': monitor.temperature_fill,
        'history-alpha.png': monitor.temperature_fill_alpha,
        'music-badge.png': music.badge,
        'default-record.png': music.private_record_art('default-record.png', 222),
        'record-label.png': music.private_record_art('record-label.png', 74),
    }
    generated = []
    for name, image in images.items():
        image.save(baked / name)
        generated.append('precomposed/' + name)
    (baked / 'layers.json').write_text(json.dumps({'gauge_box': monitor.gauge_box}) + '\n')
    generated.append('precomposed/layers.json')
    with Image.open(assets / 'rio-brand.png') as source:
        brand = source.convert('RGBA')
        if brand.height > 80:
            brand = brand.crop((8, 88, 248, 168))
        brand.save(output / 'rio-brand.png')
    generated.append('rio-brand.png')
    qml = output / 'ui/Main.qml'
    qml.write_text(qml.read_text(encoding='utf-8').replace('sourceClipRect: Qt.rect(8,88,240,80)', 'sourceClipRect: Qt.rect(0,0,240,80)'), encoding='utf-8')
    generated.append('ui/Main.qml')
    manifest['asset_layout'] = 'precomposed-v1'
    manifest['files'] = [r for r in manifest['files'] if r['path'] not in SOURCE_ONLY | {'ui/Main.qml'} and not r['path'].startswith('precomposed/')]
    for name in generated:
        raw = (output / name).read_bytes()
        manifest['files'].append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    (output / 'private-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    verify(output)
    return output

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
    ui_generated=[p.relative_to(output).as_posix() for p in (output/'fangcun-ui').rglob('*') if p.is_file()] if (output/'fangcun-ui').is_dir() else []
    ui_generated += [p.relative_to(output).as_posix() for p in (output/'ui').rglob('*') if p.is_file() and p.name!='Main.qml']
    gourd_source=assets.parent.parent/'artwork/fangcun'
    if gourd_source.is_dir():
        for name in ['fangcun-gourd.png','fangcun-gourd.provenance.json','fangcun-gourd-v2.png','fangcun-gourd-v2.provenance.json','fangcun-gourd-v4.png','fangcun-gourd-v4.provenance.json']:
            shutil.copyfile(gourd_source/name,output/name)
        (output/'fangcun-ui').mkdir(exist_ok=True)
        for name in ['cultivation-body.png','navigation-compact-v2.png','cultivation-ui.provenance.json','navigation-compact-v2.provenance.json','cultivation-qi-v1.png','spiritual-roots-v1.png','inventory-v1.png','map-inventory-v1.provenance.json']:
            shutil.copyfile(gourd_source/name,output/'fangcun-ui'/name)
        ui_generated=list(dict.fromkeys(ui_generated+[p.relative_to(output).as_posix() for p in (output/'fangcun-ui').iterdir() if p.is_file()]))
    game_source=assets.parent.parent/'idle-game'
    if game_source.is_dir():
        from prepare_fangcun import prepare as prepare_game
        prepare_game(game_source,output/'fangcun')
    if not (output/'fangcun/runtime.mjs').is_file():
        raise ValueError('Fangcun runtime assets missing; run tools/prepare_fangcun.py from the private game source.')
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
    generated = ui_generated+['fangcun-gourd.png','fangcun-gourd.provenance.json','fangcun-gourd-v2.png','fangcun-gourd-v2.provenance.json','fangcun-gourd-v4.png','fangcun-gourd-v4.provenance.json']+[p.relative_to(output).as_posix() for p in (output/'fangcun').rglob('*') if p.is_file()]
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
    qml = output / 'ui/Rio/UI/PanelWindow.qml'
    qml.write_text(qml.read_text(encoding='utf-8').replace('property rect brandClipRect: Qt.rect(8,88,240,80)', 'property rect brandClipRect: Qt.rect(0,0,240,80)'), encoding='utf-8')
    generated.append('ui/Main.qml')
    manifest['asset_layout'] = 'precomposed-v1'
    manifest['files'] = [r for r in manifest['files'] if r['path'] not in SOURCE_ONLY | {'ui/Main.qml'} | set(ui_generated) and not r['path'].startswith(('precomposed/','fangcun/','ui/'))]
    for name in generated:
        raw = (output / name).read_bytes()
        manifest['files'].append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    (output / 'private-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    verify(output)
    return output

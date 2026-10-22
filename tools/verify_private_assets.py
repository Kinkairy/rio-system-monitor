"""Validate local, ignored assets before a private build. No downloads or credentials."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('background.png','clock.otf','fonts/Born2bSporty.otf',
            'fonts/PixelOperatorHB.ttf','gauge-mask.png','layout.json',
            'ram-separator.png','rio-brand.png','rio-icon.ico','rio-icon.png',
            'robot-front.png','robot-left.png','robot-right.png',
            'robot-turn-atlas.png','robot-turn.json','default-screen.gif','media/ffmpeg.exe')

def verify(root=ROOT/'assets'):
    manifest = root/'private-manifest.json'
    if not manifest.is_file():
        raise ValueError('Private assets missing. See README for tools/import_private_assets.py and its startup-loop/ffmpeg inputs.')
    data = json.loads(manifest.read_text(encoding='utf-8-sig'))
    rows = {r['path']:r for r in data['files']}
    for name in REQUIRED:
        path = root/name
        if name not in rows or not path.is_file(): raise ValueError('Missing private asset: '+name)
        raw = path.read_bytes()
        if len(raw)!=rows[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=rows[name]['sha256']:
            raise ValueError('Private asset checksum mismatch: '+name)
    return data

if __name__=='__main__':
    try:
        data=verify();print('Private assets verified for local build.')
    except (ValueError,KeyError,OSError) as exc:
        raise SystemExit(str(exc))

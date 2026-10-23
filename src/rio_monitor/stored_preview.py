"""Per-device preview of the last acknowledged write, never a device readback."""
import hashlib
import json
from pathlib import Path
from .media import PreparedMedia
from .resources import MAX_MEDIA_BYTES, gif_info


class StoredPreviewCache:
    def __init__(self, root):
        self.root = Path(root)

    def paths(self, device):
        if not isinstance(device, str) or not device:
            raise ValueError('A device identity is required')
        key = hashlib.sha256(device.lower().encode('utf-8')).hexdigest()
        return key, self.root / (key + '.json'), self.root / (key + '.gif')

    def atomic(self, path, data):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)

    def invalidate(self, device):
        key, record, _ = self.paths(device)
        self.atomic(record, json.dumps({'version': 1, 'device': key, 'valid': False}).encode('utf-8'))

    def store(self, device, media):
        gif_info(media.gif)
        key, record, preview = self.paths(device)
        self.atomic(preview, media.gif)
        data = dict(version=1, device=key, valid=True, name=media.name,
                    source_bytes=media.source_bytes, sha256=hashlib.sha256(media.gif).hexdigest())
        self.atomic(record, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def load(self, device):
        try:
            key, record, preview = self.paths(device)
            if record.stat().st_size > 4096:
                return None
            data = json.loads(record.read_text(encoding='utf-8'))
            if data.get('version') != 1 or data.get('device') != key or data.get('valid') is not True:
                return None
            name = data['name']
            if not isinstance(name, str) or not 0 < len(name) <= 512:
                return None
            with preview.open('rb') as stream:
                gif = stream.read(MAX_MEDIA_BYTES + 1)
            if hashlib.sha256(gif).hexdigest() != data['sha256']:
                return None
            info = gif_info(gif)
            return PreparedMedia(name, len(gif), gif, preview, **info)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

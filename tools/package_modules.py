"""Pack each extension module with its merged runtime resources; pin size and SHA-256 for the host.

Runs after prepare_fixed_layers: module resources move out of build/runtime-assets into
dist/RIO-Module-*.zip, so the EXE keeps only the host. Original artwork never enters a package.
"""
from pathlib import Path
import hashlib
import io
import json
import shutil
import zipfile

MODULES = {
    'fangcun': dict(package='rio_fangcun', asset='RIO-Module-Fangcun.zip',
                    resources=['fangcun', 'fangcun-ui', 'fangcun-gourd-v4.png'],
                    retired=['fangcun-gourd.png', 'fangcun-gourd-v2.png']),
    'blackshark': dict(package='rio_blackshark', asset='RIO-Module-BlackShark.zip', resources=[], retired=[]),
}
STAMP = (2026, 1, 1, 0, 0, 0)  # Fixed entry times keep packages reproducible.


def entry(name):
    info = zipfile.ZipInfo(name, STAMP)
    info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
    return info


def module_files(src, runtime, spec):
    files = {}
    for path in (src / spec['package']).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[spec['package'] + '/' + path.relative_to(src / spec['package']).as_posix()] = path
    for resource in spec['resources']:
        path = runtime / resource
        if not path.exists():
            raise ValueError('Module resource missing from runtime assets: ' + resource)
        for item in ([path] if path.is_file() else sorted(path.rglob('*'))):
            if item.is_file() and not item.name.endswith('.provenance.json'):
                files['assets/' + item.relative_to(runtime).as_posix()] = item
    return files


def package(src, runtime_assets, output, version):
    src, runtime, output = Path(src), Path(runtime_assets), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest, moved = {'version': version, 'modules': {}}, set()
    for name, spec in MODULES.items():
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr(entry('module.json'), json.dumps(dict(name=name, package=spec['package'], version=version), indent=2))
            for arcname, path in sorted(module_files(src, runtime, spec).items()):
                archive.writestr(entry(arcname), path.read_bytes())
        raw = data.getvalue()
        (output / spec['asset']).write_bytes(raw)
        manifest['modules'][name] = dict(asset=spec['asset'], size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        # The EXE keeps only host resources; image provenance sidecars leave with their image.
        for resource in spec['resources'] + spec['retired']:
            for path in (runtime / resource, runtime / resource.replace('.png', '.provenance.json')):
                if path.is_dir():
                    moved.update(p.relative_to(runtime).as_posix() for p in path.rglob('*') if p.is_file())
                    shutil.rmtree(path)
                elif path.is_file():
                    moved.add(path.relative_to(runtime).as_posix())
                    path.unlink()
    private = runtime / 'private-manifest.json'
    if private.is_file():
        record = json.loads(private.read_text(encoding='utf-8'))
        record['files'] = [row for row in record['files'] if row['path'] not in moved]
        private.write_text(json.dumps(record, indent=2), encoding='utf-8')
    (runtime / 'modules.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime_assets'); parser.add_argument('output')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'src'))
    from rio_monitor import __version__
    print(json.dumps(package(root / 'src', args.runtime_assets, args.output, __version__), indent=2))

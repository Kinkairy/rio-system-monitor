"""Pack each extension module with its merged runtime resources; pin size and SHA-256 for the host.

Runs after prepare_fixed_layers: module resources move out of build/runtime-assets into
dist/RIO-Module-*.zip, so the EXE keeps only the host. Original artwork never enters a package.
With --release, one module is packed as a module-only update and added to the module index instead.
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


def build(src, runtime, name, version):
    """One module package; module.json names the host interface version it was built against."""
    from rio_monitor.extensions import MODULE_API
    spec, data = MODULES[name], io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr(entry('module.json'), json.dumps(dict(name=name, package=spec['package'], version=version, api=MODULE_API), indent=2))
        for arcname, path in sorted(module_files(src, runtime, spec).items()):
            archive.writestr(entry(arcname), path.read_bytes())
    return data.getvalue()


def package(src, runtime_assets, output, version):
    from rio_monitor.extensions import MODULE_API
    src, runtime, output = Path(src), Path(runtime_assets), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest, moved = {'version': version, 'modules': {}}, set()
    for name, spec in MODULES.items():
        raw = build(src, runtime, name, version)
        (output / spec['asset']).write_bytes(raw)
        manifest['modules'][name] = dict(asset=spec['asset'], size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), api=MODULE_API)
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


def release(src, runtime_assets, output, name, version, index=None):
    """Pack one module as a module-only update and list it in RIO-Modules.json; the EXE is not rebuilt.

    index is the currently published RIO-Modules.json, so earlier entries stay listed for other hosts.
    Upload the package first and the index last, to the 'modules' prerelease.
    """
    from rio_monitor.extensions import INDEX, MODULE_API
    from rio_monitor.updater import version_key
    if version_key(version)[3] == 0:
        raise ValueError('Module updates are numbered <program version>.<n>, e.g. rc0.1.16.1')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    raw = build(Path(src), Path(runtime_assets), name, version)
    asset = MODULES[name]['asset'].replace('.zip', '-' + version + '.zip')
    (output / asset).write_bytes(raw)
    data = json.loads(Path(index).read_text(encoding='utf-8')) if index else {'schema': 1, 'modules': {}}
    rows = [row for row in data['modules'].get(name, []) if row['version'] != version]
    rows.append(dict(version=version, api=MODULE_API, asset=asset, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    data['modules'][name] = sorted(rows, key=lambda row: version_key(row['version']))
    (output / INDEX).write_text(json.dumps(data, indent=2), encoding='utf-8')
    return data


if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime_assets'); parser.add_argument('output')
    parser.add_argument('--release', nargs=2, metavar=('MODULE', 'VERSION'), help='pack one module-only update, e.g. blackshark rc0.1.16.1')
    parser.add_argument('--index', help='the published RIO-Modules.json to extend')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'src'))
    from rio_monitor import __version__
    if args.release:
        result = release(root / 'src', args.runtime_assets, args.output, *args.release, index=args.index)
    else:
        result = package(root / 'src', args.runtime_assets, args.output, __version__)
    print(json.dumps(result, indent=2))

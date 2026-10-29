"""Modules leave the EXE and are released apart from the program, each at its own version.

The EXE build runs package() after prepare_fixed_layers: module resources move out of build/runtime-assets,
so the EXE keeps only the host and assets/modules.json lists the modules it hosts. --release packs one module
with its code and merged runtime resources and lists it in the module index. Original artwork never enters a package.
"""
from pathlib import Path
import ast
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


def module_version(src, name):
    """A module's own version: __version__ in its package __init__.py, read without importing the module."""
    package = MODULES[name]['package']
    for node in ast.parse((Path(src) / package / '__init__.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(getattr(target, 'id', None) == '__version__' for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(package + ' has no __version__')


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


def package(runtime_assets, version):
    """EXE build step: take module resources out of the runtime assets and list the hosted modules in modules.json."""
    from rio_monitor.extensions import MODULE_API
    runtime = Path(runtime_assets)
    manifest, moved = {'version': version, 'api': MODULE_API, 'modules': list(MODULES)}, set()
    for spec in MODULES.values():
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
    """Pack one module at its own version and list it in RIO-Modules.json; the program is not rebuilt.

    version must be the module's __version__, raised for every new package. index is the currently published
    RIO-Modules.json, so earlier entries stay listed for other hosts. Upload the package first and the index last,
    to the 'modules' prerelease.
    """
    from rio_monitor.extensions import INDEX, MODULE_API
    from rio_monitor.updater import version_key
    own = module_version(src, name)
    if version != own or version_key(version) == (0, 0, 0, 0):
        raise ValueError(f'{name} is {own} in its source; set __version__ there to the version being released')
    raw = build(Path(src), Path(runtime_assets), name, version)
    asset, sha256 = MODULES[name]['asset'].replace('.zip', '-' + version + '.zip'), hashlib.sha256(raw).hexdigest()
    data = json.loads(Path(index).read_text(encoding='utf-8')) if index else {'schema': 1, 'modules': {}}
    # A published version never changes: hosts that have it would not take a different package of the same number.
    if any(row['version'] == version and (row['api'], row['sha256']) != (MODULE_API, sha256) for row in data['modules'].get(name, [])):
        raise ValueError(f'{name} {version} is already published with other contents; raise __version__')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    (output / asset).write_bytes(raw)
    rows = [row for row in data['modules'].get(name, []) if row['version'] != version]
    rows.append(dict(version=version, api=MODULE_API, asset=asset, size=len(raw), sha256=sha256))
    data['modules'][name] = sorted(rows, key=lambda row: (row['api'], version_key(row['version'])))
    (output / INDEX).write_text(json.dumps(data, indent=2), encoding='utf-8')
    return data


if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime_assets'); parser.add_argument('output', nargs='?', help='where --release writes the package and index')
    parser.add_argument('--release', nargs=2, metavar=('MODULE', 'VERSION'), help="pack one module at its own __version__, e.g. blackshark rc0.2")
    parser.add_argument('--index', help='the published RIO-Modules.json to extend')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'src'))
    from rio_monitor import __version__
    if args.release:
        if not args.output:
            parser.error('--release needs an output folder')
        result = release(root / 'src', args.runtime_assets, args.output, *args.release, index=args.index)
    else:
        result = package(args.runtime_assets, __version__)
    print(json.dumps(result, indent=2))

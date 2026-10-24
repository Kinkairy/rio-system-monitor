"""Write the license sidecar for an existing PyInstaller executable."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / 'dist/RIO-System-Monitor-Qt.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--version', help='Release version, when supplementing an older unchanged EXE')
    args = parser.parse_args()
    version = args.version or re.search(r'__version__\s*=\s*[\"\']([^\"\']+)', (ROOT / 'src/rio_monitor/__init__.py').read_text()).group(1)
    executable = args.executable.resolve()
    archive = CArchiveReader(str(executable))
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / f'RIO-System-Monitor-{version}-licenses.zip'
    materials = [ROOT / 'LICENSE', ROOT / 'THIRD-PARTY-NOTICES.md', ROOT / 'docs/distribution-licenses.md', ROOT / 'tools/build_ffmpeg_slim.sh']
    materials += sorted(p for p in (ROOT / 'docs/third-party').rglob('*') if p.is_file() and p.suffix.lower() in {'.txt', '.md', '.json', '.gplv3'})
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in materials:
            bundle.write(path, path.relative_to(ROOT).as_posix())
        # Preserve notices already shipped with the exact binary, including fonts.
        # No font, image, DLL or other runtime payload is copied into this ZIP.
        for name in sorted(archive.toc):
            relative = name.replace('\\', '/')
            if Path(relative).suffix.lower() in {'.txt', '.md', '.rst'} and any(word in relative.lower() for word in ('license', 'copying', 'notice')):
                bundle.writestr('bundled-notices/' + relative, archive.extract(name))
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        bundle.writestr('RELEASE.json', json.dumps({'version': version, 'executable': executable.name, 'size': executable.stat().st_size, 'sha256': digest, 'scope': 'Qt/PySide and FFmpeg distribution materials; no artwork or fonts'}, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()

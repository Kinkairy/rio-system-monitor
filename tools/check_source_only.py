"""Prevent binary/media assets or build products from entering the public tree."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'.png','.jpg','.jpeg','.webp','.gif','.bmp','.ico','.svg','.mp4','.avi',
           '.mov','.mkv','.webm','.ttf','.otf','.woff','.woff2','.exe','.dll','.zip',
           '.bundle','.bin','.pfx','.p12','.key'}

def main():
    paths=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
    bad=[p for p in paths if p and (Path(p).suffix.lower() in FORBIDDEN or (p.startswith('assets/') and not p.endswith('.qml')))]
    if bad:raise SystemExit('Public repository must contain source only:\n'+'\n'.join(bad))
    print('Public tracked tree contains source and documentation only; no private assets or builds.')

if __name__=='__main__':main()

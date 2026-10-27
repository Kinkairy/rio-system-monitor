"""Prevent binary/media assets, build products or extension-module sources from entering the public tree."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'.png','.jpg','.jpeg','.webp','.gif','.bmp','.ico','.svg','.mp4','.avi',
           '.mov','.mkv','.webm','.ttf','.otf','.woff','.woff2','.exe','.dll','.zip',
           '.bundle','.bin','.pfx','.p12','.key'}
# Extension modules stay in the private repository and are published only as Release packages.
PRIVATE_MODULES=('src/rio_fangcun/','src/rio_blackshark/','tools/fangcun/')

def main():
    paths=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
    bad=[p for p in paths if p and (Path(p).suffix.lower() in FORBIDDEN or p.startswith(PRIVATE_MODULES) or (p.startswith('assets/') and not p.endswith('.qml') and Path(p).name!='qmldir'))]
    if bad:raise SystemExit('Public repository must contain main-program source only:\n'+'\n'.join(bad))
    print('Public tracked tree contains main-program source and documentation only; no private assets, modules or builds.')

if __name__=='__main__':main()

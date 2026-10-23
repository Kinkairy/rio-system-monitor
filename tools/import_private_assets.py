"""Import explicitly supplied private materials without tracking or publishing them."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, shutil
from verify_private_assets import ROOT, verify

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--startup-loop',type=Path,required=True,help='Private fa2f691 color-accent GIF')
    parser.add_argument('--ffmpeg',type=Path,required=True,help='Local FFmpeg 6.1.1 Windows x64 converter; never uploaded')
    parser.add_argument('--music-font',type=Path,help='Private RIOPixel-Regular.ttf for approved music typography')
    args=parser.parse_args();source=args.source.resolve();target=(ROOT/'assets').resolve()
    manifest=source/'manifest.json';data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    checked=[]
    for row in data['files']:
        name=PurePosixPath(row['path'])
        if name.is_absolute() or '..' in name.parts or ':' in row['path'] or '\\' in row['path'] or name.suffix.lower() not in ('.png','.ico','.otf','.ttf','.json','.txt'):
            raise ValueError('Unexpected asset path')
        src=(source/str(name)).resolve();dest=(target/str(name)).resolve()
        if not src.is_relative_to(source) or not dest.is_relative_to(target):raise ValueError('Asset escapes directory')
        raw=src.read_bytes()
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Asset checksum mismatch: '+str(name))
        checked.append((src,dest))
    extras=[]
    for src,name,expected in (
        (args.startup_loop,'default-screen.gif','7d1d5659c04ce92810bf7be6717844946815666220b13c5c785cfe63b80daa6c'),
        (args.ffmpeg,'media/ffmpeg.exe','04e1307997530f9cf2fe35cba2ca7e8875ca91da02f89d6c7243df819c94ad00')):
        raw=src.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=expected:raise ValueError('Bundled file checksum mismatch: '+name)
        checked.append((src,target/name));extras.append({'path':name,'bytes':len(raw),'sha256':digest})
    if args.music_font:
        raw=args.music_font.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!='82ef63f9bb67a52b5daae663bc83e56bd86d2bc062a78223270e82117fe87919':raise ValueError('Music font checksum mismatch')
        checked.append((args.music_font,target/'fonts/RIOPixel-Regular.ttf'));extras.append({'path':'fonts/RIOPixel-Regular.ttf','bytes':len(raw),'sha256':digest})
    for src in sorted((ROOT/'docs/third-party/ffmpeg').iterdir()):
        if src.is_file() and (src.suffix=='.txt' or src.name=='COPYING.GPLv3'):
            raw=src.read_bytes();name='media/'+src.name
            checked.append((src,target/name));extras.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    data['files'].extend(extras)
    data['startup_source']={'repository':'Kinkairy/usb-round-screen','commit':'fa2f6913e507a728961b18bed42addf9919294f8','path':'artwork/startup-loop/RIO-System-Monitor-color-accent-loop.gif'}
    for src,dest in checked:
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    (target/'private-manifest.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    verify(target);print(f'Imported and verified {len(checked)} private assets. These files must remain untracked.')

if __name__=='__main__':main()


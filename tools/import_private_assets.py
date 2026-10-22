"""Import explicitly supplied private materials without tracking or publishing them."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, shutil
from verify_private_assets import ROOT, verify

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
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
    for src,dest in checked:
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    (target/'private-manifest.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    verify(target);print(f'Imported and verified {len(checked)} private assets. These files must remain untracked.')

if __name__=='__main__':main()

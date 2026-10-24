"""Prepare the exact slim components used by Build-Windows.cmd."""
import argparse,hashlib,json,os,shutil,sys,zipfile
from pathlib import Path
from verify_private_assets import ROOT,verify

NUMPY_SHA='4ce98489fdf3f2e53f058d7d80e3a95d76440c4092482840a625e281f7bded67'
FFMPEG_SHA='5c342ee11ed7d24b1fe55fd4a3df06afa6e52f95af78674d5156b5db2ccee221'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--numpy-wheel',type=Path,default=os.environ.get('RIO_NUMPY_WHEEL'))
    parser.add_argument('--ffmpeg',type=Path,default=os.environ.get('RIO_FFMPEG',str(ROOT/'assets/media/ffmpeg.exe')))
    args=parser.parse_args()
    if args.numpy_wheel is None:parser.error('Set RIO_NUMPY_WHEEL or pass --numpy-wheel; see README.')
    if sys.version_info[:2]!=(3,12):parser.error('The pinned NumPy wheel requires Python 3.12 x64.')
    for path,expected in ((args.numpy_wheel,NUMPY_SHA),(args.ffmpeg,FFMPEG_SHA)):
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            parser.error('Expected the documented slim component: '+str(path))
    verify()
    runtime=ROOT/'build/numpy-slim'
    runtime.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.numpy_wheel) as wheel:wheel.extractall(runtime)
    target=ROOT/'assets/media/ffmpeg.exe'
    if args.ffmpeg.resolve()!=target.resolve():shutil.copyfile(args.ffmpeg,target)
    manifest=ROOT/'assets/private-manifest.json'
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    for row in data['files']:
        if row['path']=='media/ffmpeg.exe':row.update(bytes=target.stat().st_size,sha256=FFMPEG_SHA)
    manifest.write_text(json.dumps(data,indent=2),encoding='utf-8')
    verify()
    print('Slim NumPy and FFmpeg prepared; Qt exclusions are defined in packaging_filter.py.')

if __name__=='__main__':main()

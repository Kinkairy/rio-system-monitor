# -*- mode: python ; coding: utf-8 -*-
import os,sys,json
from pathlib import Path
sys.path.insert(0,SPECPATH)
from packaging_filter import keep
from PyInstaller.utils.hooks import collect_submodules,collect_dynamic_libs
music_imports=[]
music_binaries=[]
if sys.platform=="win32":
    music_imports=collect_submodules("winrt")+collect_submodules("pyaudiowpatch")
    music_binaries=collect_dynamic_libs("pyaudiowpatch")
root=Path(SPECPATH)
sys.path.insert(0,str(root/'tools'))
from prepare_fixed_layers import prepare
from package_modules import MODULES,package as package_modules
from windows_version_info import windows_version_info
runtime_assets=prepare(root/'assets',root/'build/runtime-assets')
sys.path.insert(0,str(root/'src'))
from rio_monitor import __version__
from rio_monitor.firmware_update import load_plan
from rio_monitor import firmware_release
from rio_monitor.t113_display import WAVESHARE_FIRMWARE,read_firmware_package
firmware_dir=Path(os.environ['RIO_LT168B_FIRMWARE_DIR']).resolve()
load_plan(firmware_dir)
firmware_release.bundled(firmware_dir)  # Verify each released image before embedding it.
waveshare_package=root.parent/'firmware'/'waveshare_t113'/WAVESHARE_FIRMWARE
waveshare_data=[]
if waveshare_package.is_file():
    read_firmware_package(waveshare_package)
    waveshare_data.append((str(waveshare_package),'firmware'))

# Extension modules leave the EXE; assets/modules.json lists them and each is released apart (package_modules.py --release).
package_modules(runtime_assets,__version__,disable_fangcun_download=os.environ.get("RIO_NO_FANGCUN_DOWNLOAD")=="1")
module_packages=[spec['package'] for spec in MODULES.values()]
a=Analysis([str(root/'launch.py')],pathex=[str(root/'src')],binaries=music_binaries,datas=[(str(runtime_assets),'assets'),(str(firmware_dir/'em133-v3-rio1.json'),'firmware'),(str(firmware_dir/firmware_release.FILENAME),'firmware'),(str(root/'docs/third-party'),'licenses'),(str(root/'THIRD-PARTY-NOTICES.md'),'licenses'),(str(root/'docs/distribution-licenses.md'),'licenses'),(str(root/'LICENSE'),'licenses/RIO')]+waveshare_data,hiddenimports=music_imports+module_packages,hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['tkinter','PIL.AvifImagePlugin','PIL._avif'],noarchive=False)
# Analysing the modules keeps their dependencies in the EXE; their own code ships only in the packages.
a.pure=[entry for entry in a.pure if entry[0].split('.')[0] not in module_packages]
removed=[n for n,_,_ in list(a.binaries)+list(a.datas) if not keep(n)]
a.binaries=[entry for entry in a.binaries if keep(entry[0])]
a.datas=[entry for entry in a.datas if keep(entry[0])]
(root/'bundle-pruning.json').write_text(json.dumps({'removed_files':len(removed),'removed':removed,'software_opengl_fallback_retained':True},indent=2))
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='RIO-System-Monitor-Qt',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,icon=str(root/'assets/rio-icon.ico'),version=windows_version_info(__version__) if sys.platform=='win32' else None)


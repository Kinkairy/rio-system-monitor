# -*- mode: python ; coding: utf-8 -*-
import os,sys,json
from pathlib import Path
sys.path.insert(0,SPECPATH)
from packaging_filter import keep
root=Path(SPECPATH)
sys.path.insert(0,str(root/'tools'))
from verify_private_assets import verify
verify(root/'assets')
a=Analysis([str(root/'launch.py')],pathex=[str(root/'src')],binaries=[],datas=[(str(root/'assets'),'assets')],hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['tkinter','PIL.AvifImagePlugin','PIL._avif'],noarchive=False)
removed=[n for n,_,_ in list(a.binaries)+list(a.datas) if not keep(n)]
a.binaries=[entry for entry in a.binaries if keep(entry[0])]
a.datas=[entry for entry in a.datas if keep(entry[0])]
(root/'bundle-pruning.json').write_text(json.dumps({'removed_files':len(removed),'removed':removed,'software_opengl_fallback_retained':True},indent=2))
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='RIO-System-Monitor-Qt',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,icon=str(root/'assets/rio-icon.ico'))

"""Windows VERSIONINFO for the RIO System Monitor executable."""

import re


def version_fields(version):
    match = re.fullmatch(r'rc(\d+)\.(\d+)\.(\d+)', version)
    if match is None:
        raise ValueError(f'Invalid RIO release version {version!r}')
    number = tuple(map(int, match.groups())) + (0,)
    strings = {
        'FileDescription': 'RIO System Monitor',
        'FileVersion': version,
        'InternalName': 'RIO-System-Monitor',
        'OriginalFilename': 'RIO-System-Monitor.exe',
        'ProductName': 'RIO System Monitor',
        'ProductVersion': version,
    }
    return number, strings


def windows_version_info(version):
    from PyInstaller.utils.win32 import versioninfo

    number, strings = version_fields(version)
    return versioninfo.VSVersionInfo(
        ffi=versioninfo.FixedFileInfo(
            filevers=number, prodvers=number, mask=0x3F, flags=0x02, OS=0x40004,
            fileType=1, subtype=0, date=(0, 0),
        ),
        kids=[
            versioninfo.StringFileInfo([
                versioninfo.StringTable('040904B0', [
                    versioninfo.StringStruct(key, value) for key, value in strings.items()
                ]),
            ]),
            versioninfo.VarFileInfo([versioninfo.VarStruct('Translation', [0x0409, 1200])]),
        ],
    )

"""Per-user preferences; no service, elevated writes or automatic USB connection."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json, os, sys

@dataclass
class Settings:
    fps: int = 30
    rotation: int = 0
    weather_mode: str = 'auto'
    city: str = ''
    start_hidden: bool = True  # Legacy key; normal launches always enter the tray.
    autostart: bool = False
    language: str = 'en'
    temperature_monitor: bool = True
    display_mode: str = 'monitor'
    game_enabled: bool = False
    gourd_x: int = -1
    gourd_y: int = -1
    music_enabled: bool = False
    music_online_lyrics: bool = True
    music_source: str = ''
    music_lyrics_consent: int = 2
    blackshark_enabled: bool = False

def config_path():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.config'))/'RIO-Monitor'/'settings.json'

def load():
    try:
        raw=json.loads(config_path().read_text(encoding='utf-8'))
        s=Settings(**{k:v for k,v in raw.items() if k in Settings.__dataclass_fields__})
        if s.fps not in (15,20,30) or (not isinstance(s.rotation,int) or not 0<=s.rotation<=359) or s.weather_mode not in ('off','auto','manual'):raise ValueError('Invalid settings')
        if s.language not in ('en','zh') or not isinstance(s.city,str) or not isinstance(s.start_hidden,bool) or not isinstance(s.autostart,bool) or not isinstance(s.temperature_monitor,bool):raise ValueError('Invalid settings')
        if not isinstance(s.game_enabled,bool) or type(s.gourd_x) is not int or type(s.gourd_y) is not int:raise ValueError('Invalid game setting')
        if s.display_mode not in ('monitor','stored'):raise ValueError('Invalid display mode')
        if not isinstance(s.music_enabled,bool) or not isinstance(s.music_online_lyrics,bool) or not isinstance(s.music_source,str):raise ValueError('Invalid music settings')
        if not isinstance(s.blackshark_enabled,bool):raise ValueError('Invalid BlackShark setting')
        if 'music_online_lyrics' in raw and 'music_lyrics_consent' not in raw:s.music_lyrics_consent=0
        if s.music_lyrics_consent != 2:s.music_online_lyrics=False  # Preserve older provider opt-outs.
        s.start_hidden=True
        s.display_mode='monitor'  # Each program launch reconnects the live display.
    except (OSError,ValueError,TypeError):raw={};s=Settings()
    # Older releases resumed BlackShark whenever its saved configuration existed.
    if 'blackshark_enabled' not in raw:s.blackshark_enabled=config_path().with_name('blackshark.json').is_file()
    return s

def save(s):
    p=config_path();p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(s),ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)

def acquire_instance():
    """Keep one Windows GUI owner, including a running older release."""
    if sys.platform!='win32':return True
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateMutexW(None,False,r'Local\RIO-System-Monitor')
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    exists=ctypes.get_last_error()==183
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p];user.FindWindowW.restype=ctypes.c_void_p
    if exists or user.FindWindowW(None,'RIO System Monitor'):
        kernel.CloseHandle(handle);return None
    return handle  # Windows releases the mutex handle when this process exits.

def set_autostart(enabled):
    if sys.platform!='win32':
        if enabled:raise RuntimeError('Autostart is currently Windows-only')
        return
    if enabled and not getattr(sys,'frozen',False):raise RuntimeError('Enable autostart in the packaged EXE, not the source preview')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'RIO-Monitor',0,winreg.REG_SZ,'"'+sys.executable+'"')
        else:
            try:winreg.DeleteValue(key,'RIO-Monitor')
            except FileNotFoundError:pass


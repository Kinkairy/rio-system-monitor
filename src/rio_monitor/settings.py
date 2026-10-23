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
    music_enabled: bool = False
    music_online_lyrics: bool = False
    music_source: str = ''

def config_path():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.config'))/'RIO-Monitor'/'settings.json'

def load():
    try:
        raw=json.loads(config_path().read_text(encoding='utf-8'))
        s=Settings(**{k:v for k,v in raw.items() if k in Settings.__dataclass_fields__})
        if s.fps not in (15,20,30) or (not isinstance(s.rotation,int) or not 0<=s.rotation<=359) or s.weather_mode not in ('off','auto','manual'):raise ValueError('Invalid settings')
        if s.language not in ('en','zh') or not isinstance(s.city,str) or not isinstance(s.start_hidden,bool) or not isinstance(s.autostart,bool) or not isinstance(s.temperature_monitor,bool):raise ValueError('Invalid settings')
        if s.display_mode not in ('monitor','stored'):raise ValueError('Invalid display mode')
        if not isinstance(s.music_enabled,bool) or not isinstance(s.music_online_lyrics,bool) or not isinstance(s.music_source,str):raise ValueError('Invalid music settings')
        s.start_hidden=True
        s.display_mode='monitor'  # Each program launch reconnects the live display.
        return s
    except (OSError,ValueError,TypeError):return Settings()

def save(s):
    p=config_path();p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(s),ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)

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


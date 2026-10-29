"""Anonymous GitHub Release updates, applied only after the running EXE exits."""
import hashlib,json,os,re,subprocess,sys,threading,urllib.request
from pathlib import Path
from . import __version__

REPOSITORY='Kinkairy/rio-system-monitor'
ASSET_NAME='RIO-System-Monitor.exe'
API_URL=f'https://api.github.com/repos/{REPOSITORY}/releases/latest'


def version_key(value):
    # A fourth part numbers module-only updates made on top of a program version, e.g. rc0.1.16.1.
    match=re.fullmatch(r'(?:rc|v)?(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?',str(value))
    return tuple(int(part or 0) for part in match.groups()) if match else (0,0,0,0)


def latest_asset(current=__version__):
    request=urllib.request.Request(API_URL,headers={'User-Agent':'RIO-System-Monitor/'+__version__,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=8) as response:release=json.load(response)
    if release.get('draft') or release.get('prerelease') or version_key(release.get('tag_name'))<=version_key(current):return None
    for asset in release.get('assets',[]):
        if asset.get('name')!=ASSET_NAME or asset.get('state')!='uploaded':continue
        if not re.fullmatch('sha256:[0-9a-fA-F]{64}',asset.get('digest') or ''):continue
        prefix=f'https://github.com/{REPOSITORY}/releases/download/'
        if not str(asset.get('browser_download_url','')).startswith(prefix):continue
        return dict(asset,version=release['tag_name'])
    return None


def download_asset(asset,directory,stop=None,progress=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    expected=asset['digest'].split(':',1)[1].lower()
    destination=directory/asset.get('file',asset['version']+'.exe');partial=destination.with_suffix('.part')
    if destination.is_file() and file_hash(destination)==expected:
        if progress:progress(asset['size'],asset['size'])
        return destination
    request=urllib.request.Request(asset['browser_download_url'],headers={'User-Agent':'RIO-System-Monitor/'+__version__})
    digest=hashlib.sha256();size=0
    try:
        if progress:progress(0,asset['size'])
        with urllib.request.urlopen(request,timeout=15) as response,partial.open('wb') as output:
            while block:=response.read(1024*1024):
                if stop and stop.is_set():raise InterruptedError('Program is exiting')
                size+=len(block);digest.update(block);output.write(block)
                if progress:progress(size,asset['size'])
        if size!=asset['size'] or digest.hexdigest()!=expected:raise ValueError('Incomplete or damaged update')
        partial.replace(destination)
        return destination
    finally:partial.unlink(missing_ok=True)


def file_hash(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


INSTALL_SCRIPT=r"""
param([string]$Plan)
$ErrorActionPreference='Stop'
$data=Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    foreach ($processId in $data.wait_pids) {
        $process=Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            try { if (-not $process.WaitForExit(60000)) { throw ('RIO process '+$processId+' did not exit') } }
            finally { $process.Dispose() }
        }
    }
    $target=[IO.Path]::GetFullPath([string]$data.target)
    if ([IO.Path]::GetExtension($target) -ne '.exe') { throw 'Invalid update target' }
    # Without a staged program this only restarts RIO, so updated modules load.
    if ($data.staged) {
        $staged=[IO.Path]::GetFullPath([string]$data.staged)
        $stream=[IO.File]::OpenRead($staged)
        $sha=[Security.Cryptography.SHA256]::Create()
        try { $actual=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose();$sha.Dispose() }
        if ($actual -ne $data.sha256) { throw 'Update changed' }
        $replacement=$target+'.update'
        Copy-Item -LiteralPath $staged -Destination $replacement -Force
        [IO.File]::Replace($replacement,$target,[NullString]::Value)
        Remove-Item -LiteralPath $staged -Force
    }
    $env:PYINSTALLER_RESET_ENVIRONMENT='1'
    if ($data.arguments) { Start-Process -FilePath $target -ArgumentList $data.arguments -WindowStyle Hidden }
    else { Start-Process -FilePath $target -WindowStyle Hidden }
    @{status=$data.status;version=$data.version} | ConvertTo-Json | Set-Content -LiteralPath $data.status_path -Encoding UTF8
} catch {
    @{status='install_failed';version=$data.version;error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $data.status_path -Encoding UTF8
} finally {
    Remove-Item -LiteralPath $Plan -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
"""


def launch_install(staged,target,directory,version,wait_pids,arguments=('--show-settings',)):
    """Replace target with staged after the given processes exit, then start it; staged=None only restarts."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    script=directory/'install-update.ps1';plan=directory/'install-update.json'
    script.write_text(INSTALL_SCRIPT,encoding='utf-8-sig')
    data=dict(staged=str(Path(staged).resolve()) if staged else '',target=str(Path(target).resolve()),version=version,
              sha256=file_hash(staged) if staged else '',wait_pids=wait_pids,arguments=list(arguments),
              status='installed' if staged else 'restarted',status_path=str((directory/'status.json').resolve()))
    plan.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8-sig')
    powershell=Path(os.environ.get('SYSTEMROOT','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-Plan',str(plan)],
                            creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


class AutoUpdater:
    def __init__(self,directory,modules=None):
        self.directory=Path(directory);self.stop=threading.Event();self.worker=None;self.pending=None
        self.lock=threading.Lock();self.state=dict(state='idle',connection='unknown',progress=0)
        # modules(stop) installs module updates after each program check and returns True when a restart would load them.
        # restart: such packages are installed; relaunch: the host is exiting to load them.
        self.modules=modules;self.restart=False;self.relaunch=False
    def snapshot(self):
        with self.lock:return dict(self.state)
    def update(self,**values):
        with self.lock:self.state.update(values)
    def check(self):
        with self.lock:
            if self.stop.is_set() or self.pending or (self.worker and self.worker.is_alive()):return
            self.state.update(state='checking',progress=0)
            self.worker=threading.Thread(target=self.run,daemon=True,name='RIO-update');self.worker.start()
    def run(self):
        self.program()
        # A staged program restarts RIO anyway; it reads the module index for its own interface after that.
        if self.modules and not self.pending and not self.stop.is_set():
            try:
                if self.modules(self.stop):self.restart=True
            except Exception:pass
    def program(self):
        try:
            asset=latest_asset()
            self.update(connection='connected')
            if not asset:self.update(state='latest');return
            self.update(state='downloading')
            staged=download_asset(asset,self.directory,self.stop,
                                  lambda done,total:self.update(progress=min(99,done*100//max(1,total))))
            if not self.stop.is_set():
                self.pending=(staged,asset['version']);self.update(state='ready',progress=100)
        except Exception as exc:
            snapshot=self.snapshot()
            self.update(state='error',connection='failed' if snapshot['state']=='checking' else snapshot['connection'])
            try:
                self.directory.mkdir(parents=True,exist_ok=True)
                (self.directory/'status.json').write_text(json.dumps(dict(status='check_failed',error=type(exc).__name__)),encoding='utf-8')
            except OSError:pass
    def install_on_exit(self):
        self.stop.set()
        if self.pending:
            staged,version=self.pending
            try:launch_install(staged,sys.executable,self.directory,version,[os.getpid(),os.getppid()])
            except OSError:pass
        elif self.restart and self.relaunch:
            try:launch_install(None,sys.executable,self.directory,__version__,[os.getpid(),os.getppid()],arguments=())
            except OSError:pass

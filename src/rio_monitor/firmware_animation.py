"""Install the built-in animation on an identified eM133-V3 using its two USB modes."""
import hashlib
import json
import os
import struct
import tempfile
import time
from contextlib import closing
from pathlib import Path

from . import firmware_release as release_files
from . import firmware_segments as seg

GAP_SIZE = seg.BANK - seg.LOW_END
QUICK = (seg.LOW_END, seg.LOW_END+seg.SECTOR, seg.BANK, seg.BANK_END, seg.END_GUARD)
FACTORY_CRC = 0x7a77b01c
FIRST_GUARD = 0x8a1711f4
END_GUARD = 0x3648671b

def preserve(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            tmp = Path(output.name)
        try:
            with tmp.open('wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                if os.name == 'nt':
                    tmp.rename(path)
                else:
                    os.link(tmp, path)
            except FileExistsError:
                pass
        finally:
            tmp.unlink(missing_ok=True)
    if path.read_bytes() != data:
        raise OSError('Existing firmware backup differs: '+str(path))

def flash_snapshot(loader):
    if loader.identify() != seg.LOADER:
        raise ValueError('Unrecognized screen bootloader')
    snapshot = {end:loader.checksum(end) for end in seg.ENDS}
    gap, guard = seg.signatures(snapshot)
    if gap[0] != FIRST_GUARD or guard != END_GUARD:
        raise ValueError('Flash layout does not match the supported eM133-V3')
    return snapshot, gap

def bank_matches(snapshot, bank):
    checksum = snapshot[seg.BANK]
    start = seg.BANK
    for end in seg.BANK_ENDS:
        checksum = seg.crc(memoryview(bank)[start-seg.BANK:end-seg.BANK], checksum)
        if checksum != snapshot[end]:
            return False
        start = end
    return True

def write_application(loader, image, before):
    delta = before[seg.LOW_END] ^ seg.crc(image.data)
    loader.write_image(image, lambda count: None)
    for end in QUICK:
        expected = before[end] ^ seg.crc(bytes(end-seg.LOW_END), delta)
        if loader.checksum(end) != expected:
            raise OSError('Application or adjacent flash verification failed at '+hex(seg.ORIGIN+end))
    loader.run()

def verify_gap(data, checks):
    if len(data) != GAP_SIZE or len(checks) != len(seg.GAP_ENDS):
        raise ValueError('Incomplete eM133-V3 protected partition')
    for i, original in enumerate(checks):
        if seg.crc(data[i*seg.SECTOR:(i+1)*seg.SECTOR]) != original:
            raise OSError(f'Protected sector {i} differs from the pre-update screen')
    return hashlib.sha256(data).hexdigest()

class Maintenance:
    def __init__(self, usb):
        self.usb = usb

    def close(self):
        self.usb.close()

    def request(self, code, index=0):
        length = {0x57:64, 0x58:seg.SECTOR, 0x59:0, 0x5a:0, 0x5b:0}[code]
        data = self.usb.control(0xc0 if length else 0x40, code, 0xb201, index, length)
        if len(data)!=length:
            raise OSError(f'Short maintenance transfer at sector {index}')
        return data

    def status(self):
        raw=self.request(0x57)
        if raw[:8]!=b'RIOBK201' or raw[8:40]!=release_files.CHAIN_ROOT:
            raise ValueError('Unexpected RIO maintenance release')
        return struct.unpack_from('<5I2B',raw,40)

    def read_gap(self, checks):
        data=b''.join(self.request(0x58,i) for i in range(len(checks)))
        verify_gap(data, checks)
        if self.status()[0]!=len(checks):
            raise OSError('The screen did not confirm all backup sectors')
        return data

    def wait_sector(self, index, committed):
        deadline=time.monotonic()+15
        while True:
            _, next_sector, received, fault, _, phase, _ = self.status()
            if fault:
                raise OSError(f'Animation sector {index} reported device error {fault}')
            if committed and next_sector==index+1 and phase==0:
                return
            if not committed and next_sector==index and phase==1 and received==seg.SECTOR+32:
                return
            if time.monotonic()>=deadline:
                raise TimeoutError(f'No animation acknowledgement at sector {index}')
            time.sleep(.01)

    def write_bank(self, records, checks, backup, progress):
        _, start, _, fault, _, phase, armed=self.status()
        if fault or phase==2 or start>len(records):
            raise OSError('Previous sector operation has not completed')
        if not armed:
            self.request(0x59)
        for i in range(start,len(records)):
            self.request(0x5a,i)
            if self.usb.write(1,records[i])!=len(records[i]):
                raise OSError(f'Incomplete transfer at animation sector {i}')
            self.wait_sector(i,False)
            self.request(0x5b,i)
            self.wait_sector(i,True)
            if i==0 and self.read_gap(checks)!=backup:
                raise OSError('Protected data changed after the first animation sector')
            progress((i+1)/len(records))
        if self.status()[1]!=len(records) or self.read_gap(checks)!=backup:
            raise OSError('Animation readback or protected partition verification failed')

class Connections:
    def __init__(self, ports, opener, paths):
        self.ports, self.opener, self.paths = ports, opener, paths

    def maintenance(self):
        from .display_protocols import rio_frame_interface
        from .winusb import WinUSB
        deadline=time.monotonic()+35
        last_error=None
        while time.monotonic()<deadline:
            paths=self.paths()
            if len(paths)>1:
                raise ValueError('Connect only the eM133-V3 being updated')
            if paths and rio_frame_interface(paths[0]):
                try:
                    target=Maintenance(WinUSB(paths[0],profile='lt168b-bench'))
                    try:
                        target.status()
                    except BaseException:
                        target.close()
                        raise
                    return target
                except OSError as exc:
                    last_error=exc
            time.sleep(.25)
        raise TimeoutError('The RIO maintenance interface did not appear') from last_error

    def boot(self):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            ports=self.ports()
            if len(ports)>1:
                raise ValueError('Connect only one upgrade-mode screen')
            if ports and not self.paths():
                return self.opener(ports[0])
            time.sleep(.4)
        raise TimeoutError('Waiting for activation timed out. Reopen the update with the screen in boot mode to resume.')

def run(port, release, backups, install, record, stage, connections, *, factory_only=False):
    loader=seg.RioLoader(port)
    before, checks=flash_snapshot(loader)
    current=before[seg.LOW_END]
    previous={seg.crc(data):data for data in release.previous}
    helper_crc=seg.crc(release.helper.data)
    if factory_only:
        if current in previous or current==seg.crc(release.player.data):
            loader.run()
            return 'rio_firmware_present'
        if current not in (FACTORY_CRC,helper_crc):
            return 'unrecognized_firmware'
    full=bank_matches(before,release.bank)
    record(dict(stage='identified', board=seg.BOARD, application_crc=current, animation_verified=full))
    if current==seg.crc(release.player.data):
        if not full:
            raise OSError('Installed player has a different animation bank')
        loader.run()
        return 'already_installed_and_verified'
    if current not in (*previous, FACTORY_CRC, helper_crc):
        raise ValueError('The installed firmware is outside the eM133-V3 release profile')
    if current!=helper_crc and not full and not bank_matches(before,seg.BLANK):
        raise ValueError('Animation storage contains a different image')
    if not install:
        loader.run()
        return 'compatible_maintenance_pending' if current==helper_crc else 'compatible_for_animation'

    fingerprint=hashlib.sha256(struct.pack('<%dI'%len(checks),*checks)).hexdigest()
    folder=Path(backups)/('em133-v3-'+fingerprint)
    checkpoint=folder/'layout.json'
    layout=json.dumps(dict(board=seg.BOARD,protected_crc32=checks,following_crc32=END_GUARD),
                      separators=(',',':')).encode('ascii')
    if current==helper_crc:
        if not checkpoint.is_file() or checkpoint.read_bytes()!=layout:
            raise OSError('Resume on the computer holding this screen’s pre-update backup')
    else:
        preserve(checkpoint,layout)
        if current in previous:
            data=previous[current]
            preserve(folder/('rio-before-'+hashlib.sha256(data).hexdigest()+'.bin'),data)
    backup_path=folder/'protected-588KiB.bin'
    if current==helper_crc and full and backup_path.is_file():
        digest=verify_gap(backup_path.read_bytes(),checks)
        record(dict(stage='resumed_verified_bank',protected_sha256=digest))
        stage('activating',.94)
        write_application(loader,release.player,before)
        return 'segments_verified_and_started'

    stage('backing_up',.03)
    if current==helper_crc:
        loader.run()
    else:
        write_application(loader,release.helper,before)
    port.close()
    with closing(connections.maintenance()) as helper:
        backup=helper.read_gap(checks)
        preserve(backup_path,backup)
        digest=verify_gap(backup_path.read_bytes(),checks)
        record(dict(stage='backup_verified',path=str(backup_path),bytes=len(backup),sha256=digest))
        stage('writing_bank',.08)
        helper.write_bank(release_files.sector_records(release.bank),checks,backup,
                          lambda p:stage('writing_bank',.08+.82*p))
    record(dict(stage='awaiting_activation',sectors=len(release.bank)//seg.SECTOR,protected_sha256=digest))
    stage('wait_activation',.90)
    with closing(connections.boot()) as final_port:
        loader=seg.RioLoader(final_port)
        staged, after_checks=flash_snapshot(loader)
        if after_checks!=checks or staged[seg.LOW_END]!=helper_crc or not bank_matches(staged,release.bank):
            raise OSError('Reconnected screen does not match the verified update')
        stage('activating',.94)
        write_application(loader,release.player,staged)
    record(dict(stage='player_verified_and_started',player_sha256=release_files.PLAYER_SHA))
    return 'segments_verified_and_started'

"""Build the unqualified LT168B bench application. Never programs a device.

Run from a fixed exported input snapshot using the official portable CCore
toolchain. SDK binaries/headers remain external and are hashed in the manifest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', action='store_true', help='diagnostic stage counters only')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    sdk, tc, out = (p.resolve() for p in (args.sdk, args.toolchain, args.output))
    out.mkdir(parents=True, exist_ok=True)
    commands = []
    environment = os.environ.copy()
    environment['PATH'] = str(tc.parent / 'bin') + os.pathsep + environment.get('PATH', '')

    def run(name, options):
        exe = tc / 'bin' / ('mcore-elf-' + name + '.exe')
        command = [str(exe), *map(str, options)]
        commands.append(command)
        result = subprocess.run(command, capture_output=True, env=environment)
        with (out / 'build.log').open('ab') as log:
            log.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('exit %s: %s' % (result.returncode, (result.stdout + result.stderr).decode('utf-8', 'replace')))
        return result.stdout.decode('utf-8', 'replace')

    (out / 'build.log').write_bytes(b'')
    version = run('gcc', ['--version'])
    includes = [source, sdk / 'User', sdk / 'MCU_drv', sdk / 'include']
    flags = ['-std=gnu99', '-Os', '-fno-common', '-ffunction-sections',
             '-fdata-sections', '-mlittle-endian', '-Wall', '-Wextra']
    if args.profile:
        flags.append('-DRIO_STAGE_PROFILE=1')
    inputs = [source / n for n in ('board_main.c', 'board_cache.c', 'board_panel.c', 'board_backlight.c', 'board_flash_probe.c', 'board_usb.c', 'rio_stream.c', 'rio_usb.c', 'rio_lz4.c')]
    inputs += [sdk / 'User' / n for n in ('startup.s', 'vector_table.c')]
    inputs += [sdk / 'MCU_drv' / 'lt168_clock.c']
    objects = []
    for path in inputs:
        obj = out / (path.stem + '.o')
        run('gcc', [*flags, *['-I' + str(p) for p in includes], '-c', path, '-o', obj])
        objects.append(obj)
    elf, binary = out / 'rio-lt168b-bench.elf', out / 'rio-lt168b-bench.bin'
    run('ld', ['-EL', '--gc-sections', '-e', '__start', '-N', '-T', source / 'linkmap',
               '-Map', out / 'rio-lt168b-bench.map', '-o', elf, *objects,
               '-L' + str(tc / 'mcore-elf/lib/c0_div'),
               '-L' + str(tc / 'lib/gcc/mcore-elf/4.6.0/c0_div'),
               '--start-group', '-lgcc', '-lc', '-lnosys', '--end-group'])
    run('objcopy', ['-O', 'binary', elf, binary])
    (out / 'sections.txt').write_text(run('objdump', ['-h', elf]), encoding='utf-8')
    (out / 'size.txt').write_text(run('size', [elf]), encoding='utf-8')
    hashed = {}
    for label, root in [('source', source), ('sdk', sdk), ('toolchain', tc)]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                hashed[label + '/' + p.relative_to(root).as_posix()] = digest(p)
    for p in sorted((tc.parent / 'bin').glob('*.dll')):
        hashed['toolchain-runtime/' + p.name] = digest(p)
    manifest = dict(qualification='COMPILE ONLY - NOT APPROVED FOR FLASHING',
                    load_address='0x6000A000', compiler=version, commands=commands,
                    inputs=hashed, binary_sha256=digest(binary), binary_size=binary.stat().st_size)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ('qualification', 'binary_sha256', 'binary_size')}))


if __name__ == '__main__':
    main()

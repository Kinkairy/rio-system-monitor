"""Read-only target-ELF layout check; no compiler, USB or firmware writes.

4-byte buffers preserve the proven30780 word-aligned layout. This conservative
contract is not a claim that the LT168 datasheet explicitly forbids byte alignment.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def inspect(path):
    path = Path(path)
    text = subprocess.check_output(['readelf', '-sW', str(path)], text=True)
    required = {'table':512, 'control_out':4, 'control_in':4, 'bulk_out':4, 'bulk_in':4}
    symbols = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[-1] in required:
            name = fields[-1]
            if name in symbols:
                raise ValueError('Duplicate symbol: '+name)
            address, size = int(fields[1],16), int(fields[2])
            alignment = required[name]
            symbols[name] = dict(address=hex(address), size=size,
                                 alignment=alignment, aligned=address%alignment == 0)
    if set(symbols) != set(required):
        raise ValueError('Missing USB layout symbols: '+repr(set(required)-set(symbols)))
    violations = [name for name, item in symbols.items() if not item['aligned']]
    if symbols['bulk_out']['size'] % 64:
        violations.append('bulk_out_packet_stride')
    return dict(elf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), symbols=symbols,
                passed=not violations, violations=violations,
                contract='512-byte EBT alignment; preserve30780 4-byte buffers and64-byte packet stride',
                limit='Address drift is proven; a DMA fault as the historical timeout cause is unproven.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('elf')
    args = parser.parse_args()
    result = inspect(args.elf)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)

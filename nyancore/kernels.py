#!/usr/bin/env python3
"""Run NyanCore's directed performance kernels (sim/tests/perf) on the NyanCore
configuration of XS-GEM5 and compare the whole-run clocks with the RTL pins of
NyanCore's sim/CMakeLists.txt.

Each kernel runs from reset to its tohost store, as `check-cpi` measures it;
tohost is read every cycle.  The differences of the two lengths of a kernel
remove start-up and cold-cache cost: they give the per-link load-to-use time
(pointer-chase), the store-to-load forwarding time (store-load) and the
dependent ALU time (dependent).

usage: kernels.py [--gem5 BIN] [--dir DIR] [-- extra nyancore.py args]
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEM5 = os.path.dirname(HERE)

# Whole-run RTL clocks (sim/CMakeLists.txt of NyanCore at 437fbe9).
PINS = {
    'dependent': 80097,
    'dependent-long': 160108,
    'pointer-chase-1000': 24061,
    'pointer-chase-2000': 48061,
    'store-load-1000': 44087,
    'store-load-2000': 88087,
    'cache-walk': 73794,
    'branch-cost': 1836,
    'divide-mix': 1400068,
}
DIFFS = [
    ('dependent ALU, 8 x 10,000 extra adds', 'dependent-long', 'dependent', 80000),
    ('pointer chase, 8,000 extra links', 'pointer-chase-2000', 'pointer-chase-1000', 8000),
    ('store/load, 8,000 extra pairs', 'store-load-2000', 'store-load-1000', 8000),
]


def run(gem5, elf, out, extra):
    os.makedirs(out, exist_ok=True)
    cmd = [gem5, '-r', '-d', out, os.path.join(GEM5, 'configs/example/nyancore.py'),
           '--elf', elf, '--poll', '1', *extra]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    with open(os.path.join(out, 'simout')) as f:
        simout = f.read()
    m = re.search(r'Exiting @ tick (\d+) because tohost written \(code (\d+)\)', simout)
    if not m:
        return None, simout[-1500:] + res.stdout[-1500:]
    # 1 GHz: a tick is a picosecond.
    return (int(m.group(1)) // 1000, int(m.group(2))), None


def main():
    argv = sys.argv[1:]
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--gem5', default=os.path.join(GEM5, 'build/RISCV/gem5.opt'))
    p.add_argument('--dir', default=os.path.join(HERE, '_work/kern'))
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('names', nargs='*', default=list(PINS))
    args = p.parse_args(argv)

    def one(name):
        return name, run(args.gem5, os.path.join(args.dir, name + '.elf'),
                         os.path.join(args.dir, 'm5out', name), extra)

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
        results = dict(ex.map(one, args.names))
    clocks = {}
    for name in args.names:
        res, err = results[name]
        if res is None:
            print(f'{name:20s} failed\n{err}')
            continue
        cycles, code = res
        clocks[name] = cycles
        pin = PINS[name]
        status = 'pass' if code == 1 else f'tohost={code}'
        print(f'{name:20s} {cycles:>10,} gem5 {pin:>10,} RTL {cycles / pin - 1:+7.2%} {status}')
    for label, a, b, n in DIFFS:
        if a in clocks and b in clocks:
            g = (clocks[a] - clocks[b]) / n
            r = (PINS[a] - PINS[b]) / n
            print(f'{label:40s} {g:6.3f} gem5 {r:6.3f} RTL clocks each')


if __name__ == '__main__':
    main()

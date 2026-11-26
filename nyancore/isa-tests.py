#!/usr/bin/env python3
"""Run the RV32 physical-memory riscv-tests (isa/rv32*-p-*) on the NyanCore
configuration of XS-GEM5 with RiscvISA.rv32.

A test writes 1 to tohost when it passes and (TESTNUM << 1) | 1 when a check
fails; TohostMonitor ends the run with that word as the exit code.

usage: isa-tests.py [--gem5 BIN] [--jobs N] [--out DIR] ISA_DIR [REGEX]

ISA_DIR is riscv-tests/isa built with `make XLEN=32`.  REGEX (default
`rv32.*-p-.*`) selects the tests.
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEM5 = os.path.dirname(HERE)


def run(gem5, elf, out):
    os.makedirs(out, exist_ok=True)
    cmd = [gem5, '-r', '-d', out, os.path.join(GEM5, 'configs/example/nyancore.py'),
           '--elf', elf, '--poll', '10', '--max-ticks', str(2 * 10**9), '--fp']
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with open(os.path.join(out, 'simout')) as f:
            simout = f.read()
    except OSError:
        return 'no output'
    m = re.search(r'because tohost written \(code (\d+)\)', simout)
    if m:
        code = int(m.group(1))
        return 'pass' if code == 1 else f'fail test {code >> 1}'
    for pat in (r'panic: .*', r'fatal: .*', r'Assertion failed.*'):
        m = re.search(pat, simout)
        if m:
            return m.group(0)[:120]
    return 'timeout'


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--gem5', default=os.path.join(GEM5, 'build/RISCV/gem5.opt'))
    p.add_argument('--jobs', type=int, default=8)
    p.add_argument('--out', default=os.path.join(HERE, '_work/isa'))
    p.add_argument('isa_dir')
    p.add_argument('regex', nargs='?', default=r'rv32.*-p-.*')
    args = p.parse_args()

    tests = sorted(f for f in os.listdir(args.isa_dir)
                   if re.fullmatch(args.regex, f) and '.' not in f)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(lambda t: (t, run(args.gem5, os.path.join(args.isa_dir, t),
                                                os.path.join(args.out, t))), tests))
    suites = {}
    for t, r in results:
        suites.setdefault(re.split(r'-[pv]-', t)[0], []).append((t, r))
    failed = 0
    for suite, rs in suites.items():
        bad = [(t, r) for t, r in rs if r != 'pass']
        failed += len(bad)
        print(f'{suite:22s} {len(rs) - len(bad):3d}/{len(rs):<3d} pass')
        for t, r in bad:
            print(f'    {t}: {r}')
    print(f'{len(results) - failed}/{len(results)} pass')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

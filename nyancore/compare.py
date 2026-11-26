#!/usr/bin/env python3
"""Run CoreMark images on the NyanCore configuration of XS-GEM5 and compare the
timed cycles with the Verilated NyanCore RTL.

The RTL figures are NyanCore's GCC 15.2 baseline (docs/performance-baseline.md
of NyanCore at 437fbe9): 16KB 4-way I+D caches, a 2 cycle memory latency,
CoreMark 100 iterations, validated CRC 0x988c, mcycle as the tick counter.

usage: compare.py [--gem5 BIN] [--jobs N] [--out DIR] [-- extra nyancore.py args]
                  IMAGE...

An IMAGE is ELF[:RTL_CYCLES]; the two baseline images are recognised by name
(coremark-*-be_stall.elf and coremark-*-be_stall-zba-zbb.elf of 100
iterations) and need no RTL figure.
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEM5 = os.path.dirname(HERE)

# Timed CoreMark cycles and instructions of the RTL, 100 iterations.
RTL = {
    'rv32ima': (19308825, 24797080),
    'rv32ima_zba_zbb': (19144883, 24359279),
}
TOLERANCE = 0.05


def run(gem5, elf, out, extra):
    os.makedirs(out, exist_ok=True)
    cmd = [gem5, '-r', '-d', out, os.path.join(GEM5, 'configs/example/nyancore.py'),
           '--elf', elf, *extra]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    with open(os.path.join(out, 'simout')) as f:
        simout = f.read()
    pmu = re.search(r'PMU cycles=0x([0-9a-f]+) instret=0x([0-9a-f]+)', simout)
    crc = re.search(r'\[0\]crcfinal\s*:\s*(0x[0-9a-f]+)', simout)
    ok = 'Correct operation validated' in simout and crc is not None
    return {
        'elf': elf, 'out': out, 'rc': res.returncode,
        'validated': ok, 'crc': crc.group(1) if crc else None,
        'cycles': int(pmu.group(1), 16) if pmu else None,
        'instret': int(pmu.group(2), 16) if pmu else None,
        'log': res.stdout[-2000:],
    }


def stats(out, names):
    vals = {}
    try:
        with open(os.path.join(out, 'stats.txt')) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] in names:
                    vals[parts[0]] = parts[1]
    except OSError:
        pass
    return vals


def main():
    argv = sys.argv[1:]
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--gem5', default=os.path.join(GEM5, 'build/RISCV/gem5.opt'))
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--out', default=os.path.join(HERE, '_work/m5out'))
    p.add_argument('images', nargs='+')
    args = p.parse_args(argv)

    jobs = []
    for spec in args.images:
        elf, _, rtl = spec.partition(':')
        name = os.path.basename(elf)
        if rtl:
            ref = (int(rtl), None)
        elif name.endswith('be_stall-zba-zbb.elf'):
            ref = RTL['rv32ima_zba_zbb']
        elif name.endswith('be_stall.elf'):
            ref = RTL['rv32ima']
        else:
            ref = (None, None)
        tag = os.path.basename(os.path.dirname(os.path.abspath(elf))) + '-' + name[:-4]
        jobs.append((elf, os.path.join(args.out, tag), ref))

    worst = 0.0
    failed = False
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(lambda j: (run(args.gem5, j[0], j[1], extra), j[2]), jobs))
    for r, (rtl_cycles, rtl_insts) in results:
        print(f"== {r['elf']}")
        if not r['validated'] or r['cycles'] is None:
            print(r['log'])
            print('   CoreMark did not validate')
            failed = True
            continue
        cm = 100 * 1e6 / r['cycles'] if rtl_insts else None
        line = (f"   gem5: {r['cycles']:,} timed cycles, {r['instret']:,} "
                f"instructions, IPC {r['instret'] / r['cycles']:.3f}, CRC {r['crc']}")
        print(line)
        if rtl_insts and r['instret'] != rtl_insts:
            print(f'   instret differs from the RTL ({rtl_insts:,})')
        if rtl_cycles:
            err = r['cycles'] / rtl_cycles - 1
            worst = max(worst, abs(err))
            iters = 100 if rtl_insts else None
            extra_s = ''
            if iters:
                extra_s = (f", CoreMark/MHz {iters * 1e6 / r['cycles']:.3f} vs "
                           f"{iters * 1e6 / rtl_cycles:.3f}")
            print(f"   RTL:  {rtl_cycles:,} timed cycles; error {err:+.2%}{extra_s}")
        s = stats(r['out'], {
            'system.cpu.commit.branchMispredicts',
            'system.cpu.iew.branchMispredicts',
            'system.cpu.branchPred.condIncorrect',
            'system.cpu.ipc', 'system.cpu.numCycles',
            'system.cpu.icache.overallMisses::total',
            'system.cpu.dcache.overallMisses::total'})
        if s:
            print('   ' + ', '.join(f'{k.split(".", 2)[-1]}={v}' for k, v in sorted(s.items())))
    if worst:
        print(f'worst error {worst:.2%} (tolerance {TOLERANCE:.0%})')
    sys.exit(1 if failed or worst > TOLERANCE else 0)


if __name__ == '__main__':
    main()

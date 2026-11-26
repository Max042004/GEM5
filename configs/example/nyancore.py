# A NyanCore-aligned configuration of the XS-GEM5 O3 core.
#
# NyanCore (github.com/sysprog21/nyancore) is a 32-bit RISC-V core that
# fetches, dispatches and retires two instructions per cycle and issues out
# of order from an eight-entry queue.  This script models it on the
# Kunminghu-derived O3 CPU of XS-GEM5 and runs a bare-metal RV32 ELF the way
# NyanCore's compliance runner does: loaded at 0x80000000, a 16550 UART THR
# at 0xffff1000, stopped by a store to the `tohost` word.
#
#   build/RISCV/gem5.opt configs/example/nyancore.py --elf coremark.elf
#
# The calibration against the Verilated RTL (16KB 4-way I+D caches, a
# 2 cycle memory latency, CoreMark 100 iterations, GCC 15.2 -O3) is in
# nyancore/README.md.

import argparse
import struct
import sys

import m5
from m5.objects import *


# ---------------------------------------------------------------- the image

def elf32_symbol(path, wanted):
    """The value of a symbol of a little-endian ELF32 file, or None."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'\x7fELF' or data[4] != 1:
        sys.exit(f'{path} is not an ELF32 file')
    shoff, = struct.unpack_from('<I', data, 0x20)
    shentsize, shnum = struct.unpack_from('<HH', data, 0x2e)
    sections = [struct.unpack_from('<IIIIIIIIII', data, shoff + i * shentsize)
                for i in range(shnum)]
    for sh in sections:
        if sh[1] != 2:          # SHT_SYMTAB
            continue
        strtab = sections[sh[6]]
        for off in range(sh[4], sh[4] + sh[5], 16):
            name, value = struct.unpack_from('<II', data, off)
            start = strtab[4] + name
            end = data.index(b'\0', start)
            if data[start:end].decode() == wanted:
                return value
    return None


# ------------------------------------------------------------- the back end

# The execution units of NyanCore.  Two instructions issue per cycle, the
# oldest eligible first, at most one per unit: IntExec (ALU operations,
# branches, jumps, CSRs), SecALU (ALU operations, LUI, AUIPC), the LSU, the
# pipelined multiplier and the divider.  An ALU operation can take either
# integer unit, so two ALU ports share one ready queue.
UNIT_SEC, UNIT_INT, UNIT_LSU, UNIT_MUL, UNIT_DIV = range(5)


class NyanALU(FUDesc):
    opList = [OpDesc(opClass='IntAlu', opLat=1)]


class NyanBranch(FUDesc):
    # Branches, jumps, CSR and the other serialized operations of IntExec.
    opList = [OpDesc(opClass='IntBr', opLat=1),
              OpDesc(opClass='IntJp', opLat=1),
              OpDesc(opClass='No_OpClass', opLat=1, pipelined=False),
              OpDesc(opClass='IprAccess', opLat=1, pipelined=False)]


class NyanLSU(FUDesc):
    # Fully pipelined, one access per cycle.  A load's result is forwarded
    # from load pipe S2 (loadBypassAtS2); the equal output distances keep
    # XS-GEM5's per-port writeback check from holding a store behind a load,
    # which NyanCore does not do (stores reserve no write slot).
    opList = [OpDesc(opClass='MemRead', opLat=2),
              OpDesc(opClass='MemWrite', opLat=2),
              OpDesc(opClass='MemAtomic', opLat=2),
              OpDesc(opClass='FloatMemRead', opLat=2),
              OpDesc(opClass='FloatMemWrite', opLat=2)]


class NyanMul(FUDesc):
    opList = [OpDesc(opClass='IntMult', opLat=4)]


class NyanDiv(FUDesc):
    opList = [OpDesc(opClass='IntDiv', opLat=34, pipelined=False)]


def nyan_scheduler(args):
    ports = [
        (IssuePort(fu=[NyanALU()]), UNIT_SEC),
        (IssuePort(fu=[NyanALU()]), UNIT_INT),
        (IssuePort(fu=[NyanBranch()]), UNIT_INT),
        (IssuePort(fu=[NyanLSU()]), UNIT_LSU),
        (IssuePort(fu=[NyanMul()]), UNIT_MUL),
        (IssuePort(fu=[NyanDiv()]), UNIT_DIV),
    ]
    iq = IssueQue(name='nyanIQ', inports=2, size=args.iq_size,
                  oports=[p for p, _ in ports],
                  portUnits=[u for _, u in ports],
                  maxIssuePerCycle=args.issue_width,
                  scheduleToExecDelay=args.schedule_to_exec)
    # XS-GEM5 splits a store into an address and a data uop.  NyanCore's
    # store buffer takes the data from the write ports, so the data uop has
    # a queue of its own outside the issue limit.
    std_iq = IssueQue(name='nyanSTD', inports=2, size=8,
                      oports=[IssuePort(fu=[StoreDataPort()])],
                      scheduleToExecDelay=args.schedule_to_exec)
    iqs = [iq, std_iq]
    if args.fp:
        # Not NyanCore (it has no FP): only to run F/D code, e.g. riscv-tests
        iqs.append(IssueQue(name='nyanFP', inports=2, size=8, oports=[
            IssuePort(fu=[FP_ALU(), FP_MAC()]),
            IssuePort(fu=[FP_MISC(), FP_SLOW(), IntCvt()])],
            scheduleToExecDelay=args.schedule_to_exec))
    sched = Scheduler(IQs=iqs)
    sched.xbarWakeup = True
    sched.enableFpSpecWakeup = False    # no FP units
    return sched


def nyan_cpu(args):
    cpu = RiscvO3CPU()

    # front end: two instructions per cycle from aligned 8-byte pairs
    cpu.fetchWidth = 2
    # XS-GEM5 reads two cache lines per fetch: the line of the fetch address
    # from that address and the start of the next, a buffer of a line plus
    # two bytes (66 for its 64-byte lines, 34 for NyanCore's 32).
    cpu.fetchBufferSize = 34
    cpu.fetchQueueSize = args.fetch_queue
    cpu.enablePredecode = False
    cpu.enableTwoFetch = False
    cpu.decodeBranchRedirect = False
    cpu.fetchToDecodeDelay = args.fetch_to_decode
    cpu.decodeToFetchDelay = 1
    cpu.renameToFetchDelay = 1
    cpu.iewToFetchDelay = args.iew_to_fetch
    cpu.commitToFetchDelay = args.commit_to_fetch
    cpu.commitToDecodeDelay = args.commit_to_fetch
    cpu.commitToRenameDelay = args.commit_to_fetch
    cpu.commitToIEWDelay = args.commit_to_fetch

    # decode, rename and dispatch: two per cycle, no fusion or elimination
    cpu.decodeWidth = 2
    cpu.renameWidth = 2
    cpu.decodeToRenameDelay = 1
    cpu.renameToIEWDelay = args.rename_to_iew
    cpu.enable_loadFusion = False
    cpu.enableConstantFolding = False
    cpu.enableMovImmElimination = False
    cpu.enableMoveElimination = False
    cpu.enableDecodeFusionCompaction = False
    cpu.enableDispatchStage = False
    cpu.numDQEntries = [4, 4, 4]
    cpu.dispWidth = [2, 2, 2]
    # 32 architectural and 16 renaming integer registers; the FP and vector
    # files keep their defaults (unused, but rename needs them free)
    cpu.numPhysIntRegs = 48
    cpu.scheduler = nyan_scheduler(args)

    # retirement: a 16-entry reorder buffer, two per cycle
    # the divider: a fixed 32-step radix-2 loop, not XiangShan's SRT16
    cpu.semanticIntDivLatency = False

    cpu.numROBEntries = args.rob
    cpu.RobCompressPolicy = 'none'
    cpu.CROB_instPerGroup = 1
    cpu.commitWidth = 2
    cpu.squashWidth = args.squash_width
    cpu.phyregReleaseWidth = 2
    cpu.wbWidth = 2
    cpu.iewToCommitDelay = args.iew_to_commit
    cpu.renameToROBDelay = 1

    # memory: eight store slots, loads past older stores of known address
    cpu.LQEntries = 16
    cpu.SQEntries = 8
    cpu.SbufferEntries = args.sbuffer
    cpu.SbufferEvictThreshold = max(1, args.sbuffer - 1)
    cpu.storeBufferInactiveThreshold = 1
    cpu.LdPipeStages = args.ld_pipe
    # NyanCore forwards a hit before writeback: a dependent issues 3 cycles
    # after the load
    cpu.loadBypassAtS2 = True
    cpu.StPipeStages = args.st_pipe
    cpu.StoreWbStage = min(args.st_pipe - 1, 2)
    cpu.cacheLoadPorts = 1
    cpu.cacheStorePorts = 1
    cpu.LoadCompletionWidth = 1
    cpu.StoreCompletionWidth = 1
    cpu.BankConflictCheck = False
    cpu.EnablePHASTMDP = False
    cpu.store_prefetch_train = False

    # the branch predictor: a 512-entry direct-mapped BTB with a 2-bit
    # counter per entry, index pc[10:2] (bank pc[2]), tag pc[20:11], read in
    # the cycle of the fetch address, no RAS and no history
    bp = DecoupledBPUWithBTB()
    bp.predictWidth = 8
    bp.alignedBlockEnd = True
    bp.ftq_size = args.ftq
    bp.fsq_size = args.ftq
    for name in ('ubtb', 'abtb', 'microtage', 'tage', 'ittage', 'mgsc',
                 'ras', 'pairtage'):
        getattr(bp, name).enabled = False
    bp.mbtb = MBTB(numEntries=512, numWays=1, tagBits=10, blockSize=4,
                   numDelay=0, victimCacheSize=0,
                   trainingStage=args.bp_training)
    bp.mbtb.enabled = True
    cpu.branchPred = bp
    return cpu


# ------------------------------------------------------------- the system

def build(args):
    system = System()
    system.mem_mode = 'timing'
    system.cache_line_size = 32
    system.mem_ranges = [AddrRange(start=0x80000000, size='16MB')]
    system.voltage_domain = VoltageDomain()
    system.clk_domain = SrcClockDomain(clock='1GHz',
                                       voltage_domain=system.voltage_domain)

    system.cpu = nyan_cpu(args)
    cpu = system.cpu
    cpu.createThreads()
    for isa in cpu.isa:
        isa.rv32 = True
    # Everything outside RAM is device memory: accessed at the head of the
    # reorder buffer only, so a wrong-path load through a null pointer is
    # squashed before it reaches the bus, as in NyanCore.
    ram = system.mem_ranges[0]
    cpu.mmu.pma_checker = PMAChecker(
        uncacheable=[AddrRange(0, ram.start),
                     AddrRange(ram.end + 1, 0x100000000)])

    # 16KB 4-way caches with 32-byte lines (128 sets)
    cpu.icache = Cache(size='16kB', assoc=4, tag_latency=args.icache_lat,
                       data_latency=args.icache_lat, response_latency=0,
                       mshrs=args.icache_mshrs, tgts_per_mshr=8,
                       is_read_only=True,
                       writeback_clean=False, cache_level=1)
    cpu.dcache = Cache(size='16kB', assoc=4, tag_latency=args.dcache_lat,
                       data_latency=args.dcache_lat, response_latency=0,
                       mshrs=args.dcache_mshrs, tgts_per_mshr=8,
                       writeback_clean=False,
                       cache_level=1, tag_load_read_ports=1,
                       replacement_policy=TreePLRURP(num_leaves=4))
    system.membus = SystemXBar(width=4, frontend_latency=0,
                               forward_latency=0, response_latency=0,
                               snoop_response_latency=0)
    cpu.icache.cpu_side = cpu.icache_port
    cpu.dcache.cpu_side = cpu.dcache_port
    cpu.icache.mem_side = system.membus.cpu_side_ports
    cpu.dcache.mem_side = system.membus.cpu_side_ports
    cpu.mmu.connectWalkerPorts(system.membus.cpu_side_ports,
                               system.membus.cpu_side_ports)
    cpu.createInterruptController()

    # The bus of NyanCore's simulator: a 32-bit beat per cycle after a two
    # cycle latency.
    system.mem_ctrl = SimpleMemory(range=system.mem_ranges[0],
                                   latency=f'{int(args.mem_latency * 1000)}ps',
                                   latency_var='0ns',
                                   bandwidth='4GiB/s')
    system.mem_ctrl.port = system.membus.mem_side_ports

    system.uart = Uart16550(pio_addr=0xffff1000, enable_fifo=False)
    system.uart.pio = system.membus.mem_side_ports
    system.system_port = system.membus.cpu_side_ports

    tohost = elf32_symbol(args.elf, 'tohost')
    if tohost is None:
        sys.exit(f'{args.elf} has no tohost symbol')
    system.tohost = TohostMonitor(tohost=tohost, period=args.poll)

    system.workload = RiscvBareMetal(bootloader=args.elf)
    system.workload.reset_vect = 0x80000000
    return system


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', required=True)
    p.add_argument('--max-ticks', type=int, default=0)
    p.add_argument('--fp', action='store_true',
                   help='add FP units (NyanCore has none) to run F/D code')
    p.add_argument('--poll', type=int, default=1000)
    # calibration knobs, defaults are the calibrated values
    p.add_argument('--iq-size', type=int, default=8)
    p.add_argument('--rob', type=int, default=16)
    p.add_argument('--issue-width', type=int, default=2)
    p.add_argument('--schedule-to-exec', type=int, default=1)
    p.add_argument('--fetch-queue', type=int, default=8)
    p.add_argument('--fetch-to-decode', type=int, default=1)
    p.add_argument('--iew-to-fetch', type=int, default=1)
    # commit ticks before fetch: a redirect reaches fetch in its cycle
    p.add_argument('--commit-to-fetch', type=int, default=0)
    p.add_argument('--rename-to-iew', type=int, default=1)
    p.add_argument('--iew-to-commit', type=int, default=1)
    # NyanCore walks two records a cycle but behind the front-end refill:
    # the walk held dispatch for 0.05% of CoreMark's clocks
    p.add_argument('--squash-width', type=int, default=16)
    # XS-GEM5 frees a fetch target at commit: it must not limit the window
    p.add_argument('--ftq', type=int, default=64)
    p.add_argument('--sbuffer', type=int, default=4)
    p.add_argument('--ld-pipe', type=int, default=4)
    p.add_argument('--st-pipe', type=int, default=5)
    p.add_argument('--icache-lat', type=int, default=1)
    p.add_argument('--dcache-lat', type=int, default=1)
    # the refill path of NyanCore's bus (a two cycle latency and eight
    # 32-bit beats) and caches, calibrated on cache-walk (10: -2.7%,
    # 11: +2.8% of the RTL clocks): ns per access
    p.add_argument('--mem-latency', type=float, default=11)
    # NyanCore's caches block on a miss
    p.add_argument('--icache-mshrs', type=int, default=1)
    p.add_argument('--dcache-mshrs', type=int, default=1)
    p.add_argument('--bp-training', default='Resolve')
    args = p.parse_args()

    root = Root(full_system=True, system=build(args))
    m5.instantiate()
    event = m5.simulate(args.max_ticks) if args.max_ticks else m5.simulate()
    print(f'Exiting @ tick {m5.curTick()} because {event.getCause()} '
          f'(code {event.getCode()})')
    sys.exit(0 if event.getCode() == 1 else 1)


if __name__ == '__m5_main__':
    main()

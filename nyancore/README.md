# NyanCore on XS-GEM5

This directory and `configs/example/nyancore.py` model
[NyanCore](https://github.com/sysprog21/nyancore), a two-wide out-of-order RV32
core, on the O3 CPU of XS-GEM5, front end and back end, and check the model
against NyanCore's Verilated RTL.

## Result

NyanCore's GCC 15.2 baseline (its `docs/performance-baseline.md` at `437fbe9`): 16KB
4-way I+D caches, a 2 cycle memory latency, CoreMark 100 iterations, validated
CRC `0x988c`, `mcycle` as the tick counter.  Both images are the ones of
NyanCore's `scripts/run-coremark` (four HPM events, `-O3` and the runner's flags).

| Application | RTL timed cycles | XS-GEM5 timed cycles | Error | CoreMark/MHz RTL / XS-GEM5 |
| --- | ---: | ---: | ---: | ---: |
| RV32IMA | 19,308,825 | 19,799,331 | +2.54% | 5.179 / 5.051 |
| RV32IMA + Zba/Zbb | 19,144,883 | 19,512,556 | +1.92% | 5.223 / 5.125 |

Both runs print `Correct operation validated` and `crcfinal 0x988c`, and retire
exactly the RTL's timed instructions (24,797,080 and 24,359,279, `minstret`
deltas of the port).  The whole runs mispredict 418,609 and 426,886 branches;
the RTL mispredicts 429,504 on the RV32IMA image.

NyanCore's directed kernels (`sim/tests/perf`, whole-run clocks to the tohost
store, pinned in its `sim/CMakeLists.txt`):

| Kernel | RTL | XS-GEM5 | Error | Per-unit (two lengths) |
| --- | ---: | ---: | ---: | --- |
| dependent (8 adds x 10,000) | 80,097 | 80,125 | +0.03% | 1.000 vs 1.000 clocks per add |
| dependent-long (16 adds) | 160,108 | 160,142 | +0.02% | |
| pointer-chase-1000 | 24,061 | 24,097 | +0.15% | 3.000 vs 3.000 clocks per load-to-use |
| pointer-chase-2000 | 48,061 | 48,097 | +0.07% | |
| store-load-1000 | 44,087 | 48,109 | +9.12% | 6.000 vs 5.500 clocks per store/load pair |
| store-load-2000 | 88,087 | 96,109 | +9.11% | |
| cache-walk (4,096 L1D misses) | 73,794 | 75,886 | +2.83% | |
| branch-cost | 1,836 | 1,745 | -4.96% | |
| divide-mix | 1,400,068 | 1,400,090 | +0.00% | |

## Reproduce

```sh
# XS-GEM5 (macOS: Apple clang and Apple ar; GNU binutils' ar breaks the link)
python3 -m venv .venv && .venv/bin/pip install scons
PATH=$PWD/.venv/bin:/usr/bin:$PATH CC=clang CXX=clang++ \
    scons build/RISCV/gem5.opt -j8 CCFLAGS_EXTRA=-g0

# the images, with the xPack GNU RISC-V toolchain 15.2.0-1 on PATH and a clean
# checkout of CoreMark 1f483d5 (NyanCore's pin)
nyancore/build-coremark.sh NYANCORE_DIR COREMARK_DIR nyancore/_work/elf

# CoreMark against the RTL figures (about 3 minutes per image)
python3 nyancore/compare.py nyancore/_work/elf/*.elf

# the RV32 ISA: riscv-tests built with `make -C isa XLEN=32
# RISCV_PREFIX=riscv-none-elf-`, and the RV32/RV64 decode check
python3 nyancore/isa-tests.py RISCV_TESTS/isa
riscv-none-elf-gcc -march=rv32imafdc_zicsr -mabi=ilp32 -mno-relax -nostdlib \
    -Wl,-N -Ttext=0x80000000 nyancore/tests/rv32-xlen.S -o rv32-xlen.elf
build/RISCV/gem5.opt configs/example/nyancore.py --elf rv32-xlen.elf --fp
python3 nyancore/isa-tests.py RISCV_TESTS/isa 'rv32.*-v-.*'
riscv-none-elf-gcc -march=rv32ima_zicsr -mabi=ilp32 -mno-relax -nostdlib \
    -Wl,-N -Ttext=0x80000000 nyancore/tests/sv32.S -o sv32.elf
build/RISCV/gem5.opt configs/example/nyancore.py --elf sv32.elf

# the directed kernels of NyanCore's sim/tests/perf
nyancore/build-kernels.sh NYANCORE_DIR nyancore/_work/kern
python3 nyancore/kernels.py
```

`compare.py` exits non-zero unless both images validate and stay within 5%.
Any knob of `configs/example/nyancore.py` can be given after `--`, e.g.
`compare.py IMAGE -- --squash-width 2`.

## What NyanCore is, in XS-GEM5 terms

| NyanCore | XS-GEM5 setting |
| --- | --- |
| RV32IMA, Zba, Zbb, Zicsr, M-mode bare metal at 0x80000000 | `RiscvISA.rv32`, `RiscvBareMetal` with the ELF |
| 16550 UART THR at 0xffff1000, stop on `tohost` | `Uart16550(pio_addr=0xffff1000)`, `TohostMonitor` |
| fetch two instructions from an aligned 8-byte pair, stop at a predicted-taken branch | `fetchWidth 2`, `predictWidth 8`, `alignedBlockEnd` |
| 512-entry direct-mapped BTB, index `pc[10:2]` (bank `pc[2]`), tag `pc[20:11]`, 2-bit counter, read with the fetch address | MBTB only: 512 entries, 1 way, 10 tag bits, `blockSize 4`, `numDelay 0`; uBTB, aBTB, TAGE, ITTAGE, SC, RAS off |
| BTB trained at execute; no RAS; a missed JAL resolves at execute | `trainingStage Resolve`, `decodeBranchRedirect False` |
| registered resteer one cycle after the branch executes | `commitTo*Delay 0` (commit ticks before fetch) |
| decode, rename and dispatch of two per cycle, no fusion, no move elimination | widths 2, fusion and eliminations off |
| 8-entry issue queue, two issues per cycle, oldest eligible first, one per unit: IntExec (ALU, branch, CSR), SecALU (ALU), LSU, multiplier, divider | one 8-entry `IssueQue`, six ports on five units, `maxIssuePerCycle 2`, `portUnits` |
| 1-cycle ALU, MUL 4 to a dependent; a fixed 32-step radix-2 divider (35 cycles in NyanCore's notes; `opLat` 34 matches divide-mix to the cycle) | `opLat`; `semanticIntDivLatency False` |
| load-to-use 3 cycles, forwarded before writeback | `loadBypassAtS2` |
| 16-entry ROB, two retirements per cycle, 48 physical registers | `numROBEntries 16`, `commitWidth 2`, `numPhysIntRegs 48` |
| recovery walk two a cycle, hidden behind the front-end refill | `squashWidth 16` |
| eight store slots, split store address/data | `SQEntries 8`, store data in a queue of its own outside the issue limit |
| 16KB 4-way 32-byte-line blocking I and D caches | `Cache(16kB, 4 ways)`, `cache_line_size 32`, one MSHR |
| 32-bit bus, 2 cycle latency, 8 beats a line | `SimpleMemory` 4 GiB/s, `--mem-latency 11` (fitted on cache-walk) |
| device memory accessed only at the ROB head | everything outside RAM uncacheable in the PMA |

## Changes to XS-GEM5

Every new parameter defaults to XS-GEM5's behaviour, so the existing
configurations are unaffected by construction (they were not rerun here).

- **RV32 on the RV64 decoder** (`src/arch/riscv/rv32.hh`, `types.hh`,
  `decoder.cc`, `isa/{operands,bitfields,decoder}.isa`,
  `isa/formats/{mem,amo,standard}.isa`, `insts/standard.hh`, `regs/misc.hh`,
  `isa.cc`, `rvk.hh`, `RiscvISA.py`).  XS-GEM5 forked from gem5 before upstream
  added RV32; this follows upstream gem5's RV32 (`src/arch/riscv` at `9d36889`),
  checked decode point by decode point:
  - every integer register write is sign-extended from bit 31 (one override of
    the ISA parser's `IntReg.makeWrite`), so the RV64 semantics of most
    instructions give the RV32 result; the ones whose low word differs compute
    it: `sll/srl/sra/srli`, `mulh/mulhsu/mulhu`, `divu/remu`, Zbb
    `clz/ctz/cpop/rol/ror/rori/rev8`, Zbs `bset/bclr/binv/bext`, Zbc
    `clmulh/clmulr`, Zbkx `xperm4/xperm8`, and `pack` (RV32's `zext.h`);
  - decode-time choices use a new `ExtMachInst` bit, `RV32`, as upstream's
    `RVTYPE`.  RV64-only encodings are illegal: OP-IMM-32 and OP-32 (`*w`,
    `add.uw`, `sh*add.uw`, ...), `ld/lwu/sd`, the `.d` and `.q` atomics, a
    shift amount with bit 5 set (`slli/srli/srai/rori/bseti/bclri/binvi/bexti`,
    `c.slli/c.srli/c.srai`), `aes64*`, `sha512sum*/sig*`, `fcvt.{l,lu}.*`,
    `fcvt.*.{l,lu}`, `fmv.x.d`, `fmv.d.x`, `c.addw/c.subw/c.zext.w`,
    `hlvx.hu`;
  - RV32-only encodings are decoded: `c.jal`, `c.flw/c.fsw/c.flwsp/c.fswsp`
    (RV64's `c.addiw`, `c.ld/c.sd/c.ldsp/c.sdsp`), Zbkb `zip/unzip/brev8`, Zknh
    `sha512sum0r/sum1r/sig0l/sig0h/sig1l/sig1h` (their helpers copied from
    upstream's `rvk.hh`), Zkne/Zknd `aes32esi/esmi/dsi/dsmi`, Zfa `fmvh.x.d` and
    `fmvp.d.x`;
  - addresses are 32 bits: loads, stores and atomics (compressed ones too),
    `jalr`, jump and branch targets and the sequential next PC;
  - CSRs: writes set 32 bits; `misa` reports MXL = 1 and, as upstream has no
    RV32 hypervisor, no H, and the hypervisor and VS CSRs (address bits 9:8 =
    2), `mtinst` and `mtval2` are illegal; `mstatus`/`sstatus`/`vsstatus` read
    SD at bit 31; `mstatush` is a plain register as in upstream; the counter
    halves (`mcycleh`, `minstreth`, `mhpmcounterNh`, `cycleh`, `timeh`,
    `instreth`, `hpmcounterNh`) and `pmpcfg1`/`pmpcfg3` are the high words of
    the RV64 CSRs; `mcycle`/`minstret` are writable as in upstream (XS-GEM5's
    RV64 keeps ignoring counter writes).

  All RV32 riscv-tests suites that XS-GEM5 can run pass (`isa-tests.py`, 145 of
  the 167 `-p-` tests and 123 of the 145 `-v-` ones under Sv32, the others
  below), and `tests/rv32-xlen.S` checks that 20 RV64-only
  encodings trap and that the RV32-only CSRs, `c.jal` and `misa` behave.  The
  CoreMark output is byte for byte that of NyanCore's software simulator.
- **Sv32** (`tlb.{cc,hh}`, `RiscvTLB.py`, `isa.cc`, `pagetable_walker.hh`):
  neither upstream gem5 (`"Sv32": {"implemented": False}`) nor XS-GEM5 has it,
  and XS-GEM5's walker and L2 TLB are built on Sv39/Sv48's nine-bit levels and
  eight-byte PTEs, so RV32 gets its own path, written from the privileged spec
  with NyanCore's choices where the spec leaves one (`sim/README.md`):
  - `satp` is MODE[31], nine ASID bits and PPN[19:0]: PPN[21:20] read as zero;
  - each of the ITLB and DTLB is `sv32_size` (8, as NyanCore) fully associative
    LRU entries of 4 KiB, keyed on page and ASID (or G); a megapage is cached
    one 4 KiB page at a time and `sfence.vma` with an address in it drops all of
    them; `sfence.vma` ignores the ASID and an address of 0 flushes everything
    (the instruction sees register values, flushing more is allowed);
  - a miss walks the two levels functionally through the walker port, so the
    PTE reads see the D-cache, and in timing mode completes `sv32_miss_latency`
    (6) + `sv32_level_latency` (2) per PTE read cycles later, about NyanCore's
    10 clocks a miss; a hit costs nothing extra;
  - A and D are not set by hardware: A clear, or D clear on a store, is a page
    fault (Svade); a pointer with A, D or U set is a page fault, as is a pointer
    in the last level, a misaligned megapage and W without R; a PTE read that
    PMP denies (an S-mode load) or outside memory, a pointer beyond 32 bits, and
    a permitted page beyond 32 bits are access faults; SUM, MXR and MPRV apply.

  `tests/sv32.S` checks these choices (15 checks); `rv32si-p-dirty` and the
  `-v-` riscv-tests check the rest.  No CoreMark run uses Sv32, so the timing
  of a miss is not fitted against the RTL.
- **Issue limit across ports** (`cpu/o3/issue_queue.{cc,hh}`, `FuncScheduler.py`):
  `IssueQue.maxIssuePerCycle` and `portUnits`.  XS-GEM5 issues one instruction
  per port; with the limit, each round takes the oldest candidate of the ports
  whose unit has not issued this cycle.
- **Aligned prediction blocks** (`cpu/pred/btb/common.hh` and the BTBs,
  `BranchPredictor.py`): `DecoupledBPUWithBTB.alignedBlockEnd` ends a block at the
  next `predictWidth` boundary instead of half-aligned.
- **Decode redirects** (`cpu/o3/decode.{cc,hh}`, `BaseO3CPU.py`):
  `decodeBranchRedirect False` leaves direct jumps and BPU-missed returns to execute.
- **Fixed divide latency** (`cpu/o3/inst_queue.{cc,hh}`): `semanticIntDivLatency
  False` uses the functional unit's `opLat` instead of the SRT16 model.
- **Load bypass at S2** (`cpu/o3/lsq*.{cc,hh}`): `loadBypassAtS2` marks a load's
  result on the bypass network when S2 completes it (a hit or a full forward).
- **`TohostMonitor`** (`src/dev/riscv/`): exits the simulation when the guest
  writes `tohost`, read functionally through the caches.
- **Two fixes**: `BaseCache` sized its way-prediction table for 64-byte lines
  and wrote past it with any other line size (`mem/cache/base.cc`); a statistics
  assertion assumed that only the uBTB/aBTB predict in S1 (`decoupled_bpred_stats.cc`).

## Known differences

- Store-to-load forwarding of a store whose data is still in flight takes 6.0
  clocks per store/load pair against NyanCore's 5.5 (`store-load`).
- NyanCore never lets a load pass an older store of unknown address; XS-GEM5
  predicts with store sets and replays.  The RTL waits on memory order in about
  1% of CoreMark's clocks, and XS-GEM5 saw one ordering violation in 10
  iterations, so the model is at most that much optimistic here.
- NyanCore's two register-file write ports are not arbitrated: XS-GEM5 checks
  writeback slots per issue port only.
- XS-GEM5's front end after a redirect is one cycle shorter than NyanCore's
  (whose fetch holds `resteer_pending` for a cycle), while its decode stage adds
  one cycle before rename; the redirect costs the same in total, 4.0 squash
  cycles per misprediction against the RTL's 4.02 resteer clocks.
- `--mem-latency` is fitted on `cache-walk` rather than derived from the bus
  protocol; CoreMark has about 750 cache misses in all, so it barely matters there.
- The programmable HPM counters read 0: XS-GEM5 does not model NyanCore's events.
- RV32 against upstream gem5, what is left: no Zabha (XS-GEM5 has none in RV64
  either, `rv32uzabha*`); `amocas.d`, which RV32 Zacas defines on register
  pairs, is illegal, as upstream has no Zacas (`rv32uzacas-p-amocas_d`);
  hardware misaligned accesses (`rv32ui-p-ma_data`, which NyanCore's own runner
  skips too); vector code under RV32 is not adapted.  Under the `-v-`
  environment `ma_data` and `amocas_d` end with a simulation error instead of a
  failed test: the environment does not delegate those traps and its M-mode
  handler runs on an unmapped stack.
- The ELFs built on macOS differ from the baseline's SHA-256 (the Linux-built
  toolchain writes other metadata); the code is the same, the software simulator
  counts exactly the baseline's 24,797,080 timed instructions.

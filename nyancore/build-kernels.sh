#!/usr/bin/env bash
# Build NyanCore's directed performance kernels (sim/tests/perf) with the flags
# and tohost address of add_test_elf in NyanCore's sim/CMakeLists.txt.
#
# usage: build-kernels.sh NYANCORE_DIR OUT_DIR
set -euo pipefail

src=$1/sim/tests/perf out=$2
prefix=${RISCV_PREFIX:-riscv-none-elf-}
mkdir -p "$out"
cc=("${prefix}gcc" -mno-relax -march=rv32ima_zicsr -mabi=ilp32 -nostdlib -Wl,-N
    -Wl,--no-warn-rwx-segments -Ttext=0x80000000 -Wl,--section-start=.tohost=0x8000f000)

"${cc[@]}" -o "$out/dependent.elf" "$src/dependent.S"
"${cc[@]}" -DDEPENDENT_ADDS=16 -o "$out/dependent-long.elf" "$src/dependent.S"
for n in 1000 2000; do
  "${cc[@]}" -DITERATIONS=$n -o "$out/pointer-chase-$n.elf" "$src/pointer-chase.S"
  "${cc[@]}" -DITERATIONS=$n -o "$out/store-load-$n.elf" "$src/store-load.S"
done
"${cc[@]}" -o "$out/cache-walk.elf" "$src/cache-walk.S"
"${cc[@]}" -o "$out/branch-cost.elf" "$src/branch-cost.S"
"${cc[@]}" -DMIX -o "$out/divide-mix.elf" "$src/divide.S"
ls "$out"/*.elf

#!/usr/bin/env bash
# Build the CoreMark images of nyancore's scripts/run-coremark, byte for byte:
# the same port (scripts/coremark), the same flags and the four events
# BRANCH,BRANCH_MISPRED,FE_STALL,BE_STALL of the GCC 15.2 baseline.
#
# usage: build-coremark.sh NYANCORE_DIR COREMARK_DIR OUT_DIR [ITERATIONS]
set -euo pipefail

nyan=$1 cm=$2 out=$3 iters=${4:-100}
prefix=${RISCV_PREFIX:-riscv-none-elf-}
port=$nyan/scripts/coremark
mkdir -p "$out"

cflags=(-mabi=ilp32 -mcmodel=medany -O3 -funroll-all-loops -finline-limit=1000
        -fgcse-after-reload -fno-common -ffreestanding -fno-builtin
        -fno-tree-loop-distribute-patterns)

for march in rv32ima_zicsr rv32ima_zicsr_zba_zbb; do
  tag=branch-branch_mispred-fe_stall-be_stall
  [ "$march" = rv32ima_zicsr ] || tag=$tag-zba-zbb
  elf=$out/coremark-$tag.elf
  flags=(-march=$march "${cflags[@]}")
  "${prefix}gcc" -march=rv32ima_zicsr -mabi=ilp32 -c "$port/start.S" -o "$elf.start.o"
  "${prefix}gcc" "${flags[@]}" -DPERFORMANCE_RUN=1 -DITERATIONS="$iters" \
    -DHAS_FLOAT=0 -DHAS_TIME_H=0 -DUSE_CLOCK=0 -DHAS_STDIO=0 -DHAS_PRINTF=0 \
    -DMULTITHREAD=1 -DUSE_PTHREAD=0 -DMEM_METHOD=MEM_STACK \
    "-DFLAGS_STR=\"${flags[*]}\"" -DHPM_EVENTS=3,4,5,6 \
    -include stddef.h -I"$cm" -I"$cm/barebones" -I"$port" -static -nostdlib \
    -nostartfiles -Wl,--no-warn-rwx-segments -T "$port/link.ld" \
    "$cm"/core_list_join.c "$cm"/core_main.c "$cm"/core_matrix.c \
    "$cm"/core_state.c "$cm"/core_util.c "$port/core_portme.c" "$elf.start.o" -o "$elf"
  rm -f "$elf.start.o"
  shasum -a 256 "$elf"
done

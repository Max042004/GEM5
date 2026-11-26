// RV32 decode checks for RiscvISA.rv32 that riscv-tests does not make:
// every RV64-only encoding below must raise an illegal-instruction exception
// (mcause 2), and the RV32-only ones must work.  Writes 1 to tohost when all
// hold, (n << 1) | 1 for the first failing check n otherwise.
//
// riscv-none-elf-gcc -march=rv32imafdc_zicsr -mabi=ilp32 -mno-relax -nostdlib \
//     -Wl,-N -Ttext=0x80000000 rv32-xlen.S -o rv32-xlen.elf

    .section .text
    .globl _start
_start:
    la t0, trap
    csrw mtvec, t0
    li t0, 0x2000           // mstatus.FS = initial, so FP traps mean illegal
    csrs mstatus, t0
    la sp, stack_top
    li s0, 0                // illegal-instruction traps taken
    li s1, 0                // other traps taken

    // RV64-only: OP-IMM-32, OP-32, 64-bit loads/stores, shamt[5], .d AMOs,
    // RV64-only FP conversions and moves, RV64C, hypervisor CSRs, mtinst
    .word 0x0015051b        // addiw a0, a0, 1
    .word 0x0015151b        // slliw a0, a0, 1
    .word 0x00b5053b        // addw a0, a0, a1
    .word 0x02b5053b        // mulw a0, a0, a1
    .word 0x00013503        // ld a0, 0(sp)
    .word 0x00016503        // lwu a0, 0(sp)
    .word 0x00a13023        // sd a0, 0(sp)
    .word 0x02051513        // slli a0, a0, 32
    .word 0x02055513        // srli a0, a0, 32
    .word 0x42055513        // srai a0, a0, 32
    .word 0x62055513        // rori a0, a0, 32
    .word 0x00b1352f        // amoadd.d a0, a1, (sp)
    .word 0xc0257553        // fcvt.l.s a0, fa0
    .word 0xe2050553        // fmv.x.d a0, fa0
    .word 0xf2050553        // fmv.d.x fa0, a0
    .half 0x9d2d            // c.addw a0, a1
    .half 0x9d0d            // c.subw a0, a1
    .half 0x9101            // c.srli a0, 32
    .word 0x60002573        // csrr a0, hstatus
    .word 0x34a02573        // csrr a0, mtinst
    li t0, 20
    li t1, 2
    bne s0, t0, fail

    // RV32-only: these must not trap
    li s0, 0
    csrr a0, mstatush
    csrr a0, mcycleh
    csrr a0, minstreth
    csrr a0, pmpcfg1
    csrr a0, pmpcfg3
    li t1, 3
    bnez s0, fail
    bnez s1, fail

    // c.jal (RV32 decodes it where RV64 has c.addiw) links and jumps
    li ra, 0
    .option push
    .option rvc
    c.jal 1f
    .option pop
4:  j 2f
1:  la t0, 4b               // ra is the address after the c.jal
    li t1, 4
    bne ra, t0, fail
    ret
2:
    // misa reports MXL = 1 and no hypervisor
    csrr a0, misa
    srli a1, a0, 30
    li t1, 5
    li t0, 1
    bne a1, t0, fail
    andi a1, a0, 0x80       // H
    li t1, 6
    bnez a1, fail

    // the counter halves are those of one 64-bit counter
    csrr a0, mcycleh
    csrr a1, mcycle
    csrr a2, mcycleh
    li t1, 7
    bltu a2, a0, fail

    li t0, 1
    j done
fail:
    slli t0, t1, 1
    ori t0, t0, 1
done:
    la t1, tohost
    sw t0, 0(t1)
3:  j 3b

    // Count the illegal-instruction traps and skip the instruction.
    .balign 4
trap:
    csrr t5, mcause
    li t6, 2
    beq t5, t6, 1f
    addi s1, s1, 1
    j 2f
1:  addi s0, s0, 1
2:  csrr t5, mepc
    lhu t6, 0(t5)
    andi t6, t6, 3
    addi t5, t5, 2
    li t4, 3
    bne t6, t4, 3f          // a compressed instruction is two bytes
    addi t5, t5, 2
3:  csrw mepc, t5
    mret

    .section .data
    .balign 16
    .skip 256
stack_top:

    .section .tohost, "aw", @progbits
    .balign 64
    .globl tohost
tohost: .word 0

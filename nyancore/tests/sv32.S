// Sv32 checks for RiscvISA.rv32 that riscv-tests does not make, for the
// choices nyancore makes where the spec leaves one (sim/README.md): no
// hardware A/D update, a pointer with A, D or U set is a page fault, a page
// beyond 32 bits of physical address is an access fault once the
// permissions pass, and satp.PPN[21:20] is read only zero.  M-mode builds
// the tables and runs the checks in S-mode; every S-mode trap goes to M,
// which records mcause and mtval and skips the instruction.  The run writes
// 1 to tohost when all hold, (n << 1) | 1 for the first failing check n.
//
// riscv-none-elf-gcc -march=rv32ima_zicsr -mabi=ilp32 -mno-relax -nostdlib \
//     -Wl,-N -Ttext=0x80000000 sv32.S -o sv32.elf

#define NONE    -1
#define LPF     13          // load page fault
#define SPF     15          // store page fault
#define LAF     5           // load access fault
#define VA      0x40000000  // root slot 0x100 points at l0

// pte(reg) = (pa >> 12) << 10 | flags
.macro PTE dst, pa, flags
    la \dst, \pa
    srli \dst, \dst, 12
    slli \dst, \dst, 10
    ori \dst, \dst, \flags
.endm

// Run one access with s2 = NONE; check n wants mcause \cause
.macro CHECK n, cause
    li t1, \n
    li t0, \cause
    bne s2, t0, fail
.endm

    .section .text
    .globl _start
_start:
    la t0, mtrap
    csrw mtvec, t0
    la s0, root
    la s1, l0

    // root[0x200]: identity megapage over 0x80000000, RWX A D
    li t0, (0x80000 << 10) | 0xcf
    li t2, 0x200 * 4
    add t2, t2, s0
    sw t0, 0(t2)
    PTE t0, l0, 0x01            // root[0x100]: pointer to l0
    sw t0, 0x100 * 4(s0)
    PTE t0, l0, 0x11            // root[0x101]: pointer with U set
    sw t0, 0x101 * 4(s0)
    li t0, ((0x80000 | 1) << 10) | 0x43 // root[0x102]: misaligned megapage
    sw t0, 0x102 * 4(s0)

    PTE t0, page, 0x47          // l0[0]: R W A, D clear
    sw t0, 0(s1)
    PTE t0, page, 0x03          // l0[1]: R, A clear
    sw t0, 4(s1)
    li t0, 0xc0000000 | 0x43    // l0[2]: R A, page beyond 32 bits
    sw t0, 8(s1)
    PTE t0, page, 0x53          // l0[3]: R A U
    sw t0, 12(s1)
    PTE t0, page, 0x49          // l0[4]: X A only
    sw t0, 16(s1)
    PTE t0, page, 0x01          // l0[5]: a pointer in the last level
    sw t0, 20(s1)

    // satp keeps MODE, the nine ASID bits and PPN[19:0]
    li t0, -1
    csrw satp, t0
    csrr t2, satp
    li t0, 0xffcfffff
    li t1, 1
    bne t2, t0, mfail
    srli t0, s0, 12
    li t2, 1 << 31
    or t0, t0, t2
    csrw satp, t0
    sfence.vma

    li t0, 3 << 11              // MPP = M, clear it to S below
    csrc mstatus, t0
    li t0, 1 << 11
    csrs mstatus, t0
    la t0, sstart
    csrw mepc, t0
    mret

sstart:
    li s3, VA
    li s2, NONE
    lw a1, 0(s3)                // R W A page: loads
    CHECK 2, NONE
    li t0, 0x12345678
    li t1, 3
    bne a1, t0, fail
    li s2, NONE
    sw a1, 0(s3)                // D clear: store page fault
    CHECK 4, SPF
    li t1, 5
    bne s4, s3, fail            // mtval is the virtual address
    li s2, NONE
    li t2, VA + 0x1000
    lw a1, 0(t2)           // A clear
    CHECK 6, LPF
    li s2, NONE
    li t2, VA + 0x400000
    lw a1, 0(t2)                // through a pointer with U set
    CHECK 7, LPF
    li s2, NONE
    li t2, VA + 0x800000
    lw a1, 0(t2)                // misaligned megapage
    CHECK 8, LPF
    li s2, NONE
    li t2, VA + 0x2000
    lw a1, 0(t2)           // permitted, but beyond 32 bits
    CHECK 9, LAF
    li s2, NONE
    li t2, VA + 0x3000
    lw a1, 0(t2)           // U page from S without SUM
    CHECK 10, LPF
    li t0, 1 << 18
    csrs sstatus, t0
    li s2, NONE
    li t2, VA + 0x3000
    lw a1, 0(t2)           // and with SUM
    CHECK 11, NONE
    li s2, NONE
    li t2, VA + 0x4000
    lw a1, 0(t2)           // X-only page without MXR
    CHECK 12, LPF
    li t0, 1 << 19
    csrs sstatus, t0
    li s2, NONE
    li t2, VA + 0x4000
    lw a1, 0(t2)           // and with MXR
    CHECK 13, NONE
    li s2, NONE
    li t2, VA + 0x5000
    lw a1, 0(t2)           // a pointer in the level 0 table
    CHECK 14, LPF

    // software sets D, the store goes through after sfence.vma
    lw t0, 0(s1)
    ori t0, t0, 0x80
    sw t0, 0(s1)
    sfence.vma s3
    li s2, NONE
    li a1, 0x5a5a
    sw a1, 0(s3)
    CHECK 15, NONE
    lw a2, 0(s3)
    li t1, 16
    bne a1, a2, fail

    li a0, 1
    ecall
fail:
    slli a0, t1, 1
    ori a0, a0, 1
    ecall

    // An ecall from S ends the run with a0; any other trap is recorded in
    // s2 (mcause) and s4 (mtval) and skipped.
    .balign 4
mtrap:
    csrr t5, mcause
    li t6, 9
    beq t5, t6, done
    mv s2, t5
    csrr s4, mtval
    csrr t5, mepc
    addi t5, t5, 4
    csrw mepc, t5
    mret
mfail:
    slli a0, t1, 1
    ori a0, a0, 1
done:
    la t1, tohost
    sw a0, 0(t1)
1:  j 1b

    .section .data
    .balign 4096
root: .skip 4096
l0:   .skip 4096
page: .word 0x12345678
    .skip 4092

    .section .tohost, "aw", @progbits
    .balign 64
    .globl tohost
tohost: .word 0

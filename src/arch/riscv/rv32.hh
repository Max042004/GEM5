/*
 * RV32 execution on the RV64 decoder.
 *
 * XS-GEM5 only decodes RV64.  With RiscvISA.rv32 set, an RV32 program runs
 * on it the way RV64 runs the W instructions: every integer register holds
 * its 32-bit value sign-extended to 64 bits (the ISA parser sign-extends
 * every integer register write), the few instructions whose low 32 bits
 * differ between the two widths compute the RV32 result, and addresses,
 * jump targets and CSR writes are truncated to 32 bits.  Timing is the
 * same as for any other instruction: only the values change.
 */

#ifndef __ARCH_RISCV_RV32_HH__
#define __ARCH_RISCV_RV32_HH__

#include <cstdint>

namespace gem5
{

namespace RiscvISA
{

/** Set once, from RiscvISA.rv32, before any instruction is decoded. */
extern bool rv32Mode;

/** An address or jump target of the current XLEN. */
inline uint64_t
rvAddr(uint64_t addr)
{
    return rv32Mode ? (uint64_t)(uint32_t)addr : addr;
}

/** A register value of the current XLEN, sign-extended to 64 bits. */
inline uint64_t
rvSext(uint64_t val)
{
    return rv32Mode ? (uint64_t)(int64_t)(int32_t)val : val;
}

/**
 * The RV32 CSR that holds the high word of a 64-bit RV64 CSR, as the CSR of
 * that low word, or 0: the counter halves (mcycleh, minstreth,
 * mhpmcounterNh, cycleh, timeh, instreth, hpmcounterNh) and pmpcfg1/pmpcfg3,
 * the odd configuration registers that RV64 folds into pmpcfg0/pmpcfg2.
 */
inline uint64_t
rv32HighAlias(uint64_t csr)
{
    if ((csr >= 0xB80 && csr <= 0xB9F) || (csr >= 0xC80 && csr <= 0xC9F))
        return csr - 0x80;
    if (csr == 0x3A1 || csr == 0x3A3)
        return csr - 1;
    return 0;
}

/**
 * A CSR that RV32 does not have, as in upstream gem5: the hypervisor and VS
 * CSRs (address bits 9:8 = 2, no RV32 H) and mtinst/mtval2.
 */
inline bool
rv64OnlyCsr(uint64_t csr)
{
    return ((csr >> 8) & 3) == 2 || csr == 0x34A || csr == 0x34B;
}

} // namespace RiscvISA
} // namespace gem5

#endif // __ARCH_RISCV_RV32_HH__

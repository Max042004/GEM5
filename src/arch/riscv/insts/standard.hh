/*
 * Copyright (c) 2015 RISC-V Foundation
 * Copyright (c) 2017 The University of Virginia
 * Copyright (c) 2020 Barkhausen Institut
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef __ARCH_RISCV_STANDARD_INST_HH__
#define __ARCH_RISCV_STANDARD_INST_HH__

#include <string>

#include "arch/riscv/insts/static_inst.hh"
#include "arch/riscv/rv32.hh"
#include "arch/riscv/regs/misc.hh"
#include "cpu/exec_context.hh"
#include "cpu/static_inst.hh"

namespace gem5
{

namespace RiscvISA
{

/**
 * Base class for operations that work only on registers
 */
class RegOp : public RiscvStaticInst
{
  protected:
    using RiscvStaticInst::RiscvStaticInst;

    std::string generateDisassembly(
        Addr pc, const loader::SymbolTable *symtab) const override;
};

/**
 * Base class for Zimop operations, whose encoded sources are not dependencies.
 */
class MopOp : public RiscvStaticInst
{
  protected:
    using RiscvStaticInst::RiscvStaticInst;

    std::string generateDisassembly(
        Addr pc, const loader::SymbolTable *symtab) const override;
};

/**
 * Base class for operations with immediates (I is the type of immediate)
 */
template<typename I>
class ImmOp : public RiscvStaticInst
{
  protected:
    I imm;

    ImmOp(const char *mnem, ExtMachInst _extMachInst, OpClass __opClass)
        : RiscvStaticInst(mnem, _extMachInst, __opClass), imm(0)
    {}

    int64_t getImm() const override {
        return imm;
    }

  public:
    bool isLldpImmediate() const override { return true; }
};

/**
 * Base class for system operations
 */
class SystemOp : public RiscvStaticInst
{
  protected:
    using RiscvStaticInst::RiscvStaticInst;

    std::string generateDisassembly(
        Addr pc, const loader::SymbolTable *symtab) const override;
};

/**
 * Base class for CSR operations
 */
class CSROp : public RiscvStaticInst
{
  protected:
    enum class Ordering { Serialized, WaitForOlder, Unordered };
    Ordering ordering() const;

    uint64_t csr;
    uint64_t uimm;

    bool valid = false;
    RegIndex midx = 0;
    std::string csrName;
    uint64_t maskVal = 0;
    /// An RV32 high counter CSR (mcycleh, ...): the high word of its counter
    bool highHalf = false;

    /// Constructor
    CSROp(const char *mnem, ExtMachInst _extMachInst, OpClass __opClass)
        : RiscvStaticInst(mnem, _extMachInst, __opClass),
            csr(_extMachInst.funct12), uimm(_extMachInst.csrimm)
    {
        uint64_t lookup = csr;
        if (rv32Mode && rv32HighAlias(csr)) {
            lookup = rv32HighAlias(csr);
            highHalf = true;
        }
        auto csr_data_it = CSRData.find(lookup);
        if (csr_data_it == CSRData.end() ||
            (rv32Mode && rv64OnlyCsr(csr)) ||
            (!rv32Mode && csr == CSR_MSTATUSH)) {
            valid = false;
        } else {
            valid = true;
            midx = csr_data_it->second.physIndex;
            csrName = csr_data_it->second.name;
            if (highHalf)
                csrName += "h";
            auto mask_it = CSRMasks.find(lookup);
            if (mask_it == CSRMasks.end())
                maskVal = mask(64);
            else {
                maskVal = mask_it->second;
            }
            // RV32 misa has its MXL in bits 31:30
            if (rv32Mode && lookup == CSR_MISA)
                maskVal = (RegVal(3) << 30) | ISA_EXT_MASK;
        }

        // CSRRW/CSRRWI always write; set/clear forms require a nonzero
        // encoded rs1/zimm field to write.
        if (csr == CSR_SATP &&
            (bits(_extMachInst, 13, 12) == 1 || uimm != 0)) {
            flags[IsSquashAfter] = true;
        }
    }

    std::string generateDisassembly(
        Addr pc, const loader::SymbolTable *symtab) const override;
};

} // namespace RiscvISA
} // namespace gem5

#endif // __ARCH_RISCV_STANDARD_INST_HH__

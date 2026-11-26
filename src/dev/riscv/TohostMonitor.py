# Ends the simulation when a bare-metal guest writes its tohost word, the way
# the riscv-tests and NyanCore's compliance runner do.

from m5.params import *
from m5.proxy import *
from m5.objects.ClockedObject import ClockedObject


class TohostMonitor(ClockedObject):
    type = 'TohostMonitor'
    cxx_header = "dev/riscv/tohost_monitor.hh"
    cxx_class = 'gem5::TohostMonitor'

    system = Param.System(Parent.any, "System whose memory holds tohost")
    tohost = Param.Addr("Physical address of the 32-bit tohost word")
    period = Param.Cycles(1000, "Cycles between two reads of tohost")

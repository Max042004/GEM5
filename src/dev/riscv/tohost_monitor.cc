#include "dev/riscv/tohost_monitor.hh"

#include "base/logging.hh"
#include "mem/port_proxy.hh"
#include "sim/sim_exit.hh"
#include "sim/system.hh"

namespace gem5
{

TohostMonitor::TohostMonitor(const Params &p)
    : ClockedObject(p), system(p.system), tohost(p.tohost),
      period(p.period), pollEvent([this] { poll(); }, name())
{
}

void
TohostMonitor::startup()
{
    schedule(pollEvent, clockEdge(period));
}

void
TohostMonitor::poll()
{
    uint32_t value = system->physProxy.read<uint32_t>(tohost);
    if (value != 0) {
        inform("tohost %#x = %#x\n", tohost, value);
        exitSimLoop("tohost written", value);
        return;
    }
    schedule(pollEvent, clockEdge(period));
}

} // namespace gem5

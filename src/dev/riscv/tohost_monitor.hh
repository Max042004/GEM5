#ifndef __DEV_RISCV_TOHOST_MONITOR_HH__
#define __DEV_RISCV_TOHOST_MONITOR_HH__

#include "params/TohostMonitor.hh"
#include "sim/clocked_object.hh"
#include "sim/eventq.hh"

namespace gem5
{

class System;

/**
 * Reads the guest's tohost word functionally (through the caches, so a
 * store that has not been written back is seen) every `period` cycles and
 * exits the simulation loop with the word as the exit code once it is not
 * zero.  The reads have no timing effect on the simulated system.
 */
class TohostMonitor : public ClockedObject
{
  public:
    PARAMS(TohostMonitor);
    explicit TohostMonitor(const Params &p);

    void startup() override;

  private:
    void poll();

    System *system;
    const Addr tohost;
    const Cycles period;
    EventFunctionWrapper pollEvent;
};

} // namespace gem5

#endif // __DEV_RISCV_TOHOST_MONITOR_HH__

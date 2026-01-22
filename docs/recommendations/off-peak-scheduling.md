# Off-Peak Test Scheduling

## Priority: Tier 2 - Infrastructure

**Status**: 📝 Placeholder - Detailed guide to be written

**Impact**: Medium - Smooth demand curve, reduce peak-hour contention
**Effort**: Low - Policy and configuration changes
**Cost**: Free
**Timeline**: 1 week

## Overview

This document will provide guidance on implementing intelligent test scheduling to shift non-critical tests to off-peak hours when infrastructure is more reliable.

## Planned Content

- [ ] Test priority classification (blocking vs optional)
- [ ] Time-of-day scheduling policies
- [ ] Prow priority and queue configuration
- [ ] Developer opt-in mechanisms
- [ ] Monitoring and effectiveness tracking

## Key Data Points

From [Time Cost Analysis](../findings/time-cost.md):

- **Best success rate**: 70.8% (5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT)
- **Worst success rate**: 52.6% (3 PM UTC / 10 AM EST / 11 AM EDT)
- **Variance**: 21% difference between peak and off-peak

## Strategy

### High-Priority Tests (Always Run Immediately)
- Blocking presubmits
- Tests required for merge
- Developer-triggered `/test` commands

### Low-Priority Tests (Can Schedule Off-Peak)
- Optional validation jobs
- Periodic tests
- Nightly builds
- Performance tests

## Benefits

- Reduce peak-hour congestion
- Better resource utilization
- Higher overall success rate
- No additional infrastructure cost

## References

- [Time Cost Analysis](../findings/time-cost.md) - Time-of-day data
- [Infrastructure Issues](../findings/infrastructure.md) - Peak hour analysis

## Status

This is a **Tier 2 recommendation** - free to implement, works well alongside peak-hour capacity.

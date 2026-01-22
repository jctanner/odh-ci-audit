# Peak-Hour Capacity

## Priority: Tier 2 - Infrastructure

**Status**: 📝 Placeholder - Detailed guide to be written

**Impact**: High - Improve peak-hour success rate from 52-58% → 70%+
**Effort**: High - Infrastructure provisioning and configuration
**Cost**: $15K-25K/month (additional cloud spend)
**Timeline**: 2-4 weeks

## Overview

This document will provide detailed guidance on adding cluster capacity during peak usage hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT) to match off-peak reliability.

## Planned Content

- [ ] Current capacity analysis and bottlenecks
- [ ] Autoscaling configuration for peak hours
- [ ] Node pool sizing recommendations
- [ ] Cost analysis and optimization strategies
- [ ] Monitoring and alerting setup
- [ ] Rollback procedures

## Key Data Points

From [Time Cost Analysis](../findings/time-cost.md) and [CI Pipeline Issues](../findings/ci-pipeline.md):

- **Peak-hour success rate**: 52-58% (vs 70%+ off-peak)
- **Time-of-day variance**: 21% difference between best and worst times
- **Estimated capacity gap**: Need 25-30% more capacity during business hours
- **Estimated cost**: $15K-25K/month for additional nodes

## References

- [Infrastructure Issues](../findings/infrastructure.md) - Root cause data
- [Time Cost Analysis](../findings/time-cost.md) - Peak hour analysis
- [CI Pipeline Issues](../findings/ci-pipeline.md) - Recommendations context

## Status

This is a **Tier 2 recommendation** - should be implemented AFTER Tier 1 quick wins (auto-retry, fail-fast, timeout strategy, infrastructure visibility).

**Do Tier 1 first** to validate the 25-30% capacity gap is still accurate after those improvements.

# Smart Retry Timing

## Priority: Tier 3 - Process & Monitoring

**Status**: 📝 Placeholder - Detailed guide to be written

**Impact**: Low-Medium - Higher retry success rate
**Effort**: Medium - Logic implementation
**Cost**: Free
**Timeline**: 1-2 weeks

## Overview

This document will provide guidance on implementing time-aware retry strategies that avoid retrying during peak hours when infrastructure is likely to fail again.

## Planned Content

- [ ] Time-of-day retry logic
- [ ] Integration with auto-retry system
- [ ] Configuration and tuning
- [ ] Effectiveness monitoring
- [ ] Edge cases and fallbacks

## Core Concept

**Problem**: Tests that fail during peak hours (1-4 PM UTC) often fail again on immediate retry because infrastructure is still degraded.

**Solution**: Delay retry until off-peak hours when success probability is higher.

## Strategy

### Immediate Retry (Infrastructure Healthy)
- Off-peak hours (5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT): Retry in 2-5 minutes
- Success rate: 70%+

### Delayed Retry (Infrastructure Degraded)
- Peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT): Delay 30-60 minutes
- Wait for infrastructure to recover
- Success rate improvement: 52% → 70%

## Integration

Works with [Auto-Retry Configuration](auto-retry-configuration.md):

```python
def calculate_retry_delay(failure_time):
    hour_utc = failure_time.hour

    # Peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT) - delay longer
    if 13 <= hour_utc <= 16:
        return 30  # minutes - wait for peak to pass

    # Off-peak - retry quickly
    elif 5 <= hour_utc <= 7:
        return 2  # minutes - infrastructure is healthy

    # Default
    else:
        return 5  # minutes
```

## Expected Impact

- **Retry success rate**: Improve from ~60% → 75%
- **Wasted retries**: Reduce retries that fail again
- **Developer experience**: Fewer retry loops

## References

- [Time Cost Analysis](../findings/time-cost.md) - Time-of-day success rates
- [Auto-Retry Configuration](auto-retry-configuration.md) - Base retry system

## Status

This is a **Tier 3 recommendation** - nice-to-have optimization after auto-retry is working.

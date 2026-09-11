# Fixed-release batch read benchmark

On 2026-09-11, the current release `R12be9654e692afed` was read locally for
the 20 low-Beta holdings on `2023-09-01`, requesting `close` and `paused`.
No network operation occurred.

| Measurement | Result |
| --- | ---: |
| First read | 115.804 ms |
| Warm reads | 15.316 / 13.205 / 13.164 ms |
| Warm median | 13.205 ms |
| Base-price calls | 4 |
| Status SQL calls | 1 |
| Supplementary status rows read | 20 |

The cache key includes fixed `release_id`, requested securities, date window,
and count.  It therefore cannot cross a release boundary.  Price data remains
read once per public request; this measurement proves only that the repeated
status-patch lookup is cached, not a claim that all backtest work is cached.

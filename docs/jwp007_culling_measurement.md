# JWP007 Culling Measurement

Date: 2026-09-11

Scope: local CPU timing for static visibility candidate generation and draw command creation.
This is not a GPU, browser compositing, or iPhone result.

Command:

```sh
.venv/bin/python scripts/measure_culling.py --iterations 600
```

| Extra Details | Ground Details | Candidate Chunks | Candidate Objects | Visible Objects | Visible Details | Draw Commands | Median ms | p95 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 64 | 25 | 13 | 9 | 16 | 30 | 1.5213 | 1.5577 |
| 128 | 192 | 25 | 13 | 9 | 51 | 65 | 1.7311 | 1.7607 |
| 512 | 576 | 25 | 13 | 9 | 153 | 167 | 2.3583 | 2.3966 |

Notes:

- The active enemy count for the measured spawn view was 1.
- The measurement uses `Renderer.world_commands()` with a dummy Pyxel object, so it records Python-side culling and command preparation only.
- iPhone Safari, actual draw cost, audio, and browser frame pacing remain manual verification items.

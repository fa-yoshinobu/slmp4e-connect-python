# Project Status

## Current Scope

This repository implements Mitsubishi SLMP in:

- `4E` frame only
- binary mode only

Not implemented:

- `3E`
- ASCII mode

## Current Baseline

Primary validated target:

- Mitsubishi MELSEC iQ-R `R08CPU`
- host `192.168.250.101`
- `TCP 1025`
- `UDP 1027`
- `series=iqr`

Latest mixed-block live note on the validated target:

- mixed `write_block(...)` as one `1406/0002` request was reproduced as `0xC05B`
- equivalent word-only and bit-only block writes were both `OK`
- `retry_mixed_on_error=True` was live-verified as a working fallback

## Implemented Areas

- normal device read/write
- random read/write
- block read/write
- monitor entry/execute
- memory read/write
- extend-unit read/write
- label read/write
- remote control
- password lock/unlock
- self test
- major file-command helpers
- Appendix 1 typed builders
- practical helpers for long timers and CPU buffer access

## Current Practical Guidance

Prefer these APIs on the validated iQ-R target:

- `read_long_timer(...)`
- `read_long_retentive_timer(...)`
- `read_ltc_states(...)`
- `read_lts_states(...)`
- `read_lstc_states(...)`
- `read_lsts_states(...)`
- `cpu_buffer_read_*` / `cpu_buffer_write_*` only as a target-specific workaround, not as a generally portable feature
- `write_block(..., split_mixed_blocks=True)` or `write_block(..., retry_mixed_on_error=True)` when a target rejects one mixed word+bit block write

Do not treat these as reliable on the current validated target:

- direct `G`
- direct `HG`
- direct `S`
- direct `LTC/LTS/LSTC/LSTS` reads
- Appendix 1 access as a general feature
- file-command workflows as a stable feature
- ondemand receive as a routine verified application path

## Where to Look Next

- start with [README.md](README.md) and [USER_GUIDE.md](USER_GUIDE.md)
- use [TESTING.md](TESTING.md) for verification procedure
- use [internal_docs/open_items.md](internal_docs/open_items.md) for unresolved items
- use [internal_docs/manual_implementation_differences.md](internal_docs/manual_implementation_differences.md) for manual-vs-live decisions
- use [internal_docs/iqr_r08cpu/README.md](internal_docs/iqr_r08cpu/README.md) for the validated-target report index

## Release Gate

Minimum local checks:

- `python -m unittest discover -s tests -v`
- `python -m ruff check .`
- `python -m mypy slmp4e scripts`

Minimum live check:

- `python scripts/slmp_connection_check.py --host <host> --port <port> --transport tcp --series <series>`

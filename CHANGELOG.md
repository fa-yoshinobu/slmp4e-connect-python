# Changelog

All notable changes to this project will be documented in this file.

## 0.1.2 - 2026-03-14

Patch release to align the repository release tag with the CI-passing commit.

### Fixed

- formatted `scripts/slmp_mixed_block_compare.py` so `ruff check .` passes in GitHub Actions
- release line now points to the same commit that passed unit tests, `ruff`, `mypy`, and package build

## 0.1.1 - 2026-03-14

Mixed block write compatibility update for the validated iQ-R target.

### Added

- `retry_mixed_on_error=True` fallback for `write_block(...)` so one mixed `1406/0002` write can recover by retrying as separate word-only and bit-only block writes on known rejection end codes
- `scripts/slmp_mixed_block_compare.py` for focused live comparison of mixed block read/write behavior
- focused unit tests for the mixed-write retry path
- validated-target comparison notes under `internal_docs/iqr_r08cpu/`

### Changed

- documentation now records that one-request mixed `writeBlock` on the validated `R08CPU` target reproduces `0xC05B`
- practical guidance now recommends `split_mixed_blocks=True` or `retry_mixed_on_error=True` when a PLC rejects one mixed word+bit block write
- project status and open-items tracking were updated with the latest live verification result

### Live Validation

- one-request mixed `writeBlock(D300 x2 + M200 x1 packed)` reproduced `0xC05B`
- equivalent word-only and bit-only block writes remained `OK`
- `retry_mixed_on_error=True` was live-verified as a working fallback on the validated target

## 0.1.0 - 2026-03-13

Initial packaged release for the current repository scope.

### Added

- 4E binary SLMP frame encoder/decoder
- TCP and UDP client support
- typed APIs for:
  - normal device read/write
  - random read/write
  - block read/write
  - monitor entry/execute
  - memory read/write
  - extend-unit read/write
  - label command family
  - remote control
  - password lock/unlock
  - self test
  - major file commands
- Appendix 1 typed extension builders and access APIs
- practical helper APIs for:
  - long timer / long retentive timer decoding
  - `LTC/LTS/LSTC/LSTS` state helpers
  - CPU buffer read/write via the verified `0601/1601` path
- CLI entry points for:
  - base connection check
  - device-range boundary probe
  - focused register-boundary probe
  - other-station verification
  - open-item recheck
  - pending live verification

### Changed

- documentation split into user-facing guides and internal implementation-facing records
- generated live reports moved under `internal_docs/<series>_<model>/`
- current live reports now keep a tracked `*_latest.md` plus a timestamped `archive/` copy

### Validated Environment

- Mitsubishi MELSEC iQ-R `R08CPU`
- Host `192.168.250.101`
- `TCP 1025`
- `UDP 1027`
- library mode `series=iqr`

### Known Limitations

- 3E frame is not implemented
- ASCII protocol is not implemented
- some paths remain target-specific and unresolved on the validated iQ-R target
- current unresolved items are tracked in `internal_docs/open_items.md`

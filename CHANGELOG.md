# Changelog

All notable changes to this project will be documented in this file.

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

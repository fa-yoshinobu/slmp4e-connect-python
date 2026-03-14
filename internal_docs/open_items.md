# Open Items

## Last Updated

- date: 2026-03-14
- PLC: Mitsubishi MELSEC iQ-R `R08CPU`
- host: `192.168.250.101`
- main transports: `TCP 1025`, `UDP 1027`

## 1. Active Unresolved Items

### `S` bit write

- current result: `S0` direct bit write returns `0x4030`
- read is OK, write is not
- current project handling: typed device APIs intentionally reject `S`

### `G/HG` direct and Appendix 1 access

- direct `G0` / `HG0` is still rejected
- Appendix 1 `G/HG` is still rejected on the validated target
- current project handling: typed device APIs intentionally reject `G` and `HG`
- currently verified practical alternative:
  - `cpu_buffer_read_*` / `cpu_buffer_write_*`
  - backed by `0601/1601` with `module_no=0x03E0`

### File command family (`18xx`)

- current result:
  - `1810`, `1811`, `1824` -> `0xC061`
  - `1820`, `1827`, `1825`, `1822` -> `0x413E`
  - `1826` -> `0xC207`
  - `1828`, `1829`, `182A` -> `SKIP` because the file handle never opened
- current interpretation:
  - this family is still blocked by the PLC file environment or accepted-condition rules

### Mixed block write root cause

- current result on the validated target:
  - one-request mixed `write_block(D300 x2 + M200 x1 packed)` returned `0xC05B`
  - the first failed mixed write left PLC memory unchanged
  - `retry_mixed_on_error=True` then succeeded by retrying as separate word-only and bit-only writes
- current project handling:
  - default behavior still sends one mixed request so the original PLC behavior is observable
  - practical fallbacks are available:
    - `split_mixed_blocks=True`
    - `retry_mixed_on_error=True`
- remaining unknown:
  - why this PLC rejects the one-request mixed `1406` even though the request shape is manual-aligned

### `1617` clear error visual effect

- request acceptance is confirmed: `end_code=0x0000`
- the operator-visible effect is still not pinned down
- treat transport-level verification as complete, but leave the human-facing meaning as a low-priority follow-up

## 2. Confirmed but Conditional Behavior

### Label command family

- `041A`, `141A`, `041C`, and `141B` are confirmed when the label is real and externally accessible
- verified examples:
  - random: `DDD[0]`, `EEE[0,0]`, `FFF[0,0,0]`
  - array: `DDD[0]:1:20`, `EEE[0,0]:1:20`, `FFF[0,0,0]:1:20`
- if you see `0x40C0`, first check:
  - label exists
  - `Access from External Device` is enabled

### Remote control family

- confirmed OK:
  - `1001` remote run
  - `1002` remote stop
  - `1003` remote pause
- `1005` remote latch clear is state-dependent
  - `0x4013` was observed outside the accepted state
  - `0x0000` was confirmed with the PLC in `STOP`
- `1006` remote reset is intentionally outside the routine live-verification workflow

### Password lock/unlock

- lock and unlock are both confirmed
- while the password is enabled:
  - unauthenticated `0101` and normal `0401` returned `0xC201`
- operator note:
  - the normal daily environment is usually unlocked

### Mixed block write compatibility

- `readBlock words+bits` on `D300 x2 + M200 x1 packed` is confirmed
- `writeBlock words only` and `writeBlock bits only` are both confirmed
- one-request `writeBlock mixed` is conditionally rejected with `0xC05B` on the validated target
- the practical workaround is confirmed:
  - `split_mixed_blocks=True`
  - `retry_mixed_on_error=True`

### Ondemand

- `2101` is treated as out of scope for normal testing in this project
- it is PLC-initiated and is not used as a normal external-device request

## 3. End-Code Memo

| End code | Current practical meaning |
| --- | --- |
| `0x4013` | command rejected in current PLC state |
| `0x4030` | selected device/path rejected |
| `0x4031` | configured range/allocation mismatch |
| `0x40C0` | label-side condition failure |
| `0xC05B` | direct `G/HG` path rejected, or one-request mixed `1406` block write rejected |
| `0xC061` | request content/path not accepted in the current environment |

Use [error_code_reference.md](error_code_reference.md) for the fuller table.

## 4. Recommended Next Work

If you want to close the remaining practical gaps, the natural order is:

1. explain `S` write rejection
2. explain actual `G/HG` accepted conditions on the validated PLC
3. explain the PLC-side acceptance condition for one-request mixed `1406` block writes
4. determine the PLC-side prerequisites for the file family

## 5. Related Documents

- [communication_test_record.md](communication_test_record.md)
- [manual_implementation_differences.md](manual_implementation_differences.md)
- [iqr_r08cpu/pending_live_verification_latest.md](iqr_r08cpu/pending_live_verification_latest.md)
- [iqr_r08cpu/special_device_probe_latest.md](iqr_r08cpu/special_device_probe_latest.md)
- [iqr_r08cpu/manual_label_verification_latest.md](iqr_r08cpu/manual_label_verification_latest.md)
- [iqr_r08cpu/mixed_block_compare_latest.md](iqr_r08cpu/mixed_block_compare_latest.md)
- [iqr_r08cpu/slmp4e_connect_python_comparison_checklist.md](iqr_r08cpu/slmp4e_connect_python_comparison_checklist.md)

# Scripts

This folder contains thin wrappers around `slmp4e.cli`.

You can use either:

- `python scripts/<name>.py ...`
- the installed console entry point

Use [TESTING.md](../TESTING.md) for when to run each script and [USER_GUIDE.md](../USER_GUIDE.md) for API-side context.

## Start Here

If you only need a safe first check, use:

- `slmp_connection_check.py`

If you need to validate unresolved behavior, use:

- `slmp_open_items_recheck.py`
- `slmp_pending_live_verification.py`
- `slmp_special_device_probe.py`
- `slmp_mixed_block_compare.py`

If you need human confirmation, use:

- `slmp_manual_write_verification.py`
- `slmp_manual_label_verification.py`

## Script List by Purpose

### Setup and housekeeping

- `slmp_init_model_docs.py`
  - Create `internal_docs/<series>_<model>/`.
- `slmp_device_access_matrix_sync.py`
  - Render `device_access_matrix.md` from `device_access_matrix.csv`.

### Safe connection and scope checks

- `slmp_connection_check.py`
  - Basic communication check and harmless command smoke test.
- `slmp_other_station_check.py`
  - Verify explicit target-header access to other network/station combinations.

### Rechecks for maintained open areas

- `slmp_open_items_recheck.py`
  - Re-run the current unresolved item set.
- `slmp_pending_live_verification.py`
  - Re-check maintained command families.
  - Current workflow excludes `1006 remote reset` and treats `2101` as out of scope.
- `slmp_special_device_probe.py`
  - Focused recheck for `G/HG` and `LT/LST` related paths.
- `slmp_mixed_block_compare.py`
  - Checklist-oriented live compare for word-only, bit-only, and mixed `0406/1406` block access.

### Human-in-the-loop verification

- `slmp_manual_write_verification.py`
  - Temporary write/restore check for representative devices from the matrix.
- `slmp_manual_label_verification.py`
  - Temporary write/restore check for explicitly named labels.

### Automated write/read/restore probes

- `slmp_supported_device_rw_probe.py`
  - Automated probe across currently supported writable device families.

### Boundary and range probes

- `slmp_device_range_probe.py`
  - Probe configured device-family upper boundaries.
- `slmp_register_boundary_probe.py`
  - Probe focused register-boundary edge cases.

### Load and performance

- `slmp_read_soak.py`
  - Repeated single-command read soak.
- `slmp_mixed_read_load.py`
  - Mixed `0401` / `0403` / `0406` load.
- `slmp_tcp_concurrency.py`
  - Practical multi-client TCP concurrency test.

## Notes

- Most scripts write a `*_latest.md` report under `internal_docs/<series>_<model>/`.
- Interactive scripts temporarily change PLC values; read [TESTING.md](../TESTING.md) first.
- Packet captures and raw communication logs are local-only and must not be committed.

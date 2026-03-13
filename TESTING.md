# Testing Guide

This guide explains what to run locally, what to run on a live PLC, and what should be committed afterward.

## 1. What Most Changes Need

For most code changes, the minimum useful sequence is:

1. run unit tests
2. run `ruff`
3. run `mypy`
4. run one safe live smoke check on the target PLC

Only run the heavier live scripts when the change actually touches that area.

## 2. Setup

```powershell
python -m pip install -e ".[dev]"
```

Optional:

```powershell
pre-commit install
```

## 3. Local Checks

Run these from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy slmp4e scripts
```

Recommended pass criteria:

1. unit tests pass
2. `ruff` reports no errors
3. `mypy` reports no errors

## 4. CLI Smoke Checks

Use these when changing `slmp4e.cli`, script wrappers, or packaging:

```powershell
python scripts/slmp_connection_check.py --help
python scripts/slmp_device_range_probe.py --help
python scripts/slmp_register_boundary_probe.py --help
python scripts/slmp_device_access_matrix_sync.py --help
python scripts/slmp_init_model_docs.py --help
python scripts/slmp_other_station_check.py --help
python scripts/slmp_open_items_recheck.py --help
python scripts/slmp_pending_live_verification.py --help
python scripts/slmp_manual_write_verification.py --help
python scripts/slmp_manual_label_verification.py --help
python scripts/slmp_supported_device_rw_probe.py --help
python scripts/slmp_special_device_probe.py --help
python scripts/slmp_read_soak.py --help
python scripts/slmp_mixed_read_load.py --help
python scripts/slmp_tcp_concurrency.py --help
```

Installed entry points are listed in [scripts/README.md](scripts/README.md).

## 5. Live Test Environment

Current project example target:

- PLC: Mitsubishi MELSEC iQ-R `R08CPU`
- host: `192.168.250.101`
- TCP: `1025`
- UDP: `1027`
- series: `iqr`

Replace these values when testing another PLC.

If you add a new target folder first:

```powershell
python scripts/slmp_init_model_docs.py --series iqr --model R16CPU
```

## 6. Safe Live Order

Use this order unless you have a reason not to:

1. `slmp_connection_check.py` over TCP
2. optional `slmp_connection_check.py` over UDP
3. `slmp_open_items_recheck.py` if you touched unresolved behavior
4. `slmp_pending_live_verification.py` if you touched command-family support
5. a focused script only for the area you changed

This keeps destructive or noisy checks until the end.

## 7. Safe Smoke Tests

TCP:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

TCP with a harmless device read:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --read-device D1000 --points 1
```

UDP:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1027 --transport udp --series iqr
```

Expected result:

1. `0101` succeeds
2. model and model code are printed
3. optional device read succeeds if the device is valid

## 8. Focused Live Scripts

### Device Range Boundary Probe

Use this after PLC-side device-range settings changed:

```powershell
python scripts/slmp_device_range_probe.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --spec-file internal_docs/iqr_r08cpu/current_plc_boundary_specs_20260313.txt --include-writeback
```

Report:

- `internal_docs/<series>_<model>/device_range_probe_latest.md`

### Register Boundary Probe

Use this for `Z`, `LZ`, `R`, `ZR`, and `RD` edge behavior:

```powershell
python scripts/slmp_register_boundary_probe.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --spec-file internal_docs/iqr_r08cpu/current_register_boundary_focus_specs_20260313.txt
```

Report:

- `internal_docs/<series>_<model>/register_boundary_probe_latest.md`

### Other-Station Check

Use this to validate explicit target headers:

```powershell
python scripts/slmp_other_station_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --target remote1,0x00,0x01,0x03FF,0x00
```

Report:

- `internal_docs/<series>_<model>/other_station_check_latest.md`

### Open-Item Recheck

Use this when you changed an unresolved area:

```powershell
python scripts/slmp_open_items_recheck.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

Report:

- `internal_docs/<series>_<model>/open_items_recheck_latest.md`

### Pending Command-Family Verification

Use this when you changed implemented command-family behavior:

```powershell
python scripts/slmp_pending_live_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

If you have real external-device-accessible labels, override the placeholders:

```powershell
python scripts/slmp_pending_live_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-random DDD[0] --label-array DDD[0]:1:20
```

Notes:

- `1006 remote reset` is intentionally outside routine live verification
- `2101` is PLC-initiated and remains out of scope for the normal pending workflow
- `0x40C0` on labels usually means the label is missing or external access is not enabled

Report:

- `internal_docs/<series>_<model>/pending_live_verification_latest.md`

### Special Device Probe

Use this for `G/HG` and `LT/LST` related open items:

```powershell
python scripts/slmp_special_device_probe.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

Report:

- `internal_docs/<series>_<model>/special_device_probe_latest.md`

### Supported-Device Write/Read/Restore Probe

Use this for automated smoke checks of the currently supported writable families:

```powershell
python scripts/slmp_supported_device_rw_probe.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

### Performance Scripts

Read soak:

```powershell
python scripts/slmp_read_soak.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --device D1000 --rounds 5000 --rotate-span 200
```

Mixed read load:

```powershell
python scripts/slmp_mixed_read_load.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --base-device D1000 --rounds 2000
```

TCP concurrency:

```powershell
python scripts/slmp_tcp_concurrency.py --host 192.168.250.101 --port 1025 --series iqr --device D1000 --clients 1,2,4,8,16,32 --rounds-per-client 100
```

## 9. Human-in-the-Loop Checks

### Manual Write Verification

Use this to temporarily write representative devices from the matrix:

```powershell
python scripts/slmp_manual_write_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --matrix internal_docs/iqr_r08cpu/device_access_matrix.csv --device-code D --device-code M
```

Resume from the last report:

```powershell
python scripts/slmp_manual_write_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --matrix internal_docs/iqr_r08cpu/device_access_matrix.csv --resume-from-report internal_docs/iqr_r08cpu/manual_write_verification_latest.md
```

### Manual Label Verification

Use this for explicit labels rather than the matrix:

```powershell
python scripts/slmp_manual_label_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-random LabelB --label-random LabelW --label-array DDD[0]:1:20
```

Both scripts:

1. read the current value
2. write a temporary value
3. wait for human judgement
4. restore the original value unless told otherwise

## 10. Appendix 1 Checks

Use Appendix 1 checks only when your change touches that area:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --appendix1 all --appendix1-j-network 0x0001 --appendix1-u-io 0x0000 --appendix1-cpu-io 0x03E0
```

If you need frame dumps or packet captures for local debugging:

- keep them local
- do not commit them
- do not add them back under `internal_docs/*/frame_dumps*` or `wireshark/`

## 11. What Each Layer Covers

`python -m unittest discover -s tests -v`

- frame encode/decode
- device encoding helpers
- typed API payload formation
- response parsing
- client-side validation logic

`python -m ruff check .`

- style and correctness rules
- import order
- common bug patterns

`python -m mypy slmp4e scripts`

- API typing consistency
- CLI/library interface drift

Focused scripts then verify real PLC behavior for their own area.

## 12. Interpreting Failures

Local failures usually mean:

- import or packaging problem
- request/response regression
- API drift

Live failures usually mean:

- wrong host/port/transport
- PLC communication settings mismatch
- target-specific unsupported path
- device-range or label-side condition failure

Common examples in this project:

- `0x4030`: selected device/path rejected
- `0x4031`: configured range/allocation mismatch
- `0x40C0`: label missing or external access disabled
- `0xC061`: request content/path not accepted in the current environment

Use:

- [ERROR_CODES.md](ERROR_CODES.md) for the quick table
- [internal_docs/open_items.md](internal_docs/open_items.md) for current unresolved items
- [internal_docs/communication_test_record.md](internal_docs/communication_test_record.md) for chronology

## 13. Report Files

Common tracked report outputs:

- `internal_docs/<series>_<model>/open_items_recheck_latest.md`
- `internal_docs/<series>_<model>/pending_live_verification_latest.md`
- `internal_docs/<series>_<model>/register_boundary_probe_latest.md`
- `internal_docs/<series>_<model>/manual_write_verification_latest.md`
- `internal_docs/<series>_<model>/manual_label_verification_latest.md`

Stable summaries live in:

- `internal_docs/open_items.md`
- `internal_docs/communication_test_record.md`
- `internal_docs/manual_implementation_differences.md`

## 14. Minimum Release Gate

Before a release or a merge that changes behavior, run at least:

1. `python -m unittest discover -s tests -v`
2. `python -m ruff check .`
3. `python -m mypy slmp4e scripts`
4. `python scripts/slmp_connection_check.py --host <host> --port <port> --transport tcp --series <series>`

Also run focused live scripts when the change touches that area.

# User Guide

This guide is the fastest way to start using the library safely.

Use [TESTING.md](TESTING.md) for local and live verification steps. Use [ERROR_CODES.md](ERROR_CODES.md) when the PLC returns an end code.
If you prefer runnable copy-start examples, use [samples/README.md](samples/README.md).

## 1. Scope

- supported frame: `4E`
- supported data code: binary
- not supported: `3E`, ASCII mode

## 2. Install

```powershell
python -m pip install "git+https://github.com/fa-yoshinobu/slmp4e-connect-python.git"
```

For development from a local checkout:

```powershell
python -m pip install -e ".[dev]"
```

## 3. Pick the Right `series`

Use:

- `series="ql"` for MELSEC-Q/L style device encoding
- `series="iqr"` for MELSEC iQ-R/iQ-L style device encoding

This changes device-number width, device-code width, subcommand choice, and iQ-R bit-write encoding.

## 4. Connect First

Minimal connection check:

```python
from slmp4e import SLMP4EClient

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    info = cli.read_type_name()
    print(info.model, info.model_code)
```

If you need an explicit target header:

```python
from slmp4e import SLMP4EClient, SLMPTarget

target = SLMPTarget(
    network=0x00,
    station=0xFF,
    module_io=0x03FF,
    multidrop=0x00,
)

with SLMP4EClient(
    "192.168.250.101",
    port=1025,
    transport="tcp",
    plc_series="iqr",
    default_target=target,
) as cli:
    print(cli.read_type_name().model)
```

## 5. Normal Device Read and Write

Read words:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    print(cli.read_devices("D100", 2, bit_unit=False))
```

Read bits:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    print(cli.read_devices("M100", 5, bit_unit=True))
```

Write words:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.write_devices("D100", [0x1234, 0x5678], bit_unit=False)
```

Write bits:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.write_devices("M100", [True, False, True, False], bit_unit=True)
```

Notes:

- set `bit_unit=True` for bit-oriented access
- device strings such as `D100`, `M100`, `X20`, and `ZR10` are parsed automatically
- PLC-side enabled ranges are environment-dependent; do not hard-code them in your application

## 6. Random and Block Access

Random read:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    result = cli.read_random(word_devices=["D100", "D101"], dword_devices=["D200"])
    print(result.word)
    print(result.dword)
```

Random write:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.write_random_words(
        word_values={"D100": 0x1111, "D101": 0x2222},
        dword_values={"D200": 0x12345678},
    )
    cli.write_random_bits({"M100": True, "Y20": False})
```

Block read/write:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    result = cli.read_block(word_blocks=[("D100", 2)], bit_blocks=[("M200", 1)])
    print(result.word_blocks[0].values)

    cli.write_block(
        word_blocks=[("D100", [0x1111, 0x2222])],
        bit_blocks=[("M200", [0x0005])],
    )
```

Notes:

- `bit_blocks` uses packed 16-bit words, not one boolean per bit
- mixed word/bit block access is sent as one request by default
- if a target rejects mixed blocks, use `split_mixed_blocks=True`

## 7. Monitor Access

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.entry_monitor_device(word_devices=["D100", "D101"], dword_devices=["D200"])
    result = cli.execute_monitor(word_points=2, dword_points=1)
    print(result.word)
    print(result.dword)
```

`word_points` and `dword_points` must match the registered devices.

## 8. Long Timer Helpers

On the validated iQ-R target, the supported read path for `LT/LST` state is the helper-backed `LTN/LSTN` decode path.

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    print(cli.read_long_timer(head_no=0, points=2))
    print(cli.read_long_retentive_timer(head_no=0, points=2))

    print(cli.read_ltc_states(head_no=0, points=2))
    print(cli.read_lts_states(head_no=0, points=2))
    print(cli.read_lstc_states(head_no=0, points=2))
    print(cli.read_lsts_states(head_no=0, points=2))
```

Practical rule on the validated target:

- use `read_ltc_states(...)`, `read_lts_states(...)`, `read_lstc_states(...)`, `read_lsts_states(...)`
- do not treat direct `LTC/LTS/LSTC/LSTS` reads as the preferred API path

## 9. Label Access

Random label read:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    items = cli.label_read_random_points(["LabelW", "LabelB"])
    for item in items:
        print(item.label, item.data.hex(" "))
```

Random label write:

```python
from slmp4e import LabelRandomWritePoint

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.label_write_random_points([LabelRandomWritePoint(label="LabelW", data=b"\x31\x00")])
```

Array label read/write:

```python
from slmp4e import LabelArrayReadPoint, LabelArrayWritePoint

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    points = [LabelArrayReadPoint(label="ArrayLabel[0]", unit_specification=1, array_data_length=4)]
    print(cli.array_label_read_points(points)[0].data.hex(" "))

    cli.array_label_write_points(
        [LabelArrayWritePoint(label="ArrayLabel[0]", unit_specification=1, array_data_length=2, data=b"\x34\x12")]
    )
```

Label-side conditions matter:

- the label must exist
- `Access from External Device` must be enabled

## 10. Memory and CPU Buffer Access

Status on this project: conditional / advanced only.

Do not treat this section as a broadly validated normal application path. Memory writes, extend-unit writes, and CPU-buffer writes can directly change PLC state. On the current validated target, the `cpu_buffer_*` helpers are only a practical `0601/1601` workaround and must not be treated as a generally confirmed substitute for direct `G/HG` or Appendix 1 access.

Use this area only after revalidation on the actual PLC and only when normal device access does not fit the job.

Own-station memory:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    words = cli.memory_read_words(0x00001234, 2)
    cli.memory_write_words(0x00001234, words)
```

Verified CPU-buffer helper path:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    print(cli.cpu_buffer_read_word(0x00000004))
    print(hex(cli.cpu_buffer_read_dword(0x00000000)))
```

Low-level extend-unit path:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    data = cli.extend_unit_read_bytes(0x00000000, 2, 0x03E0)
    print(data.hex(" "))
    cli.extend_unit_write_bytes(0x00000000, 0x03E0, data)
```

Practical rule on the validated target:

- treat `cpu_buffer_*` as a target-specific workaround, not as a generally portable feature
- direct `G/HG` access is still unresolved
- Appendix 1 `G/HG` is also unresolved on the current PLC
- do not assume memory / extend-unit write paths are safe just because the API exists

## 11. Appendix 1 Access

Status on this project: under investigation.

Do not assume Appendix 1 access works correctly just because the `_ext` APIs exist. On the current validated target, Appendix 1 handling remains highly environment-dependent, and `G/HG`-related Appendix 1 paths are still unresolved / rejected.

Treat the example below as payload-shape reference only, not as a generally verified workflow:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="ql") as cli:
    ext = cli.make_extension_spec(
        extension_specification=0x0001,
        extension_specification_modification=0x00,
        device_modification_index=0x00,
        use_indirect_specification=False,
        register_mode="none",
        direct_memory_specification=0xF9,
        series="ql",
    )
    print(cli.read_devices_ext("W100", 1, extension=ext, bit_unit=False, series="ql"))
```

Use:

- `0xF9` for link direct (`J`)
- `0xF8` for module access (`U`)
- `0xFA` for CPU buffer access

Appendix 1 behavior is highly environment-dependent. Revalidate it on the actual PLC before depending on it.
If Appendix 1 is business-critical for your use case, treat it as "not yet confirmed" until you verify the exact target/device/path combination yourself.

## 12. Remote Control and Password

Remote control:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.remote_stop_control()
    cli.remote_run_control(force=False, clear_mode=2)
    cli.remote_pause_control(force=False)
```

Password:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.remote_password_unlock_text("melsec1234")
    cli.remote_password_lock_text("melsec1234")
```

Warnings:

- remote operations change PLC state
- `remote_reset_control()` is disruptive and not part of the routine live-verification workflow
- `1005` remote latch clear is state-dependent; on the validated target it was confirmed under PLC `STOP`

## 13. File Commands

Status on this project: not generally usable on the validated target.

File helpers are implemented, but the current validated target still rejects most `18xx` paths. Treat this family as unresolved / environment-dependent unless your own PLC proves otherwise.

The flow below is API-shape reference only. It is not a generally confirmed working sequence on the current validated target:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    handle = cli.file_open_handle(filename="ABC.QPG", drive_no=0, subcommand=0x0000, write_open=True)
    try:
        cli.file_write_chunk(handle, offset=0, data=b"\x12\x34")
        print(cli.file_read_chunk(handle, offset=0, size=2).hex(" "))
    finally:
        cli.file_close_handle(handle)
```

Practical note:

- treat the file family as unresolved until your PLC confirms it
- do not present file-command support to application users as a stable feature on the current validated baseline

## 14. Ondemand Receive

`2101` is PLC-initiated. Do not send it as a normal request.

Status on this project: outside routine verification and not confirmed as a general application workflow.

This path only makes sense when the PLC actively sends an ondemand frame. The example below is a receive-side skeleton, not a generally verified "works everywhere" feature. Use it only when you control the PLC-side trigger and can validate the full end-to-end behavior on your own setup.

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    data = cli.receive_ondemand(timeout=5.0)
    print(data.hex(" "))
```

## 15. Raw Command Access

Use raw access only when the typed API does not cover your case:

```python
from slmp4e.constants import Command

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    response = cli.raw_command(Command.SELF_TEST, subcommand=0x0000, payload=b"\x05\x00ABCDE")
    print(response.end_code, response.data.hex(" "))
```

## 16. Useful CLI Commands

Connection check:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

Pending command-family verification:

```powershell
python scripts/slmp_pending_live_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

Manual write verification from the device matrix:

```powershell
python scripts/slmp_manual_write_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --matrix internal_docs/iqr_r08cpu/device_access_matrix.csv --device-code D
```

Manual label verification:

```powershell
python scripts/slmp_manual_label_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-random LabelB --label-random LabelW
```

More examples are listed in [scripts/README.md](scripts/README.md).

## 17. Error Handling

PLC-side errors raise `SLMPError` by default:

```python
from slmp4e import SLMPError

try:
    with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
        cli.read_devices("D100", 1)
except SLMPError as exc:
    print(exc)
    print(exc.end_code)
```

Common examples on the validated target:

- `0x4030`: selected device/path rejected
- `0x4031`: configured range/allocation mismatch
- `0x40C0`: label exists problem or external access not enabled
- `0xC061`: request content/path not accepted by the current environment

Use [ERROR_CODES.md](ERROR_CODES.md) for the quick table and `internal_docs/error_code_reference.md` for the maintainer-facing version.

## 18. Safety Checklist

- treat every write as potentially destructive
- be especially careful with remote control, memory writes, extend-unit writes, and file commands
- validate `network`, `station`, and `module_io` before talking to a non-default target
- start with `read_type_name()` and a harmless device read

## 19. Validated-Target Practical Notes

Current project guidance for the validated iQ-R target:

- prefer `read_ltc_states(...)` / `read_lts_states(...)` / `read_lstc_states(...)` / `read_lsts_states(...)`
- prefer `cpu_buffer_read_*` / `cpu_buffer_write_*`
- treat direct `G`, `HG`, and `S` device APIs as unsupported in this project
- revalidate file commands and Appendix 1 access on your own PLC before relying on them

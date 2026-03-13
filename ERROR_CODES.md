# Error Codes Guide

This file is the quick end-code table for users of the library.

For the maintainer-facing version, see [internal_docs/error_code_reference.md](internal_docs/error_code_reference.md).

## 1. Where Errors Come From

There are three different failure layers:

1. client-side validation failure
   - example: invalid device text or unsupported argument shape
   - Python result: `ValueError`
2. PLC-side rejection
   - normal SLMP response frame, but `end_code != 0`
   - Python result: `SLMPError`
3. transport failure
   - example: timeout, connection refused, route failure
   - Python result: `TimeoutError`, `ConnectionRefusedError`, or another `OSError`

## 2. Common End Codes on the Validated iQ-R Target

| End code | Practical meaning in this project | Common example |
| --- | --- | --- |
| `0x0000` | success | valid request accepted |
| `0x4013` | operation rejected in the current PLC state | `1005` remote latch clear outside the accepted state |
| `0x4030` | selected device/path rejected | `S0` bit write, direct `LTC/LTS/LSTC/LSTS` read |
| `0x4031` | configured range or allocation mismatch | start address outside the enabled range |
| `0x4043` | extend-unit argument invalid | `0601` with `module_no=0x0000` |
| `0x4080` | target/module mismatch | `0601` with `module_no=0x03FF` |
| `0x40C0` | label-side condition failure | label missing or external access disabled |
| `0x413E` | file state/environment rejected the operation | `18xx` file commands on the current target |
| `0xC051` | word-count or unit rule violation | `LZ1 x1` write, some long-counter writes |
| `0xC059` | request family not accepted by the current endpoint | unsupported request family on the current target |
| `0xC05B` | direct `G/HG` path rejected | normal `0401` read of `G0` / `HG0` |
| `0xC061` | request content/path not accepted in the current environment | Appendix 1 CPU buffer access, some file commands |
| `0xC207` | file environment rejected the operation | some `18xx` file commands |

## 3. How to Inspect the Raw `end_code`

```python
from slmp4e import SLMP4EClient

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    response = cli.raw_command(0x0401, subcommand=0x0002, payload=b"...", raise_on_error=False)
    print(hex(response.end_code))
```

High-level APIs raise `SLMPError` by default. Use `raise_on_error=False` when you need the raw response.

## 4. Reading the Result Correctly

- `0x0000` means the PLC accepted the request, not that the operator-visible effect was what you expected
- the same end code can appear in more than one context
- target-specific conditions matter, especially for labels, Appendix 1, file commands, and remote control

## 5. Related Documents

- [USER_GUIDE.md](USER_GUIDE.md)
- [TESTING.md](TESTING.md)
- [internal_docs/open_items.md](internal_docs/open_items.md)
- [internal_docs/error_code_reference.md](internal_docs/error_code_reference.md)

Note for `0xC051`:

- the current project treats it as manual-confirmed for word-count / unit violations

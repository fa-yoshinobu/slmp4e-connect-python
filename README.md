# SLMP4E Connect Python

SLMP4E Connect Python is a Python library and CLI toolkit for Mitsubishi SLMP 4E binary communication.

It is built for engineers who need broad PLC device coverage, typed APIs, and practical behavior validated against a real MELSEC target instead of protocol-only examples.

Repository: `https://github.com/fa-yoshinobu/slmp4e-connect-python`
License: `MIT`
Copyright: `Copyright (c) 2026 fa-yoshinobu`

Why this project stands out:

- broad verified device coverage across `38` PLC device families on the current validated baseline
- typed Python APIs for normal, random, block, monitor, memory, label, remote-control, and file-command workflows
- CLI tools for connection checks, probes, and live-verification support
- validated primarily on Mitsubishi MELSEC iQ-R `R08CPU` over `TCP` and `UDP`

This repository focuses on one protocol slice:

- `4E` frame only
- binary data code only

Out of scope:

- `3E` frame
- ASCII mode

## Broad PLC Device Coverage

At the current validated iQ-R baseline, the device access matrix confirms representative read/write coverage across `38` PLC device families, including manual temporary-write verification and restore for the supported set.

Representative coverage includes:

- core bit and word devices such as `X`, `Y`, `M`, `L`, `B`, `F`, `V`, `D`, `W`, `R`, `RD`, `Z`, `ZR`, `SM`, `SD`, `SB`, `SW`, `DX`, and `DY`
- timer and counter families such as `TS/TC/TN`, `STS/STC/STN`, and `CS/CC/CN`
- long-timer and long-counter families such as `LTN/LTC/LTS`, `LSTN/LSTC/LSTS`, `LCN/LCC/LCS`, and `LZ`

The current validated matrix is tracked in [internal_docs/iqr_r08cpu/device_access_matrix.md](internal_docs/iqr_r08cpu/device_access_matrix.md). Current practical exceptions remain `G`, `HG`, and typed `S` write behavior on the validated target.

## Start Here

If you just want to use the library:

1. Read [USER_GUIDE.md](USER_GUIDE.md).
2. Run the safe smoke checks in [TESTING.md](TESTING.md).
3. Check [ERROR_CODES.md](ERROR_CODES.md) when the PLC returns an end code.

If you are maintaining this repository:

1. Read [STATUS.md](STATUS.md) for the current baseline.
2. Use [internal_docs/README.md](internal_docs/README.md) as the internal report index.
3. Check [internal_docs/open_items.md](internal_docs/open_items.md) before changing target-specific behavior.

## Quick Install

```powershell
python -m pip install "git+https://github.com/fa-yoshinobu/slmp4e-connect-python.git"
```

For development from a local checkout:

```powershell
python -m pip install -e ".[dev]"
```

## Quick Example

```python
from slmp4e import SLMP4EClient

with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    info = cli.read_type_name()
    print(info.model, hex(info.model_code or 0))

    values = cli.read_devices("D1000", 2, bit_unit=False)
    print(values)
```

With an explicit target header:

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

## Common CLI Entry Points

Connection check:

```powershell
python scripts/slmp_connection_check.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

Initialize a model-specific report folder:

```powershell
python scripts/slmp_init_model_docs.py --series iqr --model R16CPU
```

Interactive label verification:

```powershell
python scripts/slmp_manual_label_verification.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-random LabelW
```

More wrapper scripts are listed in [scripts/README.md](scripts/README.md).

## Implemented Coverage

The library implements:

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
- Appendix 1 typed builders and helper APIs

Some families are implemented but still environment-dependent on the validated PLC. The current practical guidance lives in [USER_GUIDE.md](USER_GUIDE.md) and [internal_docs/open_items.md](internal_docs/open_items.md).

## Validated Target

The current repository baseline was verified mainly against:

- Mitsubishi MELSEC iQ-R `R08CPU`
- host `192.168.250.101`
- `TCP 1025`
- `UDP 1027`
- `series=iqr`

Target-specific practical notes and the current report set are indexed in [internal_docs/iqr_r08cpu/README.md](internal_docs/iqr_r08cpu/README.md).

## Documentation Map

- [USER_GUIDE.md](USER_GUIDE.md): how to use the Python API and CLI safely
- [TESTING.md](TESTING.md): local checks, live-test order, and report policy
- [ERROR_CODES.md](ERROR_CODES.md): quick interpretation of common end codes
- [BIT_DEVICE_ACCESS_TABLE.md](BIT_DEVICE_ACCESS_TABLE.md): bit-device read/write behavior by access form
- [STATUS.md](STATUS.md): current repository baseline and known limits
- [RELEASE.md](RELEASE.md): release checklist
- [CHANGELOG.md](CHANGELOG.md): release history
- [SLMP_SPECIFICATION.md](SLMP_SPECIFICATION.md): implementation-facing protocol spec
- [scripts/README.md](scripts/README.md): wrapper-script index
- [internal_docs/README.md](internal_docs/README.md): internal stable docs and model-folder layout
- [internal_docs/iqr_r08cpu/README.md](internal_docs/iqr_r08cpu/README.md): validated-target report index

## Generated Reports

Tracked live reports are stored under `internal_docs/<series>_<model>/`.

For the current validated target, start with:

- [internal_docs/iqr_r08cpu/README.md](internal_docs/iqr_r08cpu/README.md)

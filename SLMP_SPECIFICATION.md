# SLMP Specification (4E Frame, Binary)

This document is the authoritative communication specification for this repository.

Known intentional differences between manual expectations and the current implementation are tracked separately in:

- `internal_docs/manual_implementation_differences.md`

## 1. Scope

- Protocol: SLMP (Seamless Message Protocol)
- Frame type: 4E frame only
- Data code: binary only
- Out of scope: 3E frame and ASCII code mode

## 2. 4E Binary Frame Format

## 2.1 Request Frame

Field order and size:
1. `Subheader` (2 bytes): `0x54 0x00`
2. `Serial No.` (2 bytes, little-endian)
3. `Reserved` (2 bytes): `0x00 0x00`
4. `Network No.` (1 byte)
5. `Station No.` (1 byte)
6. `Module I/O No.` (2 bytes, little-endian)
7. `Multidrop Station No.` (1 byte)
8. `Request data length` (2 bytes, little-endian)
9. `Monitoring timer` (2 bytes, little-endian)
10. `Command` (2 bytes, little-endian)
11. `Subcommand` (2 bytes, little-endian)
12. `Request data` (variable)

`Request data length` is the byte count from `Monitoring timer` through the end of `Request data`.

## 2.2 Response Frame

Field order and size:
1. `Subheader` (2 bytes): `0xD4 0x00`
2. `Serial No.` (2 bytes, little-endian)
3. `Reserved` (2 bytes)
4. `Network No.` (1 byte)
5. `Station No.` (1 byte)
6. `Module I/O No.` (2 bytes, little-endian)
7. `Multidrop Station No.` (1 byte)
8. `Response data length` (2 bytes, little-endian)
9. `End code` (2 bytes, little-endian)
10. `Response data` (variable)

`Response data length` is the byte count from `End code` through the end of `Response data`.

## 2.3 Endianness

All numeric fields are handled as little-endian in binary mode unless a command-specific field explicitly defines byte-level data semantics.

## 3. Command Coverage

## 3.1 Typed APIs Implemented

Device access:
1. `0401` Read
2. `1401` Write
3. `0403` Read Random
4. `1402` Write Random
5. `0801` Entry Monitor Device
6. `0802` Execute Monitor
7. `0406` Read Block
8. `1406` Write Block
9. Long timer helpers:
   - `read_long_timer(...)` (via `LTN`, 4-word units)
   - `read_long_retentive_timer(...)` (via `LSTN`, 4-word units)
   - `read_ltc_states(...)`, `read_lts_states(...)`
   - `read_lstc_states(...)`, `read_lsts_states(...)`

Memory / extend unit:
1. `0613` Memory Read
2. `1613` Memory Write
3. `0601` Extend Unit Read
4. `1601` Extend Unit Write
5. High-level helpers:
   - `extend_unit_read_words(...)`, `extend_unit_write_words(...)`
   - `extend_unit_read_word(...)`, `extend_unit_write_word(...)`
   - `extend_unit_read_dword(...)`, `extend_unit_write_dword(...)`
   - `cpu_buffer_read_bytes(...)`, `cpu_buffer_read_words(...)`
   - `cpu_buffer_read_word(...)`, `cpu_buffer_write_word(...)`
   - `cpu_buffer_read_dword(...)`, `cpu_buffer_write_dword(...)`
   - `cpu_buffer_write_bytes(...)`, `cpu_buffer_write_words(...)`

Label access:
1. `041A` Array Label Read
2. `141A` Array Label Write
3. `041C` Label Read Random
4. `141B` Label Write Random
5. Typed builders/parsers:
   - `build_array_label_read_payload`, `build_array_label_write_payload`
   - `build_label_read_random_payload`, `build_label_write_random_payload`
   - `parse_array_label_read_response`, `parse_label_read_random_response`
6. Typed result models:
   - `LabelArrayReadResult`, `LabelRandomReadResult`

Remote control and status:
1. `1001` Remote Run
2. `1002` Remote Stop
3. `1003` Remote Pause
4. `1005` Remote Latch Clear
5. `1006` Remote Reset
6. `0101` Read Type Name

Remote password:
1. `1631` Lock
2. `1630` Unlock

File control (major typed operations):
1. `1810` Read Directory/File
2. `1811` Search Directory/File
3. `1820` New File
4. `1822` Delete File
5. `1825` Change File State
6. `1826` Change File Date
7. `1827` Open File
8. `1828` Read File
9. `1829` Write File
10. `182A` Close File

Other:
1. `0619` Self Test
2. `1617` Clear Error
3. `2101` Ondemand receive

## 3.2 Full Raw Wrappers

Raw wrappers are available for all command groups implemented in this repository, including label and other file/maintenance commands.
- `1827` raw open returns raw response bytes (file pointer number payload)
- `1829` raw write returns raw response bytes (written-byte-count payload)
- `2101` is not sent as an external-device request; use `receive_ondemand(...)`

## 3.3 Typed Result Models

The library exposes typed result classes for major multi-field responses:
1. `TypeNameInfo`
2. `RandomReadResult`
3. `MonitorResult`
4. `BlockReadResult`
5. `LongTimerResult`
6. `LabelArrayReadResult`
7. `LabelRandomReadResult`

## 4. Device Encoding Rules

## 4.1 Normal Device Access (0000..0003)

For binary requests:
- Q/L compatible subcommands (`0000`, `0001`):
  - Device number: 3 bytes
  - Device code: 1 byte
- iQ-R/iQ-L subcommands (`0002`, `0003`):
  - Device number: 4 bytes
  - Device code: 2 bytes

Bit-unit data packing:
- 2 points per byte
- high nibble: first point
- low nibble: second point

Random bit write (`1402`) state value:
- Q/L (`0001`/`0081`): 1 byte per point (`01` set, `00` reset)
- iQ-R/iQ-L (`0003`/`0083`): 2 bytes per point (`01 00` set, `00 00` reset)

Block read/write compatibility handling:
- `read_block` and `write_block` send mixed word+bit blocks in one `0406/1406` request by default, matching the manual.
- If a target environment needs a compatibility fallback, `split_mixed_blocks=True` sends two commands (word-only, bit-only).
- For write-side compatibility, `retry_mixed_on_error=True` first sends one mixed `1406` request and retries as split word-only and bit-only writes only when the PLC returns a known mixed-write rejection end code. The current retry set is `0xC05B`.
- `bit_blocks` does not use one value per bit.
- Each bit-block point is handled as one packed 16-bit unit for the specified bit device family.
- Example:
  - `read_block(bit_blocks=[("M1000", 1)])` returns one packed 16-bit value for `M1000..M1015`
  - `write_block(bit_blocks=[("M1000", [0x0005])])` writes the packed pattern for `M1000..M1015`

Long timer / long retentive timer handling:
- The supported read specification in this project is to read `LTN` / `LSTN` in 4-word units and decode the effective `LT/LST` contact and coil state from the response.
- `LTC`/`LTS` and `LSTC`/`LSTS` are therefore not treated as the primary direct read target in this implementation.
- The helper decodes each 4-word block as:
  - `current_value`: `word0 + (word1 << 16)`
  - `status_word`: `word2`
  - `coil`: `status_word bit0`
  - `contact`: `status_word bit1`
- Convenience helpers are provided for the effective direct-state view:
  - `read_ltc_states(...)` returns the decoded `coil` bits from `LTN`
  - `read_lts_states(...)` returns the decoded `contact` bits from `LTN`
  - `read_lstc_states(...)` returns the decoded `coil` bits from `LSTN`
  - `read_lsts_states(...)` returns the decoded `contact` bits from `LSTN`
- Practical mapping on the validated iQ-R target:

| direct-style device | practical read API | decoded source |
|---|---|---|
| `LTC` | `read_ltc_states(...)` | `LTN` status-word coil bit |
| `LTS` | `read_lts_states(...)` | `LTN` status-word contact bit |
| `LSTC` | `read_lstc_states(...)` | `LSTN` status-word coil bit |
| `LSTS` | `read_lsts_states(...)` | `LSTN` status-word contact bit |
- This matches the manual note that `LTN` / `LSTN` responses include current value, contact bit, and coil bit in one 4-word response block.
- Latest live note on the validated iQ-R target:
  - `1402` random bit writes to `LTC`/`LTS` and `LSTC`/`LSTS` were verified with helper-backed readback and restore after correcting the helper mapping to the manual (`LTC/LSTC=coil`, `LTS/LSTS=contact`)
  - this repository does not pursue direct-programmatic `LTC/LTS/LSTC/LSTS` support as a separate target
  - `1402` random dword writes to `LTN`, `LSTN`, and `LCN` were verified with readback and restore
  - `1401`/`1402` manual-style long-counter writes were also verified:
    - `LCS` via `1401` word bulk write
    - `LCC` via `1401` bit bulk write and `1402` bit random write
    - `LCN` via `1401` word bulk write and `1402` dword random write
- Operational summary on the validated iQ-R target:

| family | supported read interpretation | current write interpretation |
|---|---|---|
| `LTC` / `LTS` | use `LTN` 4-word decode | `1402` bit random write verified with helper-backed readback and restore; direct-device API support is not pursued |
| `LSTC` / `LSTS` | use `LSTN` 4-word decode | `1402` bit random write verified with helper-backed readback and restore; direct-device API support is not pursued |
| `LTN` / `LSTN` | direct current-value access | `1402` dword random write verified |
| `LCS` | direct access | `1401` word bulk write verified |
| `LCC` | direct access | `1401` bit bulk write and `1402` bit random write verified |
| `LCN` | direct access | `1401` word bulk write and `1402` dword random write verified |

## 4.2 Supported Device Codes

Device code table is implemented in `slmp4e/constants.py` as `DEVICE_CODES`.
It includes standard codes and long-timer/long-counter related codes defined in the source manual.

## 5. Appendix 1 Extension Specification (0080..0083)

## 5.1 Extension Fields

Typed model: `ExtensionSpec`

Fields:
1. `extension_specification` (2 bytes)
2. `extension_specification_modification` (1 byte)
3. `device_modification_index` (1 byte)
4. `device_modification_flags` (1 byte)
5. `direct_memory_specification` (1 byte)

Binary payload builder:
- `encode_extended_device_spec(...)`
- `build_device_modification_flags(...)`

## 5.2 Direct Memory Specification Constants

1. `0x00`: normal device
2. `0xF8`: module access device (`U\\G` type)
3. `0xF9`: link direct device (`J\\W` type)
4. `0xFA`: CPU buffer memory access device

For `G/HG`, the practical meaning is that the access is unit/module-scoped, not a standalone normal device address.
- `G` corresponds to a module access device (`U\\G` style, for example `U4\\G0` in engineering-tool notation).
- `HG` is CPU-buffer related, but it is still not a standalone direct device on the validated target.
- In both cases, plain `G0` / `HG0` without surrounding unit/module context is not sufficient on the validated target.
- In the currently verified iQ-R path, that unit context is provided by `0601/1601` with `module_no=0x03E0`.
- For Appendix 1, the same idea appears as module-access / CPU-buffer access fields, but that path is still unresolved on the validated target.

## 5.3 Typed Extension APIs

1. `read_devices_ext`, `write_devices_ext`
2. `read_random_ext`
3. `write_random_words_ext`, `write_random_bits_ext`
4. `entry_monitor_device_ext`
5. `make_extension_spec(...)`

## 5.4 Observed Environment Gap (Manual vs PLC)

In the current iQ-R test environment, Appendix 1 module/CPU-buffer style access for `G/HG` is still returning `0xC061`, even when:
1. `direct_memory_specification` is changed (`0xFA` and `0xF8` tested)
2. extension specification variants are changed (`0x03E0`, `0x3E00`, `0x0000` tested)
3. both series modes are tested (`iqr` and `ql`)

This means Appendix 1 framing/parameter requirements on this PLC setup are stricter than what was inferred from manual examples alone.
Current operational status is tracked in:
1. `internal_docs/open_items.md`
2. `internal_docs/iqr_r08cpu/device_access_matrix.md`

Practical conclusion for this repository:
- `G` should be documented and treated as a unit-qualified module-access device (`U\\G` style).
- `HG` should be documented and treated as requiring explicit CPU-buffer / module context as well.
- On the validated target, the only verified operational form is `0601/1601` with `module_no=0x03E0`.
- The manual-side Appendix 1 interpretation for `U4\\G0` is:
  - direct memory `0xF8`
  - device code `G`
  - extension specification = intelligent-function-module start I/O number
- A focused `U4\\G0` check used the manual-aligned start I/O interpretation `0x0004` (`0040H` -> upper 3 digits), but that Appendix 1 path still returned `0xC061` on the validated target.
- A separate `0601/1601` path through `module_no=0x0004` returned data for low addresses, but those values did not match the live engineering-tool view of `U4\\G0`; therefore that path must not be treated as a confirmed `U\\G` equivalent.

## 6. Error Handling

- Protocol-level validation failures raise `SLMPError`.
- Intentionally blocked families in typed APIs raise `SLMPUnsupportedDeviceError`.
- Current blocked families in this project are `G`, `HG`, and `S`.
- `End code != 0` raises `SLMPError` by default (`raise_on_error=True`).
- Response frame size consistency is validated against `response_data_length`.
- Known target-specific risk paths may emit `SLMPPracticalPathWarning`.
- Known target-specific boundary behavior may emit `SLMPBoundaryBehaviorWarning`.

## 7. Transport Behavior

- TCP and UDP are supported.
- TCP receives exactly one SLMP frame using `response_data_length`.
- For remote reset (`1006`), the typed helper defaults to subcommand `0000` with no-response handling because normal completion may not return a response.
- `receive_request(...)` decodes an incoming 4E request frame from the PLC.
- `receive_ondemand(...)` / `ondemand()` wait for an incoming PLC-initiated `2101/0000` message and return its send data.

## 7.1 File Command Compliance Notes

- The file subcommand matrix is validated per command:
  - `1810`, `1811`, `1820`, `1826`: `0000`, `0040`
  - `1822`, `1824`, `1825`, `1827`: `0000`, `0004`, `0040`
  - `1828`, `1829`, `182A`: `0000` only
- For file password subcommand `0040`, the password length must be `0` or `6..32`.
- `file_change_state_by_name(...)` encodes the file attribute as a 2-byte field.
- `file_close_handle(...)` accepts close types `0`, `1`, and `2`.

## 7.2 Verified Practical Access Path Notes

- In the current iQ-R environment, direct `G/HG` device access is not operational.
- Appendix 1 `G/HG` access is also not operational in the same environment.
- The currently verified raw module/CPU-buffer access path is `0601/1601` with `module_no=0x03E0`.
- The `cpu_buffer_*` helpers are thin convenience wrappers around that verified `0601/1601` path.
- Read-then-write-same-value smoke checks were completed for `cpu_buffer_write_word(...)` and `cpu_buffer_write_dword(...)` at head address `0x00000000`.

## 8. Connection Verification

Use:
- `scripts/slmp_connection_check.py`

Capabilities:
1. Base communication test via `0101` (Read Type Name)
2. Optional normal device read via `0401`
3. Optional Appendix 1 extension checks for J/U/CPU buffer (`--appendix1`)
4. Optional local-only frame dumps for debugging (`--dump-frame-dir`)

Additional operational scripts:
1. `scripts/slmp_open_items_recheck.py` (recheck current open items only)
2. `scripts/slmp_device_range_probe.py` (probe PLC-configured boundary behavior from a spec file)
3. `scripts/slmp_register_boundary_probe.py` (repeatable focused boundary probe for `Z`, `LZ`, `R`, `ZR`, and `RD`)
4. `scripts/slmp_init_model_docs.py` (create a new `internal_docs/<series>_<model>/` scaffold)
5. `scripts/slmp_other_station_check.py` (verify multiple explicit target headers / other stations)
6. `scripts/slmp_pending_live_verification.py` (execute pending command-family live checks)

Installed console entry points:
1. `slmp4e-connection-check`
2. `slmp4e-device-range-probe`
3. `slmp4e-register-boundary-probe`
4. `slmp4e-init-model-docs`
5. `slmp4e-other-station-check`
6. `slmp4e-open-items-recheck`
7. `slmp4e-pending-live-verification`

## 9. Source Files

Core implementation:
- `slmp4e/core.py`
- `slmp4e/client.py`
- `slmp4e/constants.py`

Validation:
- `tests/test_slmp4e.py`

Generated live reports are tracked as `internal_docs/<series>_<model>/*_latest.md`, and each new run also writes a timestamped archive copy under `internal_docs/<series>_<model>/archive/`.

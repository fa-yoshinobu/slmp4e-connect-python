# Manual vs Implementation Differences

This file records places where the implementation follows a practical rule that is narrower, clearer, or different from what the manuals alone would suggest.

## Review Baseline

- last updated: 2026-03-13
- validated target: Mitsubishi MELSEC iQ-R `R08CPU`
- host: `192.168.250.101`

## 1. `LT/LST` Read Semantics

Manual expectation:

- `LTN` / `LSTN` responses include the effective contact and coil bits
- direct devices such as `LTC`, `LTS`, `LSTC`, and `LSTS` also exist

Current implementation:

- the supported read rule is the `LTN/LSTN` 4-word decode path
- public helpers:
  - `read_long_timer(...)`
  - `read_long_retentive_timer(...)`
  - `read_ltc_states(...)`
  - `read_lts_states(...)`
  - `read_lstc_states(...)`
  - `read_lsts_states(...)`

Reason:

- the helper path is live-verified and manual-aligned on the validated target
- direct `LTC/LTS/LSTC/LSTS` reads remain rejected there

Status:

- settled practical rule

## 2. `G/HG` Access

Manual expectation:

- `G` is unit-qualified module access
- `HG` is CPU-buffer related
- Appendix 1 access should work when the correct context is supplied

Current implementation:

- typed device APIs intentionally reject `G` and `HG`
- the practical supported path is:
  - `cpu_buffer_read_*`
  - `cpu_buffer_write_*`
  - implemented via `0601/1601` with `module_no=0x03E0`

Reason:

- direct and Appendix 1 `G/HG` remain rejected on the validated target
- the CPU-buffer helper path was live-verified

Status:

- practical deviation in favor of the verified path

## 3. Step Relay `S`

Manual expectation:

- `S` exists as a normal device family

Current implementation:

- typed device APIs intentionally reject `S`

Reason:

- live verification showed read OK but write `0x4030`

Status:

- temporarily blocked pending root-cause clarification

## 4. Mixed Block Fallback

Manual expectation:

- mixed word and bit blocks are sent in one `0406/1406` request

Current implementation:

- default behavior still sends one mixed request
- an optional compatibility fallback exists:
  - `split_mixed_blocks=True`

Reason:

- some PLC environments reject one mixed request

Status:

- optional non-default deviation

## 5. Remote Reset `1006`

Manual expectation:

- the manual is internally inconsistent between `0000` and `0001`
- successful `0000` may return no response

Current implementation:

- `remote_reset_control()` defaults to `1006/0000`
- no-response handling is the default behavior

Reason:

- this best matches the manual note about successful completion without a response

Status:

- manual ambiguity resolved by implementation choice

## 6. `R/ZR` Boundary Acceptance

Manual expectation:

- many devices are rejected once the requested span crosses the configured upper bound

Current implementation:

- the library does not hard-code those limits
- it sends the request and lets the PLC decide

Observed on the validated target:

- `R32767` and `ZR163839` were accepted as start addresses
- `R32768` and `ZR163840` were rejected as start addresses

Status:

- target-specific live behavior recorded

## 7. `LZ` Write Unit Rule

Manual expectation:

- `C051H` covers word-count or unit violations

Current implementation:

- the library does not add a PLC-specific client-side special case
- it sends the request and lets the PLC validate it

Observed on the validated target:

- `LZ1 x1` write -> `0xC051`
- `LZ1 x2` write -> `0x0000`

Status:

- target-specific live behavior recorded

## 8. `ZR` Numbering Base

Manual expectation:

- current device tables suggest hexadecimal-style `ZR`

Current implementation:

- the library uses decimal `ZR` numbering on the validated iQ-R target

Reason:

- live verification showed decimal numbering is the working behavior there

Status:

- manual/live discrepancy recorded; implementation follows live behavior

## Use Rule

If a future change introduces another manual-vs-live rule, add it here immediately with:

1. manual expectation
2. implemented behavior
3. reason
4. current status

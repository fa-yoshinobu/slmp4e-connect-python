# Bit Device Access Table

This note explains how bit-device families such as `M`, `B`, `X`, and `Y` behave across the main read forms used in this project.

## Key Rule

The device code stays the same. What changes is:

1. command
2. subcommand
3. interpretation unit

For bit devices:

- normal bit read returns one value per bit
- normal word read returns one packed 16-bit value per point
- block bit read also returns one packed 16-bit value per point

## Packed 16-Bit Meaning

If the device state is:

- `M1000 = 1`
- `M1001 = 0`
- `M1002 = 1`
- `M1003 = 0`

then the packed value beginning at `M1000` is `0x0005`.

The same rule applies to `B`, `X`, and `Y`.

## Device Family Notes

| Family | Number Format | Example Start |
|---|---|---|
| `M` | decimal | `M1000` |
| `B` | hexadecimal | `B20` |
| `X` | hexadecimal | `X20` |
| `Y` | hexadecimal | `Y20` |

## Access Mapping

| Family | Operation | Command | API Example | Point Meaning | Returned Value |
|---|---|---|---|---|---|
| `M` | bit read | `0401` | `read_devices("M1000", 4, bit_unit=True)` | `4` bits | `[True, False, True, False]` |
| `M` | word read | `0401` | `read_devices("M1000", 1, bit_unit=False)` | `1` packed 16-bit unit | `[0x0005]` |
| `M` | block bit read | `0406` | `read_block(bit_blocks=[("M1000", 1)])` | `1` packed 16-bit unit | `[0x0005]` |
| `B` | bit read | `0401` | `read_devices("B20", 4, bit_unit=True)` | `4` bits | `[True, False, True, False]` |
| `B` | word read | `0401` | `read_devices("B20", 1, bit_unit=False)` | `1` packed 16-bit unit | `[0x0005]` |
| `B` | block bit read | `0406` | `read_block(bit_blocks=[("B20", 1)])` | `1` packed 16-bit unit | `[0x0005]` |
| `X` | bit read | `0401` | `read_devices("X20", 4, bit_unit=True)` | `4` bits | `[True, False, True, False]` |
| `X` | word read | `0401` | `read_devices("X20", 1, bit_unit=False)` | `1` packed 16-bit unit | `[0x0005]` |
| `X` | block bit read | `0406` | `read_block(bit_blocks=[("X20", 1)])` | `1` packed 16-bit unit | `[0x0005]` |
| `Y` | bit read | `0401` | `read_devices("Y20", 4, bit_unit=True)` | `4` bits | `[True, False, True, False]` |
| `Y` | word read | `0401` | `read_devices("Y20", 1, bit_unit=False)` | `1` packed 16-bit unit | `[0x0005]` |
| `Y` | block bit read | `0406` | `read_block(bit_blocks=[("Y20", 1)])` | `1` packed 16-bit unit | `[0x0005]` |

## Practical Interpretation

For `M/B/X/Y`, block read does not mean "boolean array block" in this library.

Instead:

- `bit_blocks=[("M1000", 1)]` means one packed 16-bit unit
- `bit_blocks=[("M1000", 2)]` means two packed 16-bit units
- `bit_blocks=[("M1000", 705)]` means `705` packed 16-bit units, not `705` individual bits

## Write-Side Reminder

The same packed-unit rule applies to block write:

```python
with SLMP4EClient("192.168.250.101", port=1025, transport="tcp", plc_series="iqr") as cli:
    cli.write_block(
        bit_blocks=[("M1000", [0x0005])],
    )
```

This writes the packed pattern for `M1000..M1015`.

## When To Use Which Form

- Use bit read when you want individual bit states.
- Use word read when you want one packed 16-bit snapshot from a bit device.
- Use block bit read when you want multiple packed 16-bit snapshots in one `0406` request.

## Related Documents

- `USER_GUIDE.md`
- `SLMP_SPECIFICATION.md`
- `TESTING.md`

"""Core codec/types/helpers for SLMP 4E binary."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .constants import (
    DEVICE_CODES,
    DIRECT_MEMORY_NORMAL,
    FRAME_4E_REQUEST_SUBHEADER,
    FRAME_4E_RESPONSE_SUBHEADER,
    SUBCOMMAND_DEVICE_BIT_IQR,
    SUBCOMMAND_DEVICE_BIT_IQR_EXT,
    SUBCOMMAND_DEVICE_BIT_QL,
    SUBCOMMAND_DEVICE_BIT_QL_EXT,
    SUBCOMMAND_DEVICE_WORD_IQR,
    SUBCOMMAND_DEVICE_WORD_IQR_EXT,
    SUBCOMMAND_DEVICE_WORD_QL,
    SUBCOMMAND_DEVICE_WORD_QL_EXT,
    PLCSeries,
)


class SLMPError(Exception):
    """SLMP protocol error or error response."""

    def __init__(self, message: str, *, end_code: int | None = None, data: bytes = b"") -> None:
        super().__init__(message)
        self.end_code = end_code
        self.data = data


class SLMPUnsupportedDeviceError(ValueError):
    """Project-level validation error for device families intentionally disabled in typed APIs."""


class SLMPPracticalPathWarning(UserWarning):
    """Warning for paths that are implemented but known to be problematic on validated targets."""


class SLMPBoundaryBehaviorWarning(UserWarning):
    """Warning for target-specific boundary behavior that may differ from simple range assumptions."""


@dataclass(frozen=True)
class SLMPTarget:
    """4E frame destination fields."""

    network: int = 0x00
    station: int = 0xFF
    module_io: int = 0x03FF
    multidrop: int = 0x00


@dataclass(frozen=True)
class DeviceRef:
    """Device reference (e.g. D100, X20)."""

    code: str
    number: int

    def __str__(self) -> str:
        if self.code in DEVICE_CODES and DEVICE_CODES[self.code].radix == 16:
            return f"{self.code}{self.number:X}"
        return f"{self.code}{self.number}"


@dataclass(frozen=True)
class SLMPResponse:
    """Decoded 4E response frame."""

    serial: int
    target: SLMPTarget
    end_code: int
    data: bytes
    raw: bytes

    @property
    def is_success(self) -> bool:
        return self.end_code == 0


@dataclass(frozen=True)
class SLMPRequest:
    """Decoded 4E request frame."""

    serial: int
    target: SLMPTarget
    monitoring_timer: int
    command: int
    subcommand: int
    data: bytes
    raw: bytes


@dataclass(frozen=True)
class ExtensionSpec:
    """Appendix 1 extension fields (binary, 0080..0083)."""

    extension_specification: int = 0x0000
    extension_specification_modification: int = 0x00
    device_modification_index: int = 0x00
    device_modification_flags: int = 0x00
    direct_memory_specification: int = DIRECT_MEMORY_NORMAL


def parse_device(value: str | DeviceRef) -> DeviceRef:
    if isinstance(value, DeviceRef):
        return value

    text = value.strip().upper()
    match = re.fullmatch(r"([A-Z]+)([0-9A-F]+)", text)
    if not match:
        raise ValueError(f"invalid device format: {value!r}")

    code, num_txt = match.groups()
    if code not in DEVICE_CODES:
        raise ValueError(f"unknown device code: {code}")

    base = DEVICE_CODES[code].radix
    number = int(num_txt, base)
    return DeviceRef(code=code, number=number)


def encode_4e_request(
    *,
    serial: int,
    target: SLMPTarget,
    monitoring_timer: int,
    command: int,
    subcommand: int,
    data: bytes = b"",
) -> bytes:
    _check_u16(serial, "serial")
    _check_u16(monitoring_timer, "monitoring_timer")
    _check_u16(command, "command")
    _check_u16(subcommand, "subcommand")
    _check_u8(target.network, "target.network")
    _check_u8(target.station, "target.station")
    _check_u16(target.module_io, "target.module_io")
    _check_u8(target.multidrop, "target.multidrop")

    body = bytearray()
    body += target.network.to_bytes(1, "little")
    body += target.station.to_bytes(1, "little")
    body += target.module_io.to_bytes(2, "little")
    body += target.multidrop.to_bytes(1, "little")

    req_len = 2 + 2 + 2 + len(data)  # timer + command + subcommand + payload
    _check_u16(req_len, "request_data_length")
    body += req_len.to_bytes(2, "little")
    body += monitoring_timer.to_bytes(2, "little")
    body += command.to_bytes(2, "little")
    body += subcommand.to_bytes(2, "little")
    body += data

    frame = bytearray()
    frame += FRAME_4E_REQUEST_SUBHEADER
    frame += serial.to_bytes(2, "little")
    frame += b"\x00\x00"
    frame += body
    return bytes(frame)


def decode_4e_response(frame: bytes) -> SLMPResponse:
    if len(frame) < 15:
        raise SLMPError(f"response too short: {len(frame)} bytes")
    if frame[:2] != FRAME_4E_RESPONSE_SUBHEADER:
        got = frame[:2].hex(" ").upper()
        raise SLMPError(f"unexpected 4E response subheader: {got}")

    serial = int.from_bytes(frame[2:4], "little")
    target = SLMPTarget(
        network=frame[6],
        station=frame[7],
        module_io=int.from_bytes(frame[8:10], "little"),
        multidrop=frame[10],
    )

    response_data_length = int.from_bytes(frame[11:13], "little")
    if len(frame) != 13 + response_data_length:
        raise SLMPError(
            "response size mismatch: "
            f"actual={len(frame)}, expected={13 + response_data_length}, "
            f"response_data_length={response_data_length}"
        )
    if response_data_length < 2:
        raise SLMPError(f"invalid response_data_length: {response_data_length}")

    end_code = int.from_bytes(frame[13:15], "little")
    data = frame[15:]
    return SLMPResponse(serial=serial, target=target, end_code=end_code, data=data, raw=frame)


def decode_4e_request(frame: bytes) -> SLMPRequest:
    if len(frame) < 19:
        raise SLMPError(f"request too short: {len(frame)} bytes")
    if frame[:2] != FRAME_4E_REQUEST_SUBHEADER:
        got = frame[:2].hex(" ").upper()
        raise SLMPError(f"unexpected 4E request subheader: {got}")

    serial = int.from_bytes(frame[2:4], "little")
    target = SLMPTarget(
        network=frame[6],
        station=frame[7],
        module_io=int.from_bytes(frame[8:10], "little"),
        multidrop=frame[10],
    )

    request_data_length = int.from_bytes(frame[11:13], "little")
    if len(frame) != 13 + request_data_length:
        raise SLMPError(
            "request size mismatch: "
            f"actual={len(frame)}, expected={13 + request_data_length}, "
            f"request_data_length={request_data_length}"
        )
    if request_data_length < 6:
        raise SLMPError(f"invalid request_data_length: {request_data_length}")

    monitoring_timer = int.from_bytes(frame[13:15], "little")
    command = int.from_bytes(frame[15:17], "little")
    subcommand = int.from_bytes(frame[17:19], "little")
    data = frame[19:]
    return SLMPRequest(
        serial=serial,
        target=target,
        monitoring_timer=monitoring_timer,
        command=command,
        subcommand=subcommand,
        data=data,
        raw=frame,
    )


def resolve_device_subcommand(
    *,
    bit_unit: bool,
    series: PLCSeries,
    extension: bool = False,
) -> int:
    if extension:
        if series == PLCSeries.QL:
            return SUBCOMMAND_DEVICE_BIT_QL_EXT if bit_unit else SUBCOMMAND_DEVICE_WORD_QL_EXT
        return SUBCOMMAND_DEVICE_BIT_IQR_EXT if bit_unit else SUBCOMMAND_DEVICE_WORD_IQR_EXT
    if series == PLCSeries.QL:
        return SUBCOMMAND_DEVICE_BIT_QL if bit_unit else SUBCOMMAND_DEVICE_WORD_QL
    return SUBCOMMAND_DEVICE_BIT_IQR if bit_unit else SUBCOMMAND_DEVICE_WORD_IQR


def encode_device_spec(device: str | DeviceRef, *, series: PLCSeries) -> bytes:
    ref = parse_device(device)
    dev = DEVICE_CODES[ref.code]

    if series == PLCSeries.QL:
        if ref.number < 0 or ref.number > 0xFFFFFF:
            raise ValueError(f"device number out of range for Q/L format: {ref.number}")
        return ref.number.to_bytes(3, "little") + (dev.code & 0xFF).to_bytes(1, "little")

    _check_u32(ref.number, "device.number")
    return ref.number.to_bytes(4, "little") + dev.code.to_bytes(2, "little")


def encode_extension_spec(spec: ExtensionSpec) -> bytes:
    _check_u16(spec.extension_specification, "extension_specification")
    _check_u8(spec.extension_specification_modification, "extension_specification_modification")
    _check_u8(spec.device_modification_index, "device_modification_index")
    _check_u8(spec.device_modification_flags, "device_modification_flags")
    _check_u8(spec.direct_memory_specification, "direct_memory_specification")
    return (
        spec.extension_specification.to_bytes(2, "little")
        + spec.extension_specification_modification.to_bytes(1, "little")
        + spec.device_modification_index.to_bytes(1, "little")
        + spec.device_modification_flags.to_bytes(1, "little")
    )


def encode_extended_device_spec(
    device: str | DeviceRef,
    *,
    series: PLCSeries,
    extension: ExtensionSpec,
    include_direct_memory_at_end: bool = True,
) -> bytes:
    payload = bytearray()
    payload += encode_extension_spec(extension)
    payload += encode_device_spec(device, series=series)
    if include_direct_memory_at_end:
        payload += extension.direct_memory_specification.to_bytes(1, "little")
    return bytes(payload)


def build_device_modification_flags(
    *,
    series: PLCSeries,
    use_indirect_specification: bool = False,
    register_mode: str = "none",
) -> int:
    """Build device_modification_flags from Appendix 1 semantics.

    register_mode:
      - "none"
      - "z"
      - "lz" (iQ-R/iQ-L only)
    """
    mode = register_mode.lower()
    if mode not in {"none", "z", "lz"}:
        raise ValueError(f"register_mode must be one of none,z,lz: {register_mode}")
    if series == PLCSeries.QL and mode == "lz":
        raise ValueError("LZ register mode is not available for Q/L extension subcommands")

    high = 0x0
    if mode == "z":
        high = 0x4
    elif mode == "lz":
        high = 0x8
    low = 0x8 if use_indirect_specification else 0x0
    return ((high & 0xF) << 4) | (low & 0xF)


def decode_device_words(data: bytes) -> list[int]:
    if len(data) % 2 != 0:
        raise SLMPError(f"word data length must be even: {len(data)}")
    return [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


def decode_device_dwords(data: bytes) -> list[int]:
    if len(data) % 4 != 0:
        raise SLMPError(f"dword data length must be multiple of 4: {len(data)}")
    return [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data), 4)]


def pack_bit_values(values: Iterable[bool | int]) -> bytes:
    bits = [1 if bool(v) else 0 for v in values]
    out = bytearray()
    for i in range(0, len(bits), 2):
        hi = bits[i] & 0x1
        lo = bits[i + 1] & 0x1 if i + 1 < len(bits) else 0
        out.append((hi << 4) | lo)
    return bytes(out)


def unpack_bit_values(data: bytes, count: int) -> list[bool]:
    result: list[bool] = []
    for byte in data:
        result.append(bool((byte >> 4) & 0x1))
        if len(result) >= count:
            return result
        result.append(bool(byte & 0x1))
        if len(result) >= count:
            return result
    if len(result) != count:
        raise SLMPError(f"bit data too short: needed {count}, got {len(result)}")
    return result


def _check_u8(value: int, name: str) -> None:
    if value < 0 or value > 0xFF:
        raise ValueError(f"{name} out of range (0..255): {value}")


def _check_u16(value: int, name: str) -> None:
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"{name} out of range (0..65535): {value}")


def _check_u32(value: int, name: str) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"{name} out of range (0..4294967295): {value}")

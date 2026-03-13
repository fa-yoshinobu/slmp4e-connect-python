"""SLMP 4E binary client."""

from __future__ import annotations

import socket
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .constants import Command, PLCSeries
from .core import (
    DeviceRef,
    ExtensionSpec,
    SLMPBoundaryBehaviorWarning,
    SLMPError,
    SLMPPracticalPathWarning,
    SLMPRequest,
    SLMPResponse,
    SLMPTarget,
    SLMPUnsupportedDeviceError,
    build_device_modification_flags,
    decode_4e_request,
    decode_4e_response,
    decode_device_dwords,
    decode_device_words,
    encode_4e_request,
    encode_device_spec,
    encode_extended_device_spec,
    pack_bit_values,
    parse_device,
    resolve_device_subcommand,
    unpack_bit_values,
)


@dataclass(frozen=True)
class LabelArrayReadPoint:
    label: str
    unit_specification: int
    array_data_length: int


@dataclass(frozen=True)
class LabelArrayWritePoint:
    label: str
    unit_specification: int
    array_data_length: int
    data: bytes


@dataclass(frozen=True)
class LabelRandomWritePoint:
    label: str
    data: bytes


@dataclass(frozen=True)
class RandomReadResult:
    word: dict[str, int]
    dword: dict[str, int]


@dataclass(frozen=True)
class MonitorResult:
    word: list[int]
    dword: list[int]


@dataclass(frozen=True)
class DeviceBlockResult:
    device: str
    values: list[int]


@dataclass(frozen=True)
class BlockReadResult:
    word_blocks: list[DeviceBlockResult]
    bit_blocks: list[DeviceBlockResult]


@dataclass(frozen=True)
class LongTimerResult:
    index: int
    device: str
    current_value: int
    contact: bool
    coil: bool
    status_word: int
    raw_words: list[int]


@dataclass(frozen=True)
class LabelArrayReadResult:
    data_type_id: int
    unit_specification: int
    array_data_length: int
    data: bytes


@dataclass(frozen=True)
class LabelRandomReadResult:
    data_type_id: int
    spare: int
    read_data_length: int
    data: bytes


@dataclass(frozen=True)
class TypeNameInfo:
    raw: bytes
    model: str
    model_code: int | None


class SLMP4EClient:
    """SLMP 4E frame (binary) client.

    The implementation is intentionally 4E-binary only.
    """

    def __init__(
        self,
        host: str,
        port: int = 5000,
        *,
        transport: str = "tcp",
        timeout: float = 3.0,
        plc_series: PLCSeries | str = PLCSeries.QL,
        default_target: SLMPTarget | None = None,
        monitoring_timer: int = 0x0010,
        raise_on_error: bool = True,
        trace_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.transport = transport.lower()
        if self.transport not in {"tcp", "udp"}:
            raise ValueError("transport must be 'tcp' or 'udp'")
        self.timeout = timeout
        self.plc_series = PLCSeries(plc_series)
        self.default_target = default_target or SLMPTarget()
        self.monitoring_timer = monitoring_timer
        self.raise_on_error = raise_on_error
        self.trace_hook = trace_hook

        self._serial = 0
        self._sock: socket.socket | None = None

    def open(self) -> None:
        if self._sock is not None:
            return
        sock_type = socket.SOCK_STREAM if self.transport == "tcp" else socket.SOCK_DGRAM
        sock = socket.socket(socket.AF_INET, sock_type)
        sock.settimeout(self.timeout)
        if self.transport == "tcp":
            sock.connect((self.host, self.port))
        self._sock = sock

    def close(self) -> None:
        if self._sock is None:
            return
        self._sock.close()
        self._sock = None

    def __enter__(self) -> SLMP4EClient:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(
        self,
        command: int | Command,
        subcommand: int = 0x0000,
        data: bytes = b"",
        *,
        serial: int | None = None,
        target: SLMPTarget | None = None,
        monitoring_timer: int | None = None,
        raise_on_error: bool | None = None,
    ) -> SLMPResponse:
        serial_no = self._next_serial() if serial is None else serial
        target_info = target or self.default_target
        monitor = self.monitoring_timer if monitoring_timer is None else monitoring_timer
        cmd = int(command)

        frame = encode_4e_request(
            serial=serial_no,
            target=target_info,
            monitoring_timer=monitor,
            command=cmd,
            subcommand=subcommand,
            data=data,
        )
        raw = self._send_and_receive(frame)
        resp = decode_4e_response(raw)
        self._emit_trace(
            {
                "serial": serial_no,
                "command": cmd,
                "subcommand": subcommand,
                "request_data": data,
                "request_frame": frame,
                "response_frame": raw,
                "response_end_code": resp.end_code,
                "target": target_info,
                "monitoring_timer": monitor,
            }
        )

        do_raise = self.raise_on_error if raise_on_error is None else raise_on_error
        if do_raise and resp.end_code != 0:
            raise SLMPError(
                f"SLMP error end_code=0x{resp.end_code:04X} command=0x{cmd:04X} subcommand=0x{subcommand:04X}",
                end_code=resp.end_code,
                data=resp.data,
            )
        return resp

    def raw_command(
        self,
        command: int | Command,
        *,
        subcommand: int = 0x0000,
        payload: bytes = b"",
        serial: int | None = None,
        target: SLMPTarget | None = None,
        monitoring_timer: int | None = None,
        raise_on_error: bool | None = None,
    ) -> SLMPResponse:
        return self.request(
            command=command,
            subcommand=subcommand,
            data=payload,
            serial=serial,
            target=target,
            monitoring_timer=monitoring_timer,
            raise_on_error=raise_on_error,
        )

    @staticmethod
    def make_extension_spec(
        *,
        extension_specification: int = 0x0000,
        extension_specification_modification: int = 0x00,
        device_modification_index: int = 0x00,
        use_indirect_specification: bool = False,
        register_mode: str = "none",
        direct_memory_specification: int = 0x00,
        series: PLCSeries | str = PLCSeries.QL,
    ) -> ExtensionSpec:
        s = PLCSeries(series)
        flags = build_device_modification_flags(
            series=s,
            use_indirect_specification=use_indirect_specification,
            register_mode=register_mode,
        )
        return ExtensionSpec(
            extension_specification=extension_specification,
            extension_specification_modification=extension_specification_modification,
            device_modification_index=device_modification_index,
            device_modification_flags=flags,
            direct_memory_specification=direct_memory_specification,
        )

    # --------------------
    # Device commands (typed)
    # --------------------

    def read_devices(
        self,
        device: str | DeviceRef,
        points: int,
        *,
        bit_unit: bool = False,
        series: PLCSeries | str | None = None,
    ) -> list[int] | list[bool]:
        _check_points_u16(points, "points")
        s = PLCSeries(series) if series is not None else self.plc_series
        ref = parse_device(device)
        _check_temporarily_unsupported_device(ref)
        _warn_practical_device_path(ref, series=s, access_kind="direct")
        _warn_boundary_behavior(
            ref,
            series=s,
            points=points,
            write=False,
            bit_unit=bit_unit,
            access_kind="direct",
        )
        sub = resolve_device_subcommand(bit_unit=bit_unit, series=s, extension=False)
        payload = encode_device_spec(ref, series=s) + points.to_bytes(2, "little")
        resp = self.request(Command.DEVICE_READ, subcommand=sub, data=payload)
        if bit_unit:
            return unpack_bit_values(resp.data, points)
        words = decode_device_words(resp.data)
        if len(words) != points:
            raise SLMPError(f"word count mismatch: expected={points}, actual={len(words)}")
        return words

    def write_devices(
        self,
        device: str | DeviceRef,
        values: Sequence[int | bool],
        *,
        bit_unit: bool = False,
        series: PLCSeries | str | None = None,
    ) -> None:
        if not values:
            raise ValueError("values must not be empty")
        s = PLCSeries(series) if series is not None else self.plc_series
        ref = parse_device(device)
        _check_temporarily_unsupported_device(ref)
        _warn_practical_device_path(ref, series=s, access_kind="direct")
        _warn_boundary_behavior(
            ref,
            series=s,
            points=len(values),
            write=True,
            bit_unit=bit_unit,
            access_kind="direct",
        )
        sub = resolve_device_subcommand(bit_unit=bit_unit, series=s, extension=False)

        payload = bytearray()
        payload += encode_device_spec(ref, series=s)
        payload += len(values).to_bytes(2, "little")
        if bit_unit:
            payload += pack_bit_values(values)
        else:
            for value in values:
                payload += int(value).to_bytes(2, "little", signed=False)
        self.request(Command.DEVICE_WRITE, subcommand=sub, data=bytes(payload))

    def read_devices_ext(
        self,
        device: str | DeviceRef,
        points: int,
        *,
        extension: ExtensionSpec,
        bit_unit: bool = False,
        series: PLCSeries | str | None = None,
    ) -> list[int] | list[bool]:
        """Appendix 1 extension read (subcommand 0081/0080 or 0083/0082)."""
        _check_points_u16(points, "points")
        s = PLCSeries(series) if series is not None else self.plc_series
        ref = parse_device(device)
        _check_temporarily_unsupported_device(ref)
        _warn_practical_device_path(ref, series=s, access_kind="appendix1")
        sub = resolve_device_subcommand(bit_unit=bit_unit, series=s, extension=True)
        payload = bytearray()
        payload += encode_extended_device_spec(ref, series=s, extension=extension)
        payload += points.to_bytes(2, "little")
        resp = self.request(Command.DEVICE_READ, subcommand=sub, data=bytes(payload))
        if bit_unit:
            return unpack_bit_values(resp.data, points)
        words = decode_device_words(resp.data)
        if len(words) != points:
            raise SLMPError(f"word count mismatch: expected={points}, actual={len(words)}")
        return words

    def write_devices_ext(
        self,
        device: str | DeviceRef,
        values: Sequence[int | bool],
        *,
        extension: ExtensionSpec,
        bit_unit: bool = False,
        series: PLCSeries | str | None = None,
    ) -> None:
        """Appendix 1 extension write (subcommand 0081/0080 or 0083/0082)."""
        if not values:
            raise ValueError("values must not be empty")
        s = PLCSeries(series) if series is not None else self.plc_series
        ref = parse_device(device)
        _check_temporarily_unsupported_device(ref)
        _warn_practical_device_path(ref, series=s, access_kind="appendix1")
        sub = resolve_device_subcommand(bit_unit=bit_unit, series=s, extension=True)
        payload = bytearray()
        payload += encode_extended_device_spec(ref, series=s, extension=extension)
        payload += len(values).to_bytes(2, "little")
        if bit_unit:
            payload += pack_bit_values(values)
        else:
            for value in values:
                payload += int(value).to_bytes(2, "little", signed=False)
        self.request(Command.DEVICE_WRITE, subcommand=sub, data=bytes(payload))

    def read_random(
        self,
        *,
        word_devices: Sequence[str | DeviceRef] = (),
        dword_devices: Sequence[str | DeviceRef] = (),
        series: PLCSeries | str | None = None,
    ) -> RandomReadResult:
        if not word_devices and not dword_devices:
            raise ValueError("word_devices and dword_devices must not both be empty")
        if len(word_devices) > 0xFF or len(dword_devices) > 0xFF:
            raise ValueError("word_devices and dword_devices must be <= 255 each")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_read_like_counts(len(word_devices), len(dword_devices), series=s, name="read_random")
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=False)

        words = [parse_device(d) for d in word_devices]
        dwords = [parse_device(d) for d in dword_devices]
        _check_temporarily_unsupported_devices(words)
        _check_temporarily_unsupported_devices(dwords)

        payload = bytearray([len(words), len(dwords)])
        for dev in words:
            payload += encode_device_spec(dev, series=s)
        for dev in dwords:
            payload += encode_device_spec(dev, series=s)

        resp = self.request(Command.DEVICE_READ_RANDOM, subcommand=sub, data=bytes(payload))
        expected = len(words) * 2 + len(dwords) * 4
        if len(resp.data) != expected:
            raise SLMPError(f"random read response size mismatch: expected={expected}, actual={len(resp.data)}")

        offset = 0
        word_values = decode_device_words(resp.data[offset : offset + (len(words) * 2)])
        offset += len(words) * 2
        dword_values = decode_device_dwords(resp.data[offset:])
        return RandomReadResult(
            word={str(dev): value for dev, value in zip(words, word_values, strict=True)},
            dword={str(dev): value for dev, value in zip(dwords, dword_values, strict=True)},
        )

    def read_random_ext(
        self,
        *,
        word_devices: Sequence[tuple[str | DeviceRef, ExtensionSpec]] = (),
        dword_devices: Sequence[tuple[str | DeviceRef, ExtensionSpec]] = (),
        series: PLCSeries | str | None = None,
    ) -> RandomReadResult:
        if not word_devices and not dword_devices:
            raise ValueError("word_devices and dword_devices must not both be empty")
        if len(word_devices) > 0xFF or len(dword_devices) > 0xFF:
            raise ValueError("word_devices and dword_devices must be <= 255 each")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_read_like_counts(len(word_devices), len(dword_devices), series=s, name="read_random_ext")
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=True)
        payload = bytearray([len(word_devices), len(dword_devices)])
        words: list[tuple[DeviceRef, ExtensionSpec]] = []
        dwords: list[tuple[DeviceRef, ExtensionSpec]] = []
        for dev, ext in word_devices:
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            words.append((ref, ext))
            payload += encode_extended_device_spec(ref, series=s, extension=ext)
        for dev, ext in dword_devices:
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            dwords.append((ref, ext))
            payload += encode_extended_device_spec(ref, series=s, extension=ext)

        resp = self.request(Command.DEVICE_READ_RANDOM, subcommand=sub, data=bytes(payload))
        expected = len(words) * 2 + len(dwords) * 4
        if len(resp.data) != expected:
            raise SLMPError(f"random read response size mismatch: expected={expected}, actual={len(resp.data)}")

        offset = 0
        word_values = decode_device_words(resp.data[offset : offset + (len(words) * 2)])
        offset += len(words) * 2
        dword_values = decode_device_dwords(resp.data[offset:])
        return RandomReadResult(
            word={str(dev): value for (dev, _), value in zip(words, word_values, strict=True)},
            dword={str(dev): value for (dev, _), value in zip(dwords, dword_values, strict=True)},
        )

    def write_random_words(
        self,
        *,
        word_values: Mapping[str | DeviceRef, int] | Sequence[tuple[str | DeviceRef, int]] = (),
        dword_values: Mapping[str | DeviceRef, int] | Sequence[tuple[str | DeviceRef, int]] = (),
        series: PLCSeries | str | None = None,
    ) -> None:
        word_items = _normalize_items(word_values)
        dword_items = _normalize_items(dword_values)
        if not word_items and not dword_items:
            raise ValueError("word_values and dword_values must not both be empty")
        if len(word_items) > 0xFF or len(dword_items) > 0xFF:
            raise ValueError("word_values and dword_values must be <= 255 each")

        s = PLCSeries(series) if series is not None else self.plc_series
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=False)
        payload = bytearray([len(word_items), len(dword_items)])
        for device, value in word_items:
            _check_temporarily_unsupported_device(device)
            payload += encode_device_spec(device, series=s)
            payload += int(value).to_bytes(2, "little", signed=False)
        for device, value in dword_items:
            _check_temporarily_unsupported_device(device)
            payload += encode_device_spec(device, series=s)
            payload += int(value).to_bytes(4, "little", signed=False)
        self.request(Command.DEVICE_WRITE_RANDOM, subcommand=sub, data=bytes(payload))

    def write_random_words_ext(
        self,
        *,
        word_values: Sequence[tuple[str | DeviceRef, int, ExtensionSpec]] = (),
        dword_values: Sequence[tuple[str | DeviceRef, int, ExtensionSpec]] = (),
        series: PLCSeries | str | None = None,
    ) -> None:
        if not word_values and not dword_values:
            raise ValueError("word_values and dword_values must not both be empty")
        if len(word_values) > 0xFF or len(dword_values) > 0xFF:
            raise ValueError("word_values and dword_values must be <= 255 each")
        s = PLCSeries(series) if series is not None else self.plc_series
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=True)
        payload = bytearray([len(word_values), len(dword_values)])
        for device, value, ext in word_values:
            _check_temporarily_unsupported_device(parse_device(device))
            payload += encode_extended_device_spec(device, series=s, extension=ext)
            payload += int(value).to_bytes(2, "little", signed=False)
        for device, value, ext in dword_values:
            _check_temporarily_unsupported_device(parse_device(device))
            payload += encode_extended_device_spec(device, series=s, extension=ext)
            payload += int(value).to_bytes(4, "little", signed=False)
        self.request(Command.DEVICE_WRITE_RANDOM, subcommand=sub, data=bytes(payload))

    def write_random_bits(
        self,
        bit_values: Mapping[str | DeviceRef, bool | int] | Sequence[tuple[str | DeviceRef, bool | int]],
        *,
        series: PLCSeries | str | None = None,
    ) -> None:
        items = _normalize_items(bit_values)
        if not items:
            raise ValueError("bit_values must not be empty")
        if len(items) > 0xFF:
            raise ValueError("bit_values must be <= 255")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_bit_write_count(len(items), series=s, name="write_random_bits")
        sub = resolve_device_subcommand(bit_unit=True, series=s, extension=False)
        payload = bytearray([len(items)])
        for device, state in items:
            _check_temporarily_unsupported_device(device)
            payload += encode_device_spec(device, series=s)
            if s == PLCSeries.IQR:
                # iQ-R/iQ-L random bit write uses 2-byte set/reset field.
                # ON must be encoded as 0x0001 (01 00 in little-endian).
                payload += b"\x01\x00" if bool(state) else b"\x00\x00"
            else:
                payload += b"\x01" if bool(state) else b"\x00"
        self.request(Command.DEVICE_WRITE_RANDOM, subcommand=sub, data=bytes(payload))

    def write_random_bits_ext(
        self,
        bit_values: Sequence[tuple[str | DeviceRef, bool | int, ExtensionSpec]],
        *,
        series: PLCSeries | str | None = None,
    ) -> None:
        if not bit_values:
            raise ValueError("bit_values must not be empty")
        if len(bit_values) > 0xFF:
            raise ValueError("bit_values must be <= 255")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_bit_write_count(len(bit_values), series=s, name="write_random_bits_ext")
        sub = resolve_device_subcommand(bit_unit=True, series=s, extension=True)
        payload = bytearray([len(bit_values)])
        for device, state, ext in bit_values:
            _check_temporarily_unsupported_device(parse_device(device))
            payload += encode_extended_device_spec(device, series=s, extension=ext)
            if s == PLCSeries.IQR:
                payload += b"\x01\x00" if bool(state) else b"\x00\x00"
            else:
                payload += b"\x01" if bool(state) else b"\x00"
        self.request(Command.DEVICE_WRITE_RANDOM, subcommand=sub, data=bytes(payload))

    def entry_monitor_device(
        self,
        *,
        word_devices: Sequence[str | DeviceRef] = (),
        dword_devices: Sequence[str | DeviceRef] = (),
        series: PLCSeries | str | None = None,
    ) -> None:
        if not word_devices and not dword_devices:
            raise ValueError("word_devices and dword_devices must not both be empty")
        if len(word_devices) > 0xFF or len(dword_devices) > 0xFF:
            raise ValueError("word_devices and dword_devices must be <= 255 each")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_read_like_counts(
            len(word_devices),
            len(dword_devices),
            series=s,
            name="entry_monitor_device",
        )
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=False)

        payload = bytearray([len(word_devices), len(dword_devices)])
        for dev in word_devices:
            _check_temporarily_unsupported_device(parse_device(dev))
            payload += encode_device_spec(dev, series=s)
        for dev in dword_devices:
            _check_temporarily_unsupported_device(parse_device(dev))
            payload += encode_device_spec(dev, series=s)
        self.request(Command.DEVICE_ENTRY_MONITOR, subcommand=sub, data=bytes(payload))

    def entry_monitor_device_ext(
        self,
        *,
        word_devices: Sequence[tuple[str | DeviceRef, ExtensionSpec]] = (),
        dword_devices: Sequence[tuple[str | DeviceRef, ExtensionSpec]] = (),
        series: PLCSeries | str | None = None,
    ) -> None:
        if not word_devices and not dword_devices:
            raise ValueError("word_devices and dword_devices must not both be empty")
        if len(word_devices) > 0xFF or len(dword_devices) > 0xFF:
            raise ValueError("word_devices and dword_devices must be <= 255 each")
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_random_read_like_counts(
            len(word_devices),
            len(dword_devices),
            series=s,
            name="entry_monitor_device_ext",
        )
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=True)
        payload = bytearray([len(word_devices), len(dword_devices)])
        for dev, ext in word_devices:
            _check_temporarily_unsupported_device(parse_device(dev))
            payload += encode_extended_device_spec(dev, series=s, extension=ext)
        for dev, ext in dword_devices:
            _check_temporarily_unsupported_device(parse_device(dev))
            payload += encode_extended_device_spec(dev, series=s, extension=ext)
        self.request(Command.DEVICE_ENTRY_MONITOR, subcommand=sub, data=bytes(payload))

    def execute_monitor(self, *, word_points: int, dword_points: int) -> MonitorResult:
        if word_points < 0 or dword_points < 0:
            raise ValueError("word_points and dword_points must be >= 0")
        resp = self.request(Command.DEVICE_EXECUTE_MONITOR, subcommand=0x0000, data=b"")
        expected = word_points * 2 + dword_points * 4
        if len(resp.data) != expected:
            raise SLMPError(f"monitor response size mismatch: expected={expected}, actual={len(resp.data)}")
        offset = 0
        words = decode_device_words(resp.data[offset : offset + word_points * 2])
        offset += word_points * 2
        dwords = decode_device_dwords(resp.data[offset:])
        return MonitorResult(word=words, dword=dwords)

    def read_block(
        self,
        *,
        word_blocks: Sequence[tuple[str | DeviceRef, int]] = (),
        bit_blocks: Sequence[tuple[str | DeviceRef, int]] = (),
        series: PLCSeries | str | None = None,
        split_mixed_blocks: bool = False,
    ) -> BlockReadResult:
        """Read word blocks and bit-device word blocks.

        `word_blocks` uses normal word-device points.

        `bit_blocks` uses packed 16-bit units for bit devices. For example,
        one point at `M1000` returns the packed 16-bit word covering
        `M1000..M1015`, two points return `M1000..M1015` and `M1001..M1016`,
        and so on, matching the PLC's `0406` behavior on this project target.
        """
        if not word_blocks and not bit_blocks:
            raise ValueError("word_blocks and bit_blocks must not both be empty")
        if len(word_blocks) > 0xFF or len(bit_blocks) > 0xFF:
            raise ValueError("word_blocks and bit_blocks must be <= 255 each")
        if split_mixed_blocks and word_blocks and bit_blocks:
            w = self.read_block(
                word_blocks=word_blocks,
                bit_blocks=(),
                series=series,
                split_mixed_blocks=False,
            )
            b = self.read_block(
                word_blocks=(),
                bit_blocks=bit_blocks,
                series=series,
                split_mixed_blocks=False,
            )
            return BlockReadResult(word_blocks=w.word_blocks, bit_blocks=b.bit_blocks)
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_block_request_limits(word_blocks, bit_blocks, series=s, name="read_block")
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=False)

        payload = bytearray([len(word_blocks), len(bit_blocks)])
        norm_word: list[tuple[DeviceRef, int]] = []
        norm_bit: list[tuple[DeviceRef, int]] = []

        for dev, points in word_blocks:
            _check_points_u16(points, "word_block points")
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            _warn_practical_device_path(ref, series=s, access_kind="direct")
            norm_word.append((ref, points))
            payload += encode_device_spec(ref, series=s)
            payload += points.to_bytes(2, "little")
        for dev, points in bit_blocks:
            _check_points_u16(points, "bit_block points")
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            _warn_practical_device_path(ref, series=s, access_kind="direct")
            norm_bit.append((ref, points))
            payload += encode_device_spec(ref, series=s)
            payload += points.to_bytes(2, "little")

        resp = self.request(Command.DEVICE_READ_BLOCK, subcommand=sub, data=bytes(payload))

        offset = 0
        word_result: list[DeviceBlockResult] = []
        for ref, points in norm_word:
            size = points * 2
            words = decode_device_words(resp.data[offset : offset + size])
            if len(words) != points:
                raise SLMPError(f"word block response mismatch for {ref}")
            word_result.append(DeviceBlockResult(device=str(ref), values=words))
            offset += size

        bit_result: list[DeviceBlockResult] = []
        for ref, points in norm_bit:
            size = points * 2
            words = decode_device_words(resp.data[offset : offset + size])
            if len(words) != points:
                raise SLMPError(f"bit block response mismatch for {ref}")
            bit_result.append(DeviceBlockResult(device=str(ref), values=words))
            offset += size

        if offset != len(resp.data):
            raise SLMPError(f"read block response trailing data: {len(resp.data) - offset} bytes")
        return BlockReadResult(word_blocks=word_result, bit_blocks=bit_result)

    def write_block(
        self,
        *,
        word_blocks: Sequence[tuple[str | DeviceRef, Sequence[int]]] = (),
        bit_blocks: Sequence[tuple[str | DeviceRef, Sequence[int]]] = (),
        series: PLCSeries | str | None = None,
        split_mixed_blocks: bool = False,
    ) -> None:
        """Write word blocks and bit-device word blocks.

        `bit_blocks` values are packed 16-bit words for bit devices, not a
        per-bit boolean list. For example, writing `[0x0005]` to `M1000`
        sets the packed pattern for `M1000..M1015`.
        """
        if not word_blocks and not bit_blocks:
            raise ValueError("word_blocks and bit_blocks must not both be empty")
        if len(word_blocks) > 0xFF or len(bit_blocks) > 0xFF:
            raise ValueError("word_blocks and bit_blocks must be <= 255 each")
        if split_mixed_blocks and word_blocks and bit_blocks:
            self.write_block(
                word_blocks=word_blocks,
                bit_blocks=(),
                series=series,
                split_mixed_blocks=False,
            )
            self.write_block(
                word_blocks=(),
                bit_blocks=bit_blocks,
                series=series,
                split_mixed_blocks=False,
            )
            return
        s = PLCSeries(series) if series is not None else self.plc_series
        _check_block_request_limits(word_blocks, bit_blocks, series=s, name="write_block")
        sub = resolve_device_subcommand(bit_unit=False, series=s, extension=False)

        payload = bytearray([len(word_blocks), len(bit_blocks)])
        for dev, values in word_blocks:
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            _warn_practical_device_path(ref, series=s, access_kind="direct")
            _check_points_u16(len(values), "word block size")
            payload += encode_device_spec(ref, series=s)
            payload += len(values).to_bytes(2, "little")
        for dev, values in bit_blocks:
            ref = parse_device(dev)
            _check_temporarily_unsupported_device(ref)
            _warn_practical_device_path(ref, series=s, access_kind="direct")
            _check_points_u16(len(values), "bit block size")
            payload += encode_device_spec(ref, series=s)
            payload += len(values).to_bytes(2, "little")

        for _, values in word_blocks:
            for value in values:
                payload += int(value).to_bytes(2, "little", signed=False)
        for _, values in bit_blocks:
            for value in values:
                payload += int(value).to_bytes(2, "little", signed=False)
        self.request(Command.DEVICE_WRITE_BLOCK, subcommand=sub, data=bytes(payload))

    def read_long_timer(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[LongTimerResult]:
        """Read long timer (LT) by LTN in 4-word units and decode status bits."""
        return self._read_long_timer_like(device_prefix="LTN", head_no=head_no, points=points, series=series)

    def read_long_retentive_timer(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[LongTimerResult]:
        """Read long retentive timer (LST) by LSTN in 4-word units and decode status bits."""
        return self._read_long_timer_like(device_prefix="LSTN", head_no=head_no, points=points, series=series)

    def read_ltc_states(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[bool]:
        """Read LT coil states by decoding LTN 4-word units."""
        return [item.coil for item in self.read_long_timer(head_no=head_no, points=points, series=series)]

    def read_lts_states(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[bool]:
        """Read LT contact states by decoding LTN 4-word units."""
        return [item.contact for item in self.read_long_timer(head_no=head_no, points=points, series=series)]

    def read_lstc_states(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[bool]:
        """Read LST coil states by decoding LSTN 4-word units."""
        return [item.coil for item in self.read_long_retentive_timer(head_no=head_no, points=points, series=series)]

    def read_lsts_states(
        self,
        *,
        head_no: int = 0,
        points: int = 1,
        series: PLCSeries | str | None = None,
    ) -> list[bool]:
        """Read LST contact states by decoding LSTN 4-word units."""
        return [item.contact for item in self.read_long_retentive_timer(head_no=head_no, points=points, series=series)]

    def _read_long_timer_like(
        self,
        *,
        device_prefix: str,
        head_no: int,
        points: int,
        series: PLCSeries | str | None,
    ) -> list[LongTimerResult]:
        if head_no < 0:
            raise ValueError(f"head_no must be >= 0: {head_no}")
        if points < 1:
            raise ValueError(f"points must be >= 1: {points}")
        word_points = points * 4
        _check_points_u16(word_points, "long timer word points")

        words_raw = self.read_devices(
            f"{device_prefix}{head_no}",
            word_points,
            bit_unit=False,
            series=series,
        )
        words = [int(v) for v in words_raw]
        if len(words) != word_points:
            raise SLMPError(f"long timer read size mismatch: expected={word_points}, actual={len(words)}")

        result: list[LongTimerResult] = []
        for offset in range(points):
            base = offset * 4
            block = words[base : base + 4]
            status_word = block[2]
            result.append(
                LongTimerResult(
                    index=head_no + offset,
                    device=f"{device_prefix}{head_no + offset}",
                    current_value=(block[1] << 16) | block[0],
                    contact=bool(status_word & 0x0002),
                    coil=bool(status_word & 0x0001),
                    status_word=status_word,
                    raw_words=block,
                )
            )
        return result

    # --------------------
    # Additional typed command APIs
    # --------------------

    def memory_read_words(self, head_address: int, word_length: int) -> list[int]:
        _check_u32(head_address, "head_address")
        if word_length < 1 or word_length > 0x01E0:
            raise ValueError(f"word_length out of range (1..480): {word_length}")
        payload = head_address.to_bytes(4, "little") + word_length.to_bytes(2, "little")
        data = self.request(Command.MEMORY_READ, 0x0000, payload).data
        words = decode_device_words(data)
        if len(words) != word_length:
            raise SLMPError(f"memory read size mismatch: expected={word_length}, actual={len(words)}")
        return words

    def memory_write_words(self, head_address: int, values: Sequence[int]) -> None:
        _check_u32(head_address, "head_address")
        if not values:
            raise ValueError("values must not be empty")
        if len(values) > 0x01E0:
            raise ValueError(f"word length out of range (1..480): {len(values)}")
        payload = bytearray()
        payload += head_address.to_bytes(4, "little")
        payload += len(values).to_bytes(2, "little")
        for value in values:
            payload += int(value).to_bytes(2, "little", signed=False)
        self.request(Command.MEMORY_WRITE, 0x0000, bytes(payload))

    def extend_unit_read_bytes(self, head_address: int, byte_length: int, module_no: int) -> bytes:
        _check_u32(head_address, "head_address")
        _check_u16(module_no, "module_no")
        if byte_length < 2 or byte_length > 0x0780:
            raise ValueError(f"byte_length out of range (2..1920): {byte_length}")
        payload = (
            head_address.to_bytes(4, "little")
            + byte_length.to_bytes(2, "little")
            + module_no.to_bytes(2, "little")
        )
        data = self.request(Command.EXTEND_UNIT_READ, 0x0000, payload).data
        if len(data) != byte_length:
            raise SLMPError(f"extend unit read size mismatch: expected={byte_length}, actual={len(data)}")
        return data

    def extend_unit_read_words(self, head_address: int, word_length: int, module_no: int) -> list[int]:
        _check_u32(head_address, "head_address")
        if word_length < 1 or word_length > 0x03C0:
            raise ValueError(f"word_length out of range (1..960): {word_length}")
        data = self.extend_unit_read_bytes(head_address, word_length * 2, module_no)
        words = decode_device_words(data)
        if len(words) != word_length:
            raise SLMPError(f"extend unit read word size mismatch: expected={word_length}, actual={len(words)}")
        return words

    def extend_unit_read_word(self, head_address: int, module_no: int) -> int:
        """Read one 16-bit word from an extend-unit buffer."""
        return self.extend_unit_read_words(head_address, 1, module_no)[0]

    def extend_unit_read_dword(self, head_address: int, module_no: int) -> int:
        """Read one 32-bit value from an extend-unit buffer."""
        return int.from_bytes(self.extend_unit_read_bytes(head_address, 4, module_no), "little", signed=False)

    def extend_unit_write_bytes(self, head_address: int, module_no: int, data: bytes) -> None:
        _check_u32(head_address, "head_address")
        _check_u16(module_no, "module_no")
        if len(data) < 2 or len(data) > 0x0780:
            raise ValueError(f"data length out of range (2..1920): {len(data)}")
        payload = (
            head_address.to_bytes(4, "little")
            + len(data).to_bytes(2, "little")
            + module_no.to_bytes(2, "little")
            + data
        )
        self.request(Command.EXTEND_UNIT_WRITE, 0x0000, payload)

    def extend_unit_write_words(self, head_address: int, module_no: int, values: Sequence[int]) -> None:
        _check_u32(head_address, "head_address")
        if not values:
            raise ValueError("values must not be empty")
        if len(values) > 0x03C0:
            raise ValueError(f"word_length out of range (1..960): {len(values)}")
        payload = bytearray()
        for value in values:
            payload += int(value).to_bytes(2, "little", signed=False)
        self.extend_unit_write_bytes(head_address, module_no, bytes(payload))

    def extend_unit_write_word(self, head_address: int, module_no: int, value: int) -> None:
        """Write one 16-bit word to an extend-unit buffer."""
        _check_u16(value, "value")
        self.extend_unit_write_words(head_address, module_no, [value])

    def extend_unit_write_dword(self, head_address: int, module_no: int, value: int) -> None:
        """Write one 32-bit value to an extend-unit buffer."""
        _check_u32(value, "value")
        self.extend_unit_write_bytes(head_address, module_no, int(value).to_bytes(4, "little", signed=False))

    def cpu_buffer_read_bytes(self, head_address: int, byte_length: int, *, module_no: int = 0x03E0) -> bytes:
        """Read CPU buffer memory by extend-unit command using the CPU start I/O number."""
        return self.extend_unit_read_bytes(head_address, byte_length, module_no)

    def cpu_buffer_read_words(self, head_address: int, word_length: int, *, module_no: int = 0x03E0) -> list[int]:
        """Read CPU buffer memory words by extend-unit command using the CPU start I/O number."""
        return self.extend_unit_read_words(head_address, word_length, module_no)

    def cpu_buffer_read_word(self, head_address: int, *, module_no: int = 0x03E0) -> int:
        """Read one 16-bit CPU buffer word via the verified extend-unit path."""
        return self.extend_unit_read_word(head_address, module_no)

    def cpu_buffer_read_dword(self, head_address: int, *, module_no: int = 0x03E0) -> int:
        """Read one 32-bit CPU buffer value via the verified extend-unit path."""
        return self.extend_unit_read_dword(head_address, module_no)

    def cpu_buffer_write_bytes(self, head_address: int, data: bytes, *, module_no: int = 0x03E0) -> None:
        """Write CPU buffer memory by extend-unit command using the CPU start I/O number."""
        self.extend_unit_write_bytes(head_address, module_no, data)

    def cpu_buffer_write_words(self, head_address: int, values: Sequence[int], *, module_no: int = 0x03E0) -> None:
        """Write CPU buffer memory words by extend-unit command using the CPU start I/O number."""
        self.extend_unit_write_words(head_address, module_no, values)

    def cpu_buffer_write_word(self, head_address: int, value: int, *, module_no: int = 0x03E0) -> None:
        """Write one 16-bit CPU buffer word via the verified extend-unit path."""
        self.extend_unit_write_word(head_address, module_no, value)

    def cpu_buffer_write_dword(self, head_address: int, value: int, *, module_no: int = 0x03E0) -> None:
        """Write one 32-bit CPU buffer value via the verified extend-unit path."""
        self.extend_unit_write_dword(head_address, module_no, value)

    def remote_run_control(self, *, force: bool = False, clear_mode: int = 2) -> None:
        if clear_mode not in {0, 1, 2}:
            raise ValueError(f"clear_mode must be one of 0,1,2: {clear_mode}")
        mode = 0x0003 if force else 0x0001
        payload = mode.to_bytes(2, "little") + clear_mode.to_bytes(2, "little")
        self.request(Command.REMOTE_RUN, 0x0000, payload)

    def remote_stop_control(self) -> None:
        self.request(Command.REMOTE_STOP, 0x0000, b"\x01\x00")

    def remote_pause_control(self, *, force: bool = False) -> None:
        mode = 0x0003 if force else 0x0001
        self.request(Command.REMOTE_PAUSE, 0x0000, mode.to_bytes(2, "little"))

    def remote_latch_clear_control(self) -> None:
        self.request(Command.REMOTE_LATCH_CLEAR, 0x0000, b"\x01\x00")

    def remote_reset_control(self, *, subcommand: int = 0x0000, expect_response: bool | None = None) -> None:
        if subcommand not in {0x0000, 0x0001}:
            raise ValueError(f"remote reset subcommand must be 0x0000 or 0x0001: 0x{subcommand:04X}")
        should_wait = (subcommand != 0x0000) if expect_response is None else expect_response
        if should_wait:
            self.request(Command.REMOTE_RESET, subcommand, b"")
            return
        self._send_no_response(Command.REMOTE_RESET, subcommand, b"")

    def remote_password_lock_text(self, password: str, *, series: PLCSeries | str | None = None) -> None:
        s = PLCSeries(series) if series is not None else self.plc_series
        payload = _encode_remote_password_payload(password, series=s)
        self.request(Command.REMOTE_PASSWORD_LOCK, 0x0000, payload)

    def remote_password_unlock_text(self, password: str, *, series: PLCSeries | str | None = None) -> None:
        s = PLCSeries(series) if series is not None else self.plc_series
        payload = _encode_remote_password_payload(password, series=s)
        self.request(Command.REMOTE_PASSWORD_UNLOCK, 0x0000, payload)

    def self_test_loopback(self, data: bytes | str) -> bytes:
        loopback = data.encode("ascii") if isinstance(data, str) else bytes(data)
        if len(loopback) < 1 or len(loopback) > 960:
            raise ValueError(f"loopback data size out of range (1..960): {len(loopback)}")
        payload = len(loopback).to_bytes(2, "little") + loopback
        resp = self.request(Command.SELF_TEST, 0x0000, payload).data
        if len(resp) < 2:
            raise SLMPError(f"self test response too short: {len(resp)}")
        size = int.from_bytes(resp[:2], "little")
        body = resp[2:]
        if size != len(body):
            raise SLMPError(f"self test response size mismatch: size={size}, actual={len(body)}")
        return body

    def file_open_handle(
        self,
        *,
        filename: str,
        drive_no: int,
        subcommand: int = 0x0000,
        password: str | None = None,
        write_open: bool = True,
    ) -> int:
        _check_file_subcommand(subcommand, command=Command.FILE_OPEN)
        _check_u16(drive_no, "drive_no")
        payload = bytearray()
        payload += _encode_file_password(subcommand=subcommand, password=password)
        payload += (0x0001 if write_open else 0x0000).to_bytes(2, "little")
        payload += drive_no.to_bytes(2, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        data = self.request(Command.FILE_OPEN, subcommand, bytes(payload)).data
        if len(data) < 2:
            raise SLMPError(f"open file response too short: {len(data)}")
        return int.from_bytes(data[:2], "little")

    def file_close_handle(self, file_pointer_no: int, *, close_type: int = 0, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CLOSE)
        _check_u16(file_pointer_no, "file_pointer_no")
        if close_type not in {0, 1, 2}:
            raise ValueError(f"close_type must be 0, 1, or 2: {close_type}")
        payload = file_pointer_no.to_bytes(2, "little") + close_type.to_bytes(2, "little")
        self.request(Command.FILE_CLOSE, subcommand, payload)

    def file_read_chunk(
        self,
        file_pointer_no: int,
        *,
        offset: int = 0,
        size: int = 1920,
        subcommand: int = 0x0000,
    ) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_READ)
        _check_u16(file_pointer_no, "file_pointer_no")
        _check_u32(offset, "offset")
        _check_u16(size, "size")
        payload = file_pointer_no.to_bytes(2, "little") + offset.to_bytes(4, "little") + size.to_bytes(2, "little")
        data = self.request(Command.FILE_READ, subcommand, payload).data
        if len(data) < 2:
            raise SLMPError(f"read file response too short: {len(data)}")
        read_size = int.from_bytes(data[:2], "little")
        body = data[2:]
        if read_size != len(body):
            raise SLMPError(f"read file size mismatch: expected={read_size}, actual={len(body)}")
        return body

    def file_write_chunk(
        self,
        file_pointer_no: int,
        *,
        offset: int = 0,
        data: bytes = b"",
        subcommand: int = 0x0000,
    ) -> int:
        _check_file_subcommand(subcommand, command=Command.FILE_WRITE)
        _check_u16(file_pointer_no, "file_pointer_no")
        _check_u32(offset, "offset")
        _check_u16(len(data), "len(data)")
        payload = (
            file_pointer_no.to_bytes(2, "little")
            + offset.to_bytes(4, "little")
            + len(data).to_bytes(2, "little")
            + data
        )
        resp = self.request(Command.FILE_WRITE, subcommand, payload).data
        if len(resp) < 2:
            raise SLMPError(f"write file response too short: {len(resp)}")
        return int.from_bytes(resp[:2], "little")

    def file_new_file(
        self,
        *,
        filename: str,
        file_size: int,
        drive_no: int,
        subcommand: int = 0x0000,
        password: str | None = None,
    ) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_NEW)
        _check_u32(file_size, "file_size")
        _check_u16(drive_no, "drive_no")
        payload = bytearray()
        payload += _encode_file_password(subcommand=subcommand, password=password)
        payload += drive_no.to_bytes(2, "little")
        payload += file_size.to_bytes(4, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        self.request(Command.FILE_NEW, subcommand, bytes(payload))

    def file_delete_by_name(
        self,
        *,
        filename: str,
        drive_no: int,
        subcommand: int = 0x0000,
        password: str | None = None,
    ) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_DELETE)
        _check_u16(drive_no, "drive_no")
        payload = bytearray()
        payload += _encode_file_password(subcommand=subcommand, password=password)
        payload += drive_no.to_bytes(2, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        self.request(Command.FILE_DELETE, subcommand, bytes(payload))

    def file_change_state_by_name(
        self,
        *,
        filename: str,
        drive_no: int,
        attribute: int,
        subcommand: int = 0x0000,
        password: str | None = None,
    ) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CHANGE_STATE)
        _check_u16(drive_no, "drive_no")
        _check_u16(attribute, "attribute")
        payload = bytearray()
        payload += _encode_file_password(subcommand=subcommand, password=password)
        payload += drive_no.to_bytes(2, "little")
        payload += attribute.to_bytes(2, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        self.request(Command.FILE_CHANGE_STATE, subcommand, bytes(payload))

    def file_change_date_by_name(
        self,
        *,
        filename: str,
        drive_no: int,
        changed_at: datetime,
        subcommand: int = 0x0000,
    ) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CHANGE_DATE)
        _check_u16(drive_no, "drive_no")
        date_raw = _encode_file_date(changed_at.year, changed_at.month, changed_at.day)
        time_raw = _encode_file_time(changed_at.hour, changed_at.minute, changed_at.second)
        payload = bytearray()
        payload += drive_no.to_bytes(2, "little")
        payload += date_raw.to_bytes(2, "little")
        payload += time_raw.to_bytes(2, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        self.request(Command.FILE_CHANGE_DATE, subcommand, bytes(payload))

    def file_search_by_name(
        self,
        *,
        filename: str,
        drive_no: int,
        subcommand: int = 0x0000,
        password: str | None = None,
    ) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_SEARCH_DIRECTORY)
        _check_u16(drive_no, "drive_no")
        payload = bytearray()
        payload += _encode_file_password(subcommand=subcommand, password=password)
        payload += drive_no.to_bytes(2, "little")
        payload += _encode_file_name(subcommand=subcommand, filename=filename)
        return self.request(Command.FILE_SEARCH_DIRECTORY, subcommand, bytes(payload)).data

    def file_read_directory_entries(
        self,
        *,
        drive_no: int,
        head_file_no: int,
        requested_files: int,
        subcommand: int = 0x0000,
        directory_path: str = "",
    ) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_READ_DIRECTORY)
        _check_u16(drive_no, "drive_no")
        if requested_files < 1 or requested_files > 36:
            raise ValueError(f"requested_files out of range (1..36): {requested_files}")
        payload = bytearray()
        payload += drive_no.to_bytes(2, "little")
        if subcommand == 0x0040:
            _check_u32(head_file_no, "head_file_no")
            if head_file_no < 1:
                raise ValueError(f"head_file_no must be >= 1: {head_file_no}")
            payload += head_file_no.to_bytes(4, "little")
        else:
            _check_u16(head_file_no, "head_file_no")
            if head_file_no < 1:
                raise ValueError(f"head_file_no must be >= 1: {head_file_no}")
            payload += head_file_no.to_bytes(2, "little")
        payload += requested_files.to_bytes(2, "little")
        if subcommand == 0x0040:
            path = directory_path.encode("utf-16-le")
            char_len = len(path) // 2
            _check_u16(char_len, "directory_path char length")
            payload += char_len.to_bytes(2, "little")
            payload += path
        return self.request(Command.FILE_READ_DIRECTORY, subcommand, bytes(payload)).data

    # --------------------
    # Label command helpers (typed)
    # --------------------

    def array_label_read_points(
        self,
        points: Sequence[LabelArrayReadPoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> list[LabelArrayReadResult]:
        payload = self.build_array_label_read_payload(points, abbreviation_labels=abbreviation_labels)
        data = self.request(Command.LABEL_ARRAY_READ, 0x0000, payload).data
        return self.parse_array_label_read_response(data, expected_points=len(points))

    def array_label_write_points(
        self,
        points: Sequence[LabelArrayWritePoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> None:
        payload = self.build_array_label_write_payload(points, abbreviation_labels=abbreviation_labels)
        self.request(Command.LABEL_ARRAY_WRITE, 0x0000, payload)

    def label_read_random_points(
        self,
        labels: Sequence[str],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> list[LabelRandomReadResult]:
        payload = self.build_label_read_random_payload(labels, abbreviation_labels=abbreviation_labels)
        data = self.request(Command.LABEL_READ_RANDOM, 0x0000, payload).data
        return self.parse_label_read_random_response(data, expected_points=len(labels))

    def label_write_random_points(
        self,
        points: Sequence[LabelRandomWritePoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> None:
        payload = self.build_label_write_random_payload(points, abbreviation_labels=abbreviation_labels)
        self.request(Command.LABEL_WRITE_RANDOM, 0x0000, payload)

    @staticmethod
    def build_array_label_read_payload(
        points: Sequence[LabelArrayReadPoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> bytes:
        if not points:
            raise ValueError("points must not be empty")
        _check_u16(len(points), "number of array points")
        _check_u16(len(abbreviation_labels), "number of abbreviation points")
        payload = bytearray()
        payload += len(points).to_bytes(2, "little")
        payload += len(abbreviation_labels).to_bytes(2, "little")
        for name in abbreviation_labels:
            payload += _encode_label_name(name)
        for point in points:
            _check_label_unit_specification(point.unit_specification, "unit_specification")
            _check_u16(point.array_data_length, "array_data_length")
            payload += _encode_label_name(point.label)
            payload += point.unit_specification.to_bytes(1, "little")
            payload += b"\x00"
            payload += point.array_data_length.to_bytes(2, "little")
        return bytes(payload)

    @staticmethod
    def build_array_label_write_payload(
        points: Sequence[LabelArrayWritePoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> bytes:
        if not points:
            raise ValueError("points must not be empty")
        _check_u16(len(points), "number of array points")
        _check_u16(len(abbreviation_labels), "number of abbreviation points")
        payload = bytearray()
        payload += len(points).to_bytes(2, "little")
        payload += len(abbreviation_labels).to_bytes(2, "little")
        for name in abbreviation_labels:
            payload += _encode_label_name(name)
        for point in points:
            _check_label_unit_specification(point.unit_specification, "unit_specification")
            _check_u16(point.array_data_length, "array_data_length")
            raw = bytes(point.data)
            expected = _label_array_data_bytes(point.unit_specification, point.array_data_length)
            if len(raw) != expected:
                raise ValueError(
                    "array label write data size mismatch: "
                    f"expected={expected}, actual={len(raw)}, unit_specification={point.unit_specification}, "
                    f"array_data_length={point.array_data_length}"
                )
            payload += _encode_label_name(point.label)
            payload += point.unit_specification.to_bytes(1, "little")
            payload += b"\x00"
            payload += point.array_data_length.to_bytes(2, "little")
            payload += raw
        return bytes(payload)

    @staticmethod
    def build_label_read_random_payload(
        labels: Sequence[str],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> bytes:
        if not labels:
            raise ValueError("labels must not be empty")
        _check_u16(len(labels), "number of read data points")
        _check_u16(len(abbreviation_labels), "number of abbreviation points")
        payload = bytearray()
        payload += len(labels).to_bytes(2, "little")
        payload += len(abbreviation_labels).to_bytes(2, "little")
        for name in abbreviation_labels:
            payload += _encode_label_name(name)
        for label in labels:
            payload += _encode_label_name(label)
        return bytes(payload)

    @staticmethod
    def build_label_write_random_payload(
        points: Sequence[LabelRandomWritePoint],
        *,
        abbreviation_labels: Sequence[str] = (),
    ) -> bytes:
        if not points:
            raise ValueError("points must not be empty")
        _check_u16(len(points), "number of write data points")
        _check_u16(len(abbreviation_labels), "number of abbreviation points")
        payload = bytearray()
        payload += len(points).to_bytes(2, "little")
        payload += len(abbreviation_labels).to_bytes(2, "little")
        for name in abbreviation_labels:
            payload += _encode_label_name(name)
        for point in points:
            raw = bytes(point.data)
            _check_u16(len(raw), "write data length")
            payload += _encode_label_name(point.label)
            payload += len(raw).to_bytes(2, "little")
            payload += raw
        return bytes(payload)

    @staticmethod
    def parse_array_label_read_response(
        data: bytes,
        *,
        expected_points: int | None = None,
    ) -> list[LabelArrayReadResult]:
        if len(data) < 2:
            raise SLMPError(f"array label read response too short: {len(data)}")
        points = int.from_bytes(data[:2], "little")
        if expected_points is not None and points != expected_points:
            raise SLMPError(f"array label read point count mismatch: expected={expected_points}, actual={points}")
        offset = 2
        out: list[LabelArrayReadResult] = []
        for _ in range(points):
            if offset + 4 > len(data):
                raise SLMPError("array label read response truncated before metadata")
            data_type_id = data[offset]
            unit_specification = data[offset + 1]
            _check_label_unit_specification(unit_specification, "response unit_specification")
            array_data_length = int.from_bytes(data[offset + 2 : offset + 4], "little")
            offset += 4
            data_size = _label_array_data_bytes(unit_specification, array_data_length)
            if offset + data_size > len(data):
                raise SLMPError(
                    "array label read response truncated in data payload: "
                    f"needed={data_size}, remaining={len(data) - offset}"
                )
            raw = data[offset : offset + data_size]
            offset += data_size
            out.append(
                LabelArrayReadResult(
                    data_type_id=data_type_id,
                    unit_specification=unit_specification,
                    array_data_length=array_data_length,
                    data=raw,
                )
            )
        if offset != len(data):
            raise SLMPError(f"array label read response has trailing bytes: {len(data) - offset}")
        return out

    @staticmethod
    def parse_label_read_random_response(
        data: bytes,
        *,
        expected_points: int | None = None,
    ) -> list[LabelRandomReadResult]:
        if len(data) < 2:
            raise SLMPError(f"label random read response too short: {len(data)}")
        points = int.from_bytes(data[:2], "little")
        if expected_points is not None and points != expected_points:
            raise SLMPError(f"label random read point count mismatch: expected={expected_points}, actual={points}")
        offset = 2
        out: list[LabelRandomReadResult] = []
        for _ in range(points):
            if offset + 4 > len(data):
                raise SLMPError("label random read response truncated before metadata")
            data_type_id = data[offset]
            spare = data[offset + 1]
            read_data_length = int.from_bytes(data[offset + 2 : offset + 4], "little")
            offset += 4
            if offset + read_data_length > len(data):
                raise SLMPError(
                    "label random read response truncated in data payload: "
                    f"needed={read_data_length}, remaining={len(data) - offset}"
                )
            raw = data[offset : offset + read_data_length]
            offset += read_data_length
            out.append(
                LabelRandomReadResult(
                    data_type_id=data_type_id,
                    spare=spare,
                    read_data_length=read_data_length,
                    data=raw,
                )
            )
        if offset != len(data):
            raise SLMPError(f"label random read response has trailing bytes: {len(data) - offset}")
        return out

    # --------------------
    # Full command wrappers (raw payload)
    # --------------------

    def array_label_read(self, payload: bytes = b"") -> bytes:
        return self.request(Command.LABEL_ARRAY_READ, 0x0000, payload).data

    def array_label_write(self, payload: bytes = b"") -> None:
        self.request(Command.LABEL_ARRAY_WRITE, 0x0000, payload)

    def label_read_random(self, payload: bytes = b"") -> bytes:
        return self.request(Command.LABEL_READ_RANDOM, 0x0000, payload).data

    def label_write_random(self, payload: bytes = b"") -> None:
        self.request(Command.LABEL_WRITE_RANDOM, 0x0000, payload)

    def memory_read(self, payload: bytes = b"") -> bytes:
        return self.request(Command.MEMORY_READ, 0x0000, payload).data

    def memory_write(self, payload: bytes = b"") -> None:
        self.request(Command.MEMORY_WRITE, 0x0000, payload)

    def extend_unit_read(self, payload: bytes = b"") -> bytes:
        return self.request(Command.EXTEND_UNIT_READ, 0x0000, payload).data

    def extend_unit_write(self, payload: bytes = b"") -> None:
        self.request(Command.EXTEND_UNIT_WRITE, 0x0000, payload)

    def remote_run(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_RUN, 0x0000, payload)

    def remote_stop(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_STOP, 0x0000, payload)

    def remote_pause(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_PAUSE, 0x0000, payload)

    def remote_latch_clear(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_LATCH_CLEAR, 0x0000, payload)

    def remote_reset(self, payload: bytes = b"") -> None:
        if payload:
            raise ValueError("remote reset does not use request data")
        self.remote_reset_control(subcommand=0x0000, expect_response=False)

    def read_type_name(self) -> TypeNameInfo:
        data = self.request(Command.READ_TYPE_NAME, 0x0000, b"").data
        model = ""
        model_code = None
        if len(data) >= 16:
            model = data[:16].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        if len(data) >= 18:
            model_code = int.from_bytes(data[16:18], "little")
        return TypeNameInfo(raw=data, model=model, model_code=model_code)

    def remote_password_lock(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_PASSWORD_LOCK, 0x0000, payload)

    def remote_password_unlock(self, payload: bytes = b"") -> None:
        self.request(Command.REMOTE_PASSWORD_UNLOCK, 0x0000, payload)

    def file_read_directory(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_READ_DIRECTORY)
        return self.request(Command.FILE_READ_DIRECTORY, subcommand, payload).data

    def file_search_directory(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_SEARCH_DIRECTORY)
        return self.request(Command.FILE_SEARCH_DIRECTORY, subcommand, payload).data

    def file_new(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_NEW)
        self.request(Command.FILE_NEW, subcommand, payload)

    def file_delete(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_DELETE)
        self.request(Command.FILE_DELETE, subcommand, payload)

    def file_copy(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_COPY)
        self.request(Command.FILE_COPY, subcommand, payload)

    def file_change_state(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CHANGE_STATE)
        self.request(Command.FILE_CHANGE_STATE, subcommand, payload)

    def file_change_date(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CHANGE_DATE)
        self.request(Command.FILE_CHANGE_DATE, subcommand, payload)

    def file_open(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_OPEN)
        return self.request(Command.FILE_OPEN, subcommand, payload).data

    def file_read(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_READ)
        return self.request(Command.FILE_READ, subcommand, payload).data

    def file_write(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> bytes:
        _check_file_subcommand(subcommand, command=Command.FILE_WRITE)
        return self.request(Command.FILE_WRITE, subcommand, payload).data

    def file_close(self, payload: bytes = b"", *, subcommand: int = 0x0000) -> None:
        _check_file_subcommand(subcommand, command=Command.FILE_CLOSE)
        self.request(Command.FILE_CLOSE, subcommand, payload)

    def self_test(self, payload: bytes = b"") -> bytes:
        return self.request(Command.SELF_TEST, 0x0000, payload).data

    def clear_error(self, payload: bytes = b"") -> None:
        self.request(Command.CLEAR_ERROR, 0x0000, payload)

    def receive_request(self, *, timeout: float | None = None) -> SLMPRequest:
        raw = self._receive_frame(timeout=timeout)
        return decode_4e_request(raw)

    def receive_ondemand(self, *, timeout: float | None = None) -> bytes:
        req = self.receive_request(timeout=timeout)
        if req.command != int(Command.ONDEMAND) or req.subcommand != 0x0000:
            raise SLMPError(
                f"unexpected incoming command: command=0x{req.command:04X} subcommand=0x{req.subcommand:04X}"
            )
        return req.data

    def ondemand(self, payload: bytes = b"", *, timeout: float | None = None) -> bytes:
        if payload:
            raise ValueError("ondemand is PLC-initiated; do not send request data from the external device")
        return self.receive_ondemand(timeout=timeout)

    # --------------------
    # Internal I/O
    # --------------------

    def _send_no_response(
        self,
        command: int | Command,
        subcommand: int,
        data: bytes,
        *,
        serial: int | None = None,
        target: SLMPTarget | None = None,
        monitoring_timer: int | None = None,
    ) -> None:
        serial_no = self._next_serial() if serial is None else serial
        target_info = target or self.default_target
        monitor = self.monitoring_timer if monitoring_timer is None else monitoring_timer

        frame = encode_4e_request(
            serial=serial_no,
            target=target_info,
            monitoring_timer=monitor,
            command=int(command),
            subcommand=subcommand,
            data=data,
        )
        self.open()
        assert self._sock is not None
        if self.transport == "tcp":
            self._sock.sendall(frame)
            self._emit_trace(
                {
                    "serial": serial_no,
                    "command": int(command),
                    "subcommand": subcommand,
                    "request_data": data,
                    "request_frame": frame,
                    "response_frame": b"",
                    "response_end_code": None,
                    "target": target_info,
                    "monitoring_timer": monitor,
                }
            )
            return
        self._sock.sendto(frame, (self.host, self.port))
        self._emit_trace(
            {
                "serial": serial_no,
                "command": int(command),
                "subcommand": subcommand,
                "request_data": data,
                "request_frame": frame,
                "response_frame": b"",
                "response_end_code": None,
                "target": target_info,
                "monitoring_timer": monitor,
            }
        )

    def _next_serial(self) -> int:
        serial = self._serial & 0xFFFF
        self._serial = (self._serial + 1) & 0xFFFF
        return serial

    def _send_and_receive(self, frame: bytes) -> bytes:
        self.open()
        assert self._sock is not None

        if self.transport == "tcp":
            self._sock.sendall(frame)
            return self._receive_frame()

        self._sock.sendto(frame, (self.host, self.port))
        return self._receive_frame()

    def _receive_frame(self, *, timeout: float | None = None) -> bytes:
        self.open()
        assert self._sock is not None
        previous_timeout = self._sock.gettimeout()
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            if self.transport == "tcp":
                return _recv_tcp_frame(self._sock)
            data, _ = self._sock.recvfrom(65535)
            return data
        finally:
            if timeout is not None:
                self._sock.settimeout(previous_timeout)

    def _emit_trace(self, trace: dict[str, Any]) -> None:
        if self.trace_hook is None:
            return
        try:
            self.trace_hook(trace)
        except Exception:
            # Trace callback failures must not affect protocol behavior.
            pass


def _recv_tcp_frame(sock: socket.socket) -> bytes:
    # Up to response_data_length field (13 bytes total for 4E response header part).
    head = _recv_exact(sock, 13)
    response_data_length = int.from_bytes(head[11:13], "little")
    tail = _recv_exact(sock, response_data_length)
    return head + tail


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise SLMPError("connection closed while receiving data")
        buf.extend(chunk)
    return bytes(buf)


def _normalize_items(
    values: Mapping[str | DeviceRef, Any] | Sequence[tuple[str | DeviceRef, Any]],
) -> list[tuple[DeviceRef, Any]]:
    if isinstance(values, Mapping):
        items = list(values.items())
    else:
        items = list(values)
    return [(parse_device(device), value) for device, value in items]


_LT_LST_DIRECT_CODES = frozenset({"LTC", "LTS", "LSTC", "LSTS"})
_CPU_BUFFER_CODES = frozenset({"G", "HG"})
_TEMPORARILY_UNSUPPORTED_TYPED_CODES = frozenset({"G", "HG", "S"})
_BOUNDARY_START_ACCEPTANCE_CODES = frozenset({"R", "ZR"})


def _check_temporarily_unsupported_device(ref: DeviceRef) -> None:
    if ref.code not in _TEMPORARILY_UNSUPPORTED_TYPED_CODES:
        return
    if ref.code in {"G", "HG"}:
        raise SLMPUnsupportedDeviceError(
            f"{ref.code} is temporarily unsupported in typed device APIs on this project; "
            "the accepted SLMP access condition is still unresolved and should be revisited when the cause is known"
        )
    raise SLMPUnsupportedDeviceError(
        f"{ref.code} is temporarily unsupported in typed device APIs on this project; "
        "the access path should be revisited when the cause is known"
    )


def _check_temporarily_unsupported_devices(refs: Sequence[DeviceRef]) -> None:
    for ref in refs:
        _check_temporarily_unsupported_device(ref)


def _warn_practical_device_path(ref: DeviceRef, *, series: PLCSeries, access_kind: str) -> None:
    if series != PLCSeries.IQR:
        return
    if access_kind == "direct" and ref.code in _LT_LST_DIRECT_CODES:
        warnings.warn(
            (
                f"direct access to {ref.code} is known to fail on the validated iQ-R target; "
                "use read_ltc_states/read_lts_states/read_lstc_states/read_lsts_states "
                "or read_long_timer/read_long_retentive_timer instead"
            ),
            SLMPPracticalPathWarning,
            stacklevel=3,
        )
        return
    if ref.code in _CPU_BUFFER_CODES:
        if access_kind == "direct":
            warnings.warn(
                (
                    f"direct access to {ref.code} is known to fail on the validated iQ-R target; "
                    "use cpu_buffer_* or extend_unit_* helpers instead"
                ),
                SLMPPracticalPathWarning,
                stacklevel=3,
            )
        elif access_kind == "appendix1":
            warnings.warn(
                (
                    f"Appendix 1 access to {ref.code} is known to fail on the validated iQ-R target; "
                    "use cpu_buffer_* or extend_unit_* helpers instead"
                ),
                SLMPPracticalPathWarning,
                stacklevel=3,
            )


def _warn_boundary_behavior(
    ref: DeviceRef,
    *,
    series: PLCSeries,
    points: int,
    write: bool,
    bit_unit: bool,
    access_kind: str,
) -> None:
    if series != PLCSeries.IQR or access_kind != "direct" or points <= 0 or bit_unit:
        return
    if ref.code in _BOUNDARY_START_ACCEPTANCE_CODES and points > 1:
        warnings.warn(
            (
                f"multi-point direct access to {ref.code} may not be rejected at the configured upper bound "
                "on the validated iQ-R target; acceptance appeared to depend mainly on the start address. "
                "Validate live boundary behavior if exact range enforcement matters."
            ),
            SLMPBoundaryBehaviorWarning,
            stacklevel=3,
        )
    if write and ref.code == "LZ" and points % 2 != 0:
        warnings.warn(
            (
                "direct LZ write with an odd word count may be rejected with 0xC051 on the validated iQ-R target; "
                "two-word units were required in live verification."
            ),
            SLMPBoundaryBehaviorWarning,
            stacklevel=3,
        )


def _check_points_u16(points: int, name: str) -> None:
    if points < 0 or points > 0xFFFF:
        raise ValueError(f"{name} out of range (0..65535): {points}")


def _check_u8(value: int, name: str) -> None:
    if value < 0 or value > 0xFF:
        raise ValueError(f"{name} out of range (0..255): {value}")


def _check_u16(value: int, name: str) -> None:
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"{name} out of range (0..65535): {value}")


def _check_u32(value: int, name: str) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"{name} out of range (0..4294967295): {value}")


def _check_random_read_like_counts(word_points: int, dword_points: int, *, series: PLCSeries, name: str) -> None:
    total = word_points + dword_points
    limit = 96 if series == PLCSeries.IQR else 192
    if total < 1 or total > limit:
        raise ValueError(
            f"{name} total access points out of range (1..{limit}) for {series.value}: "
            f"word={word_points}, dword={dword_points}"
        )


def _check_random_bit_write_count(points: int, *, series: PLCSeries, name: str) -> None:
    limit = 94 if series == PLCSeries.IQR else 188
    if points < 1 or points > limit:
        raise ValueError(f"{name} bit access points out of range (1..{limit}) for {series.value}: {points}")


def _check_block_request_limits(
    word_blocks: Sequence[tuple[str | DeviceRef, int | Sequence[object]]],
    bit_blocks: Sequence[tuple[str | DeviceRef, int | Sequence[object]]],
    *,
    series: PLCSeries,
    name: str,
) -> None:
    total_blocks = len(word_blocks) + len(bit_blocks)
    block_limit = 60 if series == PLCSeries.IQR else 120
    if total_blocks < 1 or total_blocks > block_limit:
        raise ValueError(
            f"{name} total block count out of range (1..{block_limit}) for {series.value}: {total_blocks}"
        )

    total_points = 0
    for _, points in word_blocks:
        total_points += int(points) if isinstance(points, int) else len(points)
    for _, points in bit_blocks:
        total_points += int(points) if isinstance(points, int) else len(points)
    if total_points > 960:
        raise ValueError(f"{name} total device points out of range (<=960): {total_points}")


_FILE_COMMAND_SUBCOMMANDS: dict[int, set[int]] = {
    int(Command.FILE_READ_DIRECTORY): {0x0000, 0x0040},
    int(Command.FILE_SEARCH_DIRECTORY): {0x0000, 0x0040},
    int(Command.FILE_NEW): {0x0000, 0x0040},
    int(Command.FILE_DELETE): {0x0000, 0x0004, 0x0040},
    int(Command.FILE_COPY): {0x0000, 0x0004, 0x0040},
    int(Command.FILE_CHANGE_STATE): {0x0000, 0x0004, 0x0040},
    int(Command.FILE_CHANGE_DATE): {0x0000, 0x0040},
    int(Command.FILE_OPEN): {0x0000, 0x0004, 0x0040},
    int(Command.FILE_READ): {0x0000},
    int(Command.FILE_WRITE): {0x0000},
    int(Command.FILE_CLOSE): {0x0000},
}


def _check_file_subcommand(subcommand: int, *, command: int | Command) -> None:
    cmd = int(command)
    allowed = _FILE_COMMAND_SUBCOMMANDS.get(cmd)
    if allowed is None:
        raise ValueError(f"unsupported file command for subcommand check: 0x{cmd:04X}")
    if subcommand not in allowed:
        allowed_text = ", ".join(f"0x{value:04X}" for value in sorted(allowed))
        raise ValueError(
            f"unsupported file subcommand for command 0x{cmd:04X}: 0x{subcommand:04X} "
            f"(allowed: {allowed_text})"
        )


def _encode_label_name(label: str) -> bytes:
    if not label:
        raise ValueError("label must not be empty")
    raw = label.encode("utf-16-le")
    if len(raw) % 2 != 0:
        raise ValueError("label utf-16 length must be even")
    chars = len(raw) // 2
    _check_u16(chars, "label name length")
    return chars.to_bytes(2, "little") + raw


def _check_label_unit_specification(value: int, name: str) -> None:
    if value not in {0, 1}:
        raise ValueError(f"{name} must be 0(bit) or 1(byte): {value}")


def _label_array_data_bytes(unit_specification: int, array_data_length: int) -> int:
    _check_label_unit_specification(unit_specification, "unit_specification")
    _check_u16(array_data_length, "array_data_length")
    if unit_specification == 0:
        return array_data_length * 2
    return array_data_length


def _encode_remote_password_payload(password: str, *, series: PLCSeries) -> bytes:
    pwd = password.encode("ascii")
    if series == PLCSeries.QL:
        if len(pwd) > 4:
            raise ValueError("password length for Q/L must be <= 4")
        return (4).to_bytes(2, "little") + pwd.ljust(4, b" ")
    if len(pwd) < 6 or len(pwd) > 32:
        raise ValueError("password length for iQ-R/iQ-L must be 6..32")
    return len(pwd).to_bytes(2, "little") + pwd


def _encode_file_password(*, subcommand: int, password: str | None) -> bytes:
    if subcommand == 0x0000:
        pwd = (password or "").encode("ascii")
        if len(pwd) > 4:
            raise ValueError("password length for subcommand 0000 must be <= 4")
        return pwd.ljust(4, b" ")
    if subcommand == 0x0004:
        pwd = (password or "").encode("ascii")
        if len(pwd) > 32:
            raise ValueError("password length for subcommand 0004 must be <= 32")
        return pwd.ljust(32, b" ")
    # 0040
    pwd = (password or "").encode("ascii")
    if len(pwd) == 0:
        return b"\x00\x00"
    if len(pwd) < 6 or len(pwd) > 32:
        raise ValueError("password length for subcommand 0040 must be 0 or 6..32")
    return len(pwd).to_bytes(2, "little") + pwd


def _encode_file_name(*, subcommand: int, filename: str) -> bytes:
    if subcommand in {0x0000, 0x0004}:
        raw = filename.encode("ascii")
        if len(raw) > 12:
            raise ValueError("filename length for subcommand 0000/0004 must be <= 12 bytes")
        return len(raw).to_bytes(2, "little") + raw

    # 0040: UTF-16 path from root (drive name is excluded in spec).
    utf16 = filename.encode("utf-16-le")
    chars = len(utf16) // 2
    if chars > 252:
        raise ValueError("filename/path length for subcommand 0040 must be <= 252 chars")
    return chars.to_bytes(2, "little") + utf16


def _encode_file_date(year: int, month: int, day: int) -> int:
    if year < 1980 or year > 2107:
        raise ValueError(f"year out of range for file date (1980..2107): {year}")
    if month < 1 or month > 12:
        raise ValueError(f"month out of range (1..12): {month}")
    if day < 1 or day > 31:
        raise ValueError(f"day out of range (1..31): {day}")
    return ((year - 1980) << 9) | (month << 5) | day


def _encode_file_time(hour: int, minute: int, second: int) -> int:
    if hour < 0 or hour > 23:
        raise ValueError(f"hour out of range (0..23): {hour}")
    if minute < 0 or minute > 59:
        raise ValueError(f"minute out of range (0..59): {minute}")
    if second < 0 or second > 59:
        raise ValueError(f"second out of range (0..59): {second}")
    return (hour << 11) | (minute << 5) | (second // 2)

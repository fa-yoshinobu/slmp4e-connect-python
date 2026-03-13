import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from slmp4e import cli
from slmp4e.client import (
    BlockReadResult,
    LabelArrayReadPoint,
    LabelArrayReadResult,
    LabelArrayWritePoint,
    LabelRandomReadResult,
    LabelRandomWritePoint,
    LongTimerResult,
    MonitorResult,
    RandomReadResult,
    SLMP4EClient,
    TypeNameInfo,
)
from slmp4e.constants import Command, PLCSeries
from slmp4e.core import (
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
    encode_4e_request,
    encode_device_spec,
    encode_extended_device_spec,
    pack_bit_values,
    parse_device,
    unpack_bit_values,
)


class FakeClient(SLMP4EClient):
    def __init__(self) -> None:
        super().__init__("127.0.0.1")
        self.last_request = None
        self.requests = []
        self.next_response_data = b""
        self.last_no_response = None

    def request(self, command, subcommand=0x0000, data=b"", **kwargs):  # type: ignore[override]
        self.last_request = (int(command), subcommand, data, kwargs)
        self.requests.append(self.last_request)
        return SLMPResponse(
            serial=0,
            target=SLMPTarget(),
            end_code=0,
            data=self.next_response_data,
            raw=b"",
        )

    def _send_no_response(self, command, subcommand, data, **kwargs):  # type: ignore[override]
        self.last_no_response = (int(command), subcommand, data, kwargs)


class FakeReceiveClient(SLMP4EClient):
    def __init__(self) -> None:
        super().__init__("127.0.0.1")
        self.next_request = SLMPRequest(
            serial=0,
            target=SLMPTarget(),
            monitoring_timer=0x0010,
            command=int(Command.ONDEMAND),
            subcommand=0x0000,
            data=b"",
            raw=b"",
        )

    def receive_request(self, *, timeout=None):  # type: ignore[override]
        return self.next_request


class TestCodec(unittest.TestCase):
    def test_decode_4e_request(self) -> None:
        frame = encode_4e_request(
            serial=0x1234,
            target=SLMPTarget(network=1, station=2, module_io=0x03FF, multidrop=0),
            monitoring_timer=0x0010,
            command=0x0401,
            subcommand=0x0000,
            data=b"\xAA\xBB",
        )
        req = decode_4e_request(frame)
        self.assertEqual(req.serial, 0x1234)
        self.assertEqual(req.target.network, 1)
        self.assertEqual(req.target.station, 2)
        self.assertEqual(req.monitoring_timer, 0x0010)
        self.assertEqual(req.command, 0x0401)
        self.assertEqual(req.subcommand, 0x0000)
        self.assertEqual(req.data, b"\xAA\xBB")

    def test_encode_4e_request(self) -> None:
        frame = encode_4e_request(
            serial=0x1234,
            target=SLMPTarget(network=1, station=2, module_io=0x03FF, multidrop=0),
            monitoring_timer=0x0010,
            command=0x0401,
            subcommand=0x0000,
            data=b"\xAA\xBB",
        )
        self.assertEqual(frame[:2], b"\x54\x00")
        self.assertEqual(frame[2:4], b"\x34\x12")
        self.assertEqual(frame[6], 1)
        self.assertEqual(frame[7], 2)
        self.assertEqual(frame[8:10], b"\xFF\x03")
        self.assertEqual(frame[11:13], (8).to_bytes(2, "little"))  # timer + cmd + subcmd + 2-byte payload
        self.assertEqual(frame[13:15], b"\x10\x00")
        self.assertEqual(frame[15:17], b"\x01\x04")
        self.assertEqual(frame[17:19], b"\x00\x00")
        self.assertEqual(frame[19:], b"\xAA\xBB")

    def test_decode_4e_response(self) -> None:
        # D4 00 / serial / reserve / dest / len / endcode / data
        frame = (
            b"\xD4\x00"
            + b"\x34\x12"
            + b"\x00\x00"
            + b"\x01\x02\xFF\x03\x00"
            + b"\x06\x00"
            + b"\x00\x00"
            + b"\x11\x22\x33\x44"
        )
        resp = decode_4e_response(frame)
        self.assertEqual(resp.serial, 0x1234)
        self.assertEqual(resp.target.network, 1)
        self.assertEqual(resp.target.station, 2)
        self.assertEqual(resp.end_code, 0)
        self.assertEqual(resp.data, b"\x11\x22\x33\x44")

    def test_device_and_bit_helpers(self) -> None:
        self.assertEqual(str(parse_device("D100")), "D100")
        self.assertEqual(str(parse_device("X20")), "X20")
        self.assertEqual(encode_device_spec("D100", series=PLCSeries.QL), b"\x64\x00\x00\xA8")
        self.assertEqual(encode_device_spec("D100", series=PLCSeries.IQR), b"\x64\x00\x00\x00\xA8\x00")

        raw = pack_bit_values([1, 0, 1, 1, 0])
        self.assertEqual(raw, b"\x10\x11\x00")
        bits = unpack_bit_values(raw, 5)
        self.assertEqual(bits, [True, False, True, True, False])

    def test_extension_helpers(self) -> None:
        flags_ql = build_device_modification_flags(
            series=PLCSeries.QL,
            use_indirect_specification=True,
            register_mode="z",
        )
        self.assertEqual(flags_ql, 0x48)

        ext = ExtensionSpec(
            extension_specification=0x0001,
            extension_specification_modification=0x00,
            device_modification_index=0x04,
            device_modification_flags=0x40,
            direct_memory_specification=0xF9,
        )
        data = encode_extended_device_spec("W100", series=PLCSeries.QL, extension=ext)
        self.assertEqual(data, b"\x01\x00\x00\x04\x40\x00\x01\x00\xB4\xF9")

    def test_parse_named_target(self) -> None:
        parsed = cli._parse_named_target("remote1,0x00,0x01,0x03FF,0x00")
        self.assertEqual(parsed.name, "remote1")
        self.assertEqual(parsed.target.network, 0x00)
        self.assertEqual(parsed.target.station, 0x01)
        self.assertEqual(parsed.target.module_io, 0x03FF)
        self.assertEqual(parsed.target.multidrop, 0x00)

    def test_load_named_targets_from_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "targets.txt"
            path.write_text("# comment\nremote1,0x00,0x01,0x03FF,0x00\n", encoding="utf-8")
            loaded = cli._load_named_targets(None, str(path))
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "remote1")
        self.assertEqual(loaded[0].target.station, 0x01)

    def test_parse_boundary_spec(self) -> None:
        parsed = cli._parse_boundary_spec("D,D10239,word")
        self.assertEqual(parsed.label, "D")
        self.assertEqual(parsed.last_device, "D10239")
        self.assertFalse(parsed.bit_unit)
        self.assertEqual(parsed.span_points, 1)

        parsed = cli._parse_boundary_spec("X,X2FFF,bit,1")
        self.assertEqual(parsed.last_device, "X2FFF")
        self.assertTrue(parsed.bit_unit)
        self.assertEqual(parsed.span_points, 1)

        parsed = cli._parse_boundary_spec("LTN,LTN1023,word,4")
        self.assertEqual(parsed.span_points, 4)

    def test_load_boundary_specs_from_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranges.txt"
            path.write_text("# comment\nD,D10239,word\nLTN,LTN1023,word,4\n", encoding="utf-8")
            loaded = cli._load_boundary_specs(None, str(path))
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].last_device, "D10239")
        self.assertEqual(loaded[1].last_device, "LTN1023")
        self.assertFalse(loaded[1].bit_unit)
        self.assertEqual(loaded[1].span_points, 4)

    def test_increment_device_text_uses_device_radix(self) -> None:
        self.assertEqual(cli._increment_device_text("D10239"), "D10240")
        self.assertEqual(cli._increment_device_text("X2FFF"), "X3000")
        self.assertEqual(cli._increment_device_text("ZR163839"), "ZR163840")
        self.assertEqual(cli._offset_device_text("D1000", 25), "D1025")
        self.assertEqual(cli._offset_device_text("X20", 0x10), "X30")

    def test_parse_focused_boundary_spec(self) -> None:
        parsed = cli._parse_focused_boundary_spec("ZR,ZR163839,word,1/2/3/16/64,1/2")
        self.assertEqual(parsed.label, "ZR")
        self.assertEqual(parsed.edge_device, "ZR163839")
        self.assertFalse(parsed.bit_unit)
        self.assertEqual(parsed.edge_points, (1, 2, 3, 16, 64))
        self.assertEqual(parsed.next_points, (1, 2))

    def test_load_focused_boundary_specs_defaults_when_unspecified(self) -> None:
        loaded = cli._load_focused_boundary_specs(None, None)
        self.assertGreaterEqual(len(loaded), 1)
        self.assertEqual(loaded[0].label, "Z")

    def test_model_scoped_default_paths(self) -> None:
        self.assertEqual(
            cli._default_report_output(series="iqr", model="R08CPU", filename="probe_latest.md"),
            str(Path("internal_docs") / "iqr_r08cpu" / "probe_latest.md"),
        )
        self.assertEqual(
            cli._default_capture_dir(series="iqr", model="R08CPU", dirname="frame_dumps_appendix1"),
            Path("internal_docs") / "iqr_r08cpu" / "frame_dumps_appendix1",
        )
        self.assertEqual(
            cli._resolve_capture_dir(
                output_dir=None,
                series="iqr",
                model="R08CPU",
                dirname="frame_dumps_appendix1",
            ),
            Path("internal_docs") / "iqr_r08cpu" / "frame_dumps_appendix1",
        )

    def test_write_markdown_report_creates_latest_and_archive(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "internal_docs" / "iqr_r08cpu" / "probe_latest.md"
            cli._write_markdown_report(
                str(output),
                title="# Probe",
                header_lines=["- Host: 127.0.0.1"],
                rows=[("0101", "OK", "model=R08CPU")],
            )

            self.assertTrue(output.exists())
            archive_dir = output.parent / "archive"
            self.assertTrue(archive_dir.exists())
            archived = list(archive_dir.glob("probe_*.md"))
            self.assertEqual(len(archived), 1)
            self.assertIn("| 0101 | OK | model=R08CPU |", output.read_text(encoding="utf-8"))
            self.assertEqual(output.read_text(encoding="utf-8"), archived[0].read_text(encoding="utf-8"))

    def test_initialize_model_docs_creates_scaffold(self) -> None:
        with TemporaryDirectory() as tmp:
            model_dir, created, skipped = cli._initialize_model_docs(
                root=Path(tmp),
                series="iqr",
                model="R08CPU",
            )
            self.assertEqual(model_dir, Path(tmp) / "iqr_r08cpu")
            self.assertEqual(skipped, [])
            self.assertTrue((model_dir / "README.md").exists())
            self.assertTrue((model_dir / "device_access_matrix.csv").exists())
            self.assertTrue((model_dir / "current_plc_boundary_specs_example.txt").exists())
            self.assertTrue((model_dir / "current_register_boundary_focus_specs_example.txt").exists())
            self.assertTrue((model_dir / "other_station_targets_example.txt").exists())
            self.assertTrue((model_dir / "wireshark" / "README.md").exists())
            self.assertTrue((model_dir / "frame_dumps_appendix1").exists())
            self.assertGreaterEqual(len(created), 6)

            _, created2, skipped2 = cli._initialize_model_docs(
                root=Path(tmp),
                series="iqr",
                model="R08CPU",
            )
            self.assertEqual(created2, [])
            self.assertGreaterEqual(len(skipped2), 6)

    def test_load_device_access_matrix_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "device_access_matrix.csv"
            path.write_text(
                "\n".join(
                    [
                        "device_code,device,kind,unsupported,read,write,note,manual_write,manual_write_note",
                        "D,D1000,word,,OK,OK,representative verification address,OK,human confirmed",
                        "LTC,LTC10,bit,YES,NG,SKIP,known direct-path issue,,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows = cli._load_device_access_matrix_rows(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].device, "D1000")
        self.assertEqual(rows[0].manual_write, "OK")
        self.assertEqual(rows[1].unsupported, "YES")

    def test_render_device_access_matrix_markdown(self) -> None:
        rows = [
            cli.DeviceMatrixRow(
                "D",
                "D1000",
                "word",
                "",
                "OK",
                "OK",
                "representative verification address",
                "OK",
                "human confirmed",
            ),
            cli.DeviceMatrixRow("LTC", "LTC10", "bit", "YES", "NG", "SKIP", "known direct-path issue"),
        ]
        output = cli._render_device_access_matrix_markdown(
            rows,
            source_path=Path("internal_docs/iqr_r08cpu/device_access_matrix.csv"),
        )
        self.assertIn("# Device Access Matrix", output)
        self.assertIn("- word_read_OK: 1", output)
        self.assertIn("- bit_write_SKIP: 1", output)
        self.assertIn("- manual_write_OK: 1", output)
        self.assertIn(
            "| LTC | LTC10 | bit | YES | NG | SKIP |  | known direct-path issue |  |",
            output,
        )

    def test_select_manual_write_rows_filters_unsupported_and_non_writable(self) -> None:
        rows = [
            cli.DeviceMatrixRow("D", "D1000", "word", "", "OK", "OK", ""),
            cli.DeviceMatrixRow("S", "S100", "bit", "", "OK", "NG", ""),
            cli.DeviceMatrixRow("G", "G0", "extension_cpu_buffer", "", "NG", "SKIP", ""),
            cli.DeviceMatrixRow("M", "M1000", "bit", "YES", "OK", "OK", ""),
            cli.DeviceMatrixRow("ZR", "ZR1000", "word", "", "TODO", "TODO", ""),
        ]
        selected = cli._select_manual_write_rows(rows)
        self.assertEqual([row.device_code for row in selected], ["D", "ZR"])

    def test_select_manual_write_rows_allows_explicit_lt_lst_special_case(self) -> None:
        rows = [
            cli.DeviceMatrixRow("LTC", "LTC10", "bit", "", "NG", "SKIP", "known direct-path issue"),
            cli.DeviceMatrixRow("LSTS", "LSTS10", "bit", "", "NG", "SKIP", "known direct-path issue"),
        ]
        selected = cli._select_manual_write_rows(rows, device_codes={"LTC"})
        self.assertEqual([row.device_code for row in selected], ["LTC"])

    def test_parse_manual_verdict(self) -> None:
        self.assertEqual(cli._parse_manual_verdict("Y"), "OK")
        self.assertEqual(cli._parse_manual_verdict("n"), "NG")
        self.assertEqual(cli._parse_manual_verdict("skip"), "SKIP")
        self.assertIsNone(cli._parse_manual_verdict("maybe"))

    def test_load_processed_manual_write_items(self) -> None:
        with TemporaryDirectory() as tmp:
            report = Path(tmp) / "manual_write_verification_latest.md"
            report.write_text(
                "\n".join(
                    [
                        "# Manual Write Verification Report",
                        "",
                        "| Item | Status | Detail |",
                        "|---|---|---|",
                        "| D D1000 | OK | before=0x0000, test=0x0001, restored=0x0000 |",
                        "| M M1000 | SKIP | operator skipped before write |",
                        "| W W100 | NG | temporary_write_failed=boom |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                cli._load_processed_manual_write_items(report),
                {"D D1000", "M M1000", "W W100"},
            )
            self.assertEqual(
                cli._load_manual_write_report_rows(report),
                [
                    ("D D1000", "OK", "before=0x0000, test=0x0001, restored=0x0000"),
                    ("M M1000", "SKIP", "operator skipped before write"),
                    ("W W100", "NG", "temporary_write_failed=boom"),
                ],
            )

    def test_parse_positive_int_list(self) -> None:
        self.assertEqual(cli._parse_positive_int_list("1,2,4,8"), (1, 2, 4, 8))
        with self.assertRaises(ValueError):
            cli._parse_positive_int_list("1,0,2")

    def test_parse_label_array_probe_spec(self) -> None:
        parsed = cli._parse_label_array_probe_spec("GGG.ZZZ.ZZZ.DDD[0]:1:20")
        self.assertEqual(parsed.label, "GGG.ZZZ.ZZZ.DDD[0]")
        self.assertEqual(parsed.unit_specification, 1)
        self.assertEqual(parsed.array_data_length, 20)

        with self.assertRaises(ValueError):
            cli._parse_label_array_probe_spec("DDD[0]:2:20")

    def test_make_manual_label_test_bytes(self) -> None:
        self.assertEqual(cli._make_manual_label_test_bytes(b"\x00\x00"), b"\x01\x00")
        self.assertEqual(cli._make_manual_label_test_bytes(b"\x34\x12"), b"\x35\x12")
        with self.assertRaises(ValueError):
            cli._make_manual_label_test_bytes(b"")

    def test_summarize_durations(self) -> None:
        stats = cli._summarize_durations([0.001, 0.002, 0.003, 0.004], elapsed_s=0.02)
        self.assertEqual(stats.count, 4)
        self.assertAlmostEqual(stats.avg_ms, 2.5)
        self.assertAlmostEqual(stats.max_ms, 4.0)
        self.assertAlmostEqual(stats.rate_per_s, 200.0)


class TestCli(unittest.TestCase):
    def test_manual_label_verification_main_requires_label_args(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            cli.manual_label_verification_main(["--host", "192.0.2.10"])
        self.assertEqual(ctx.exception.code, 2)

    def test_manual_label_verification_main_processes_random_and_array_labels(self) -> None:
        class ManualLabelClient(SLMP4EClient):
            init_monitoring_timers: list[int] = []
            random_read_calls: list[list[str]] = []
            random_write_calls: list[list[LabelRandomWritePoint]] = []
            array_read_calls: list[list[LabelArrayReadPoint]] = []
            array_write_calls: list[list[LabelArrayWritePoint]] = []

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
                trace_hook=None,
            ) -> None:
                super().__init__(
                    host,
                    port,
                    transport=transport,
                    timeout=timeout,
                    plc_series=plc_series,
                    default_target=default_target,
                    monitoring_timer=monitoring_timer,
                    raise_on_error=raise_on_error,
                    trace_hook=trace_hook,
                )
                type(self).init_monitoring_timers.append(monitoring_timer)

            def open(self) -> None:
                return None

            def close(self) -> None:
                return None

            def label_read_random_points(self, labels, *, abbreviation_labels=()):  # type: ignore[override]
                type(self).random_read_calls.append(list(labels))
                return [
                    LabelRandomReadResult(
                        data_type_id=0x02,
                        spare=0,
                        read_data_length=2,
                        data=b"\x34\x12",
                    )
                    for _ in labels
                ]

            def label_write_random_points(self, points, *, abbreviation_labels=()):  # type: ignore[override]
                type(self).random_write_calls.append(list(points))

            def array_label_read_points(self, points, *, abbreviation_labels=()):  # type: ignore[override]
                type(self).array_read_calls.append(list(points))
                return [
                    LabelArrayReadResult(
                        data_type_id=0x02,
                        unit_specification=point.unit_specification,
                        array_data_length=point.array_data_length,
                        data=b"\x10\x00\x20\x00",
                    )
                    for point in points
                ]

            def array_label_write_points(self, points, *, abbreviation_labels=()):  # type: ignore[override]
                type(self).array_write_calls.append(list(points))

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "manual_label_verification_latest.md"
            with patch.object(cli, "SLMP4EClient", ManualLabelClient):
                with patch("builtins.input", side_effect=["", "Y", "", "Y"]):
                    rc = cli.manual_label_verification_main(
                        [
                            "--host",
                            "192.0.2.10",
                            "--series",
                            "iqr",
                            "--monitoring-timer",
                            "0x0020",
                            "--label-random",
                            "LabelW",
                            "--label-array",
                            "DDD[0]:1:4",
                            "--output",
                            str(output),
                        ]
                    )
            report = output.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(ManualLabelClient.init_monitoring_timers, [0x0020])
        self.assertEqual(ManualLabelClient.random_read_calls, [["LabelW"]])
        self.assertEqual(
            ManualLabelClient.random_write_calls,
            [
                [LabelRandomWritePoint(label="LabelW", data=b"\x35\x12")],
                [LabelRandomWritePoint(label="LabelW", data=b"\x34\x12")],
            ],
        )
        self.assertEqual(ManualLabelClient.array_read_calls[0][0], LabelArrayReadPoint("DDD[0]", 1, 4))
        self.assertEqual(
            ManualLabelClient.array_write_calls,
            [
                [
                    LabelArrayWritePoint(
                        label="DDD[0]",
                        unit_specification=1,
                        array_data_length=4,
                        data=b"\x11\x00\x20\x00",
                    )
                ],
                [
                    LabelArrayWritePoint(
                        label="DDD[0]",
                        unit_specification=1,
                        array_data_length=4,
                        data=b"\x10\x00\x20\x00",
                    )
                ],
            ],
        )
        self.assertIn("# Manual Label Verification Report", report)
        self.assertIn("- Monitoring timer: 0x0020", report)
        self.assertIn("| random LabelW | OK |", report)
        self.assertIn("| array DDD[0]:1:4 | OK |", report)

    def test_pending_live_verification_main_uses_monitoring_timer_and_skips_ondemand_and_reset(self) -> None:
        class PendingCliClient(SLMP4EClient):
            init_monitoring_timers: list[int] = []
            directory_read_calls: list[tuple[int, int, int, int]] = []
            array_read_calls: list[list[LabelArrayReadPoint]] = []
            array_write_calls: list[list[LabelArrayWritePoint]] = []
            random_read_calls: list[list[str]] = []
            random_write_calls: list[list[LabelRandomWritePoint]] = []

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
                trace_hook=None,
            ) -> None:
                super().__init__(
                    host,
                    port,
                    transport=transport,
                    timeout=timeout,
                    plc_series=plc_series,
                    default_target=default_target,
                    monitoring_timer=monitoring_timer,
                    raise_on_error=raise_on_error,
                    trace_hook=trace_hook,
                )
                type(self).init_monitoring_timers.append(monitoring_timer)

            def open(self) -> None:
                return None

            def close(self) -> None:
                self._sock = None

            def request(self, command, subcommand=0x0000, data=b"", **kwargs):  # type: ignore[override]
                return SLMPResponse(
                    serial=0,
                    target=SLMPTarget(),
                    end_code=0,
                    data=b"",
                    raw=b"",
                )

            def extend_unit_read_bytes(self, head_address: int, size: int, module_no: int) -> bytes:
                return b"\xB1\xE9"

            def extend_unit_write_bytes(self, head_address: int, module_no: int, data: bytes) -> None:
                return None

            def array_label_read_points(
                self,
                points,
                *,
                abbreviation_labels=(),
            ):
                type(self).array_read_calls.append(list(points))
                return [
                    LabelArrayReadResult(
                        data_type_id=0x02,
                        unit_specification=point.unit_specification,
                        array_data_length=point.array_data_length,
                        data=(
                            b"\x34\x12"
                            if point.array_data_length == 2
                            else (b"\x34\x12" * (point.array_data_length // 2))
                        ),
                    )
                    for point in points
                ]

            def array_label_write_points(
                self,
                points,
                *,
                abbreviation_labels=(),
            ) -> None:
                type(self).array_write_calls.append(list(points))

            def label_read_random_points(
                self,
                labels,
                *,
                abbreviation_labels=(),
            ):
                type(self).random_read_calls.append(list(labels))
                return [
                    LabelRandomReadResult(
                        data_type_id=0x02,
                        spare=0x00,
                        read_data_length=2,
                        data=b"\x34\x12",
                    )
                    for _ in labels
                ]

            def label_write_random_points(
                self,
                points,
                *,
                abbreviation_labels=(),
            ) -> None:
                type(self).random_write_calls.append(list(points))

            def file_read_directory_entries(
                self,
                *,
                drive_no: int,
                head_file_no: int,
                requested_files: int,
                subcommand: int = 0x0000,
            ) -> bytes:
                type(self).directory_read_calls.append((drive_no, head_file_no, requested_files, subcommand))
                raise SLMPError("directory unavailable")

            def file_search_by_name(self, *, filename: str, drive_no: int, subcommand: int = 0x0000) -> bytes:
                raise SLMPError("search unavailable")

            def file_new_file(
                self,
                *,
                filename: str,
                file_size: int,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("new file unavailable")

            def file_open_handle(
                self,
                *,
                filename: str,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
                write_open: bool = True,
            ) -> int:
                raise SLMPError("open file unavailable")

            def file_change_state_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                attribute: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("change state unavailable")

            def file_change_date_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                changed_at,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("change date unavailable")

            def file_delete_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("delete unavailable")

            def read_type_name(self) -> TypeNameInfo:
                return TypeNameInfo(raw=b"\x00" * 18, model="R08CPU", model_code=0x4801)

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "pending_live_verification_latest.md"
            with patch.object(cli, "SLMP4EClient", PendingCliClient):
                rc = cli.pending_live_verification_main(
                    [
                        "--host",
                        "192.0.2.10",
                        "--series",
                        "iqr",
                        "--monitoring-timer",
                        "0x0020",
                        "--output",
                        str(output),
                    ]
                )
            report = output.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(PendingCliClient.init_monitoring_timers, [0x0020])
        self.assertEqual(PendingCliClient.directory_read_calls, [(0, 1, 1, 0x0000)])
        self.assertEqual(PendingCliClient.array_read_calls[0][0].label, "LabelW")
        self.assertEqual(PendingCliClient.array_write_calls[0][0].data, b"\x34\x12")
        self.assertEqual(PendingCliClient.random_read_calls[0], ["LabelW"])
        self.assertEqual(PendingCliClient.random_write_calls[0][0].data, b"\x34\x12")
        self.assertIn(
            "| 2101 ondemand | SKIP | manual-defined as PLC-initiated data; "
            "use receive_ondemand() with a PLC-side trigger |",
            report,
        )
        self.assertIn(
            "| 1006 remote reset | SKIP | excluded from live verification scope |",
            report,
        )

    def test_pending_live_verification_main_uses_custom_label_specs(self) -> None:
        class PendingLabelClient(SLMP4EClient):
            array_read_calls: list[list[LabelArrayReadPoint]] = []
            random_read_calls: list[list[str]] = []

            def open(self) -> None:
                return None

            def close(self) -> None:
                self._sock = None

            def request(self, command, subcommand=0x0000, data=b"", **kwargs):  # type: ignore[override]
                return SLMPResponse(
                    serial=0,
                    target=SLMPTarget(),
                    end_code=0,
                    data=b"",
                    raw=b"",
                )

            def array_label_read_points(self, points, *, abbreviation_labels=()):
                type(self).array_read_calls.append(list(points))
                raise SLMPError("label missing")

            def label_read_random_points(self, labels, *, abbreviation_labels=()):
                type(self).random_read_calls.append(list(labels))
                raise SLMPError("label missing")

            def extend_unit_read_bytes(self, head_address: int, size: int, module_no: int) -> bytes:
                return b"\x00\x00"

            def extend_unit_write_bytes(self, head_address: int, module_no: int, data: bytes) -> None:
                return None

            def file_read_directory_entries(
                self,
                *,
                drive_no: int,
                head_file_no: int,
                requested_files: int,
                subcommand: int = 0x0000,
            ) -> bytes:
                raise SLMPError("directory unavailable")

            def file_search_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                subcommand: int = 0x0000,
            ) -> bytes:
                raise SLMPError("search unavailable")

            def file_new_file(
                self,
                *,
                filename: str,
                file_size: int,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("new file unavailable")

            def file_open_handle(
                self,
                *,
                filename: str,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
                write_open: bool = True,
            ) -> int:
                raise SLMPError("open file unavailable")

            def file_change_state_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                attribute: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("change state unavailable")

            def file_change_date_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                changed_at,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("change date unavailable")

            def file_delete_by_name(
                self,
                *,
                filename: str,
                drive_no: int,
                subcommand: int = 0x0000,
                password: str | None = None,
            ) -> None:
                raise SLMPError("delete unavailable")

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "pending_live_verification_latest.md"
            with patch.object(cli, "SLMP4EClient", PendingLabelClient):
                rc = cli.pending_live_verification_main(
                    [
                        "--host",
                        "192.0.2.10",
                        "--series",
                        "iqr",
                        "--label-array",
                        "GGG.ZZZ.ZZZ.DDD[0]:1:20",
                        "--label-random",
                        "GGG.ZZZ.ZZZ.DDD[0]",
                        "--output",
                        str(output),
                    ]
                )
            report = output.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(PendingLabelClient.array_read_calls[0][0].label, "GGG.ZZZ.ZZZ.DDD[0]")
        self.assertEqual(PendingLabelClient.array_read_calls[0][0].array_data_length, 20)
        self.assertEqual(PendingLabelClient.random_read_calls[0], ["GGG.ZZZ.ZZZ.DDD[0]"])
        self.assertIn(
            "| 141A label array write | SKIP | array read unavailable; no safe same-value payload |",
            report,
        )
        self.assertIn(
            "| 141B label random write | SKIP | random read unavailable; no safe same-value payload |",
            report,
        )


class TestDeviceApi(unittest.TestCase):
    def test_read_devices_word(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x34\x12\x78\x56"
        values = client.read_devices("D100", 2, bit_unit=False, series=PLCSeries.QL)
        self.assertEqual(values, [0x1234, 0x5678])

        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_READ)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x64\x00\x00\xA8\x02\x00")

    def test_practical_path_warning_for_lt_direct_access(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x00"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.read_devices("LTC0", 1, bit_unit=True, series=PLCSeries.IQR)
        self.assertTrue(any(item.category is SLMPPracticalPathWarning for item in caught))

    def test_temporarily_unsupported_device_error_for_g_direct_and_appendix1(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11"
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_devices("G0", 1, bit_unit=False, series=PLCSeries.IQR)

        ext = ExtensionSpec(
            extension_specification=0x03E0,
            extension_specification_modification=0x00,
            device_modification_index=0x00,
            device_modification_flags=0x00,
            direct_memory_specification=0xFA,
        )
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_devices_ext("G0", 1, extension=ext, bit_unit=False, series=PLCSeries.IQR)

    def test_temporarily_unsupported_device_error_for_s(self) -> None:
        client = FakeClient()
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_devices("S0", 1, bit_unit=True, series=PLCSeries.IQR)
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.write_devices("S0", [True], bit_unit=True, series=PLCSeries.IQR)
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_block(word_blocks=(), bit_blocks=[("S0", 1)], series=PLCSeries.IQR)

    def test_temporarily_unsupported_device_error_for_hg(self) -> None:
        client = FakeClient()
        ext = ExtensionSpec(
            extension_specification=0x03E0,
            extension_specification_modification=0x00,
            device_modification_index=0x00,
            device_modification_flags=0x00,
            direct_memory_specification=0xFA,
        )
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_devices("HG0", 1, bit_unit=False, series=PLCSeries.IQR)
        with self.assertRaises(SLMPUnsupportedDeviceError):
            client.read_devices_ext("HG0", 1, extension=ext, bit_unit=False, series=PLCSeries.IQR)

    def test_boundary_warning_for_multi_point_r_family_access(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x00\x00\x00\x00"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.read_devices("ZR163839", 2, bit_unit=False, series=PLCSeries.IQR)
        self.assertTrue(any(item.category is SLMPBoundaryBehaviorWarning for item in caught))

    def test_boundary_warning_for_odd_lz_write(self) -> None:
        client = FakeClient()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.write_devices("LZ1", [0], bit_unit=False, series=PLCSeries.IQR)
        self.assertTrue(any(item.category is SLMPBoundaryBehaviorWarning for item in caught))

    def test_write_random_bits(self) -> None:
        client = FakeClient()
        client.write_random_bits({"M10": True, "Y20": False}, series=PLCSeries.QL)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_WRITE_RANDOM)
        self.assertEqual(subcommand, 0x0001)
        self.assertEqual(payload[0], 2)

        client.write_random_bits({"M10": True, "Y20": False}, series=PLCSeries.IQR)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_WRITE_RANDOM)
        self.assertEqual(subcommand, 0x0003)
        self.assertEqual(payload[0], 2)
        # iQ-R/iQ-L random bit write state is 2 bytes per point (ON=01 00, OFF=00 00)
        self.assertIn(b"\x90\x00\x01\x00", payload)
        self.assertTrue(payload.endswith(b"\x9D\x00\x00\x00"))

    def test_manual_write_helpers_use_lt_lst_special_paths(self) -> None:
        class ManualProbeClient(FakeClient):
            def read_ltc_states(self, *, head_no=0, points=1, series=None):  # type: ignore[override]
                self.last_request = ("read_ltc_states", head_no, points, series)
                return [True]

            def read_lts_states(self, *, head_no=0, points=1, series=None):  # type: ignore[override]
                self.last_request = ("read_lts_states", head_no, points, series)
                return [False]

            def read_lstc_states(self, *, head_no=0, points=1, series=None):  # type: ignore[override]
                self.last_request = ("read_lstc_states", head_no, points, series)
                return [True]

            def read_lsts_states(self, *, head_no=0, points=1, series=None):  # type: ignore[override]
                self.last_request = ("read_lsts_states", head_no, points, series)
                return [False]

        client = ManualProbeClient()
        self.assertTrue(
            cli._read_manual_row_value(
                client,
                cli.DeviceMatrixRow("LTC", "LTC10", "bit", "", "NG", "SKIP", ""),
                series="iqr",
            )
        )
        self.assertEqual(client.last_request, ("read_ltc_states", 10, 1, "iqr"))
        self.assertFalse(
            cli._read_manual_row_value(
                client,
                cli.DeviceMatrixRow("LTS", "LTS10", "bit", "", "NG", "SKIP", ""),
                series="iqr",
            )
        )
        self.assertEqual(client.last_request, ("read_lts_states", 10, 1, "iqr"))
        self.assertTrue(
            cli._read_manual_row_value(
                client,
                cli.DeviceMatrixRow("LSTC", "LSTC10", "bit", "", "NG", "SKIP", ""),
                series="iqr",
            )
        )
        self.assertEqual(client.last_request, ("read_lstc_states", 10, 1, "iqr"))
        self.assertFalse(
            cli._read_manual_row_value(
                client,
                cli.DeviceMatrixRow("LSTS", "LSTS10", "bit", "", "NG", "SKIP", ""),
                series="iqr",
            )
        )
        self.assertEqual(client.last_request, ("read_lsts_states", 10, 1, "iqr"))

        cli._write_manual_row_value(
            client,
            cli.DeviceMatrixRow("LTC", "LTC10", "bit", "", "NG", "SKIP", ""),
            True,
            series="iqr",
        )
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_WRITE_RANDOM)
        self.assertEqual(subcommand, 0x0003)
        self.assertEqual(payload[0], 1)
        self.assertEqual(payload[1:4], b"\x0A\x00\x00")
        self.assertEqual(payload[-2:], b"\x01\x00")

    def test_memory_read_words(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11\x22\x22"
        out = client.memory_read_words(0x1234, 2)
        self.assertEqual(out, [0x1111, 0x2222])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.MEMORY_READ)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x34\x12\x00\x00\x02\x00")

    def test_extend_unit_write_bytes(self) -> None:
        client = FakeClient()
        client.extend_unit_write_bytes(0x10, 0x0003, b"\x01\x02\x03\x04")
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x10\x00\x00\x00\x04\x00\x03\x00\x01\x02\x03\x04")

    def test_extend_unit_word_helpers(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11\x22\x22"
        out = client.extend_unit_read_words(0x20, 2, 0x03E0)
        self.assertEqual(out, [0x1111, 0x2222])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x20\x00\x00\x00\x04\x00\xE0\x03")

        client.extend_unit_write_words(0x20, 0x03E0, [0x3333, 0x4444])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x20\x00\x00\x00\x04\x00\xE0\x03\x33\x33\x44\x44")


        client.next_response_data = b"\x55\x55"
        self.assertEqual(client.extend_unit_read_word(0x30, 0x03E0), 0x5555)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(payload, b"\x30\x00\x00\x00\x02\x00\xE0\x03")

        client.next_response_data = b"\x78\x56\x34\x12"
        self.assertEqual(client.extend_unit_read_dword(0x34, 0x03E0), 0x12345678)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(payload, b"\x34\x00\x00\x00\x04\x00\xE0\x03")

        client.extend_unit_write_word(0x30, 0x03E0, 0x5555)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(payload, b"\x30\x00\x00\x00\x02\x00\xE0\x03\x55\x55")

        client.extend_unit_write_dword(0x34, 0x03E0, 0x12345678)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(payload, b"\x34\x00\x00\x00\x04\x00\xE0\x03\x78\x56\x34\x12")

    def test_cpu_buffer_word_helpers_default_to_03e0(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x01\x48"
        out = client.cpu_buffer_read_words(0x04, 1)
        self.assertEqual(out, [0x4801])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x04\x00\x00\x00\x02\x00\xE0\x03")

        client.cpu_buffer_write_words(0x04, [0x4801])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x04\x00\x00\x00\x02\x00\xE0\x03\x01\x48")

        client.next_response_data = b"\x01\x48"
        self.assertEqual(client.cpu_buffer_read_word(0x04), 0x4801)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(payload, b"\x04\x00\x00\x00\x02\x00\xE0\x03")

        client.next_response_data = b"\xB1\xE9\xAF\x95"
        self.assertEqual(client.cpu_buffer_read_dword(0x00), 0x95AFE9B1)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_READ)
        self.assertEqual(payload, b"\x00\x00\x00\x00\x04\x00\xE0\x03")

        client.cpu_buffer_write_word(0x04, 0x4801)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(payload, b"\x04\x00\x00\x00\x02\x00\xE0\x03\x01\x48")

        client.cpu_buffer_write_dword(0x00, 0x95AFE9B1)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.EXTEND_UNIT_WRITE)
        self.assertEqual(payload, b"\x00\x00\x00\x00\x04\x00\xE0\x03\xB1\xE9\xAF\x95")

    def test_remote_run_control(self) -> None:
        client = FakeClient()
        client.remote_run_control(force=False, clear_mode=2)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.REMOTE_RUN)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x01\x00\x02\x00")

    def test_self_test_loopback(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x05\x00ABCDE"
        out = client.self_test_loopback("ABCDE")
        self.assertEqual(out, b"ABCDE")
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.SELF_TEST)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x05\x00ABCDE")

    def test_remote_reset_uses_no_response_mode_by_default(self) -> None:
        client = FakeClient()
        client.remote_reset_control()
        self.assertEqual(client.last_no_response, (Command.REMOTE_RESET, 0x0000, b"", {}))

        client.remote_reset()
        self.assertEqual(client.last_no_response, (Command.REMOTE_RESET, 0x0000, b"", {}))

    def test_file_open_handle(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x0A\x00"
        handle = client.file_open_handle(
            filename="ABC.QPG",
            drive_no=0x0000,
            subcommand=0x0000,
            password="1234",
            write_open=True,
        )
        self.assertEqual(handle, 10)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.FILE_OPEN)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"1234\x01\x00\x00\x00\x07\x00ABC.QPG")

    def test_file_open_and_write_raw_wrappers_return_response_data(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x0A\x00"
        opened = client.file_open(b"1234\x01\x00\x00\x00\x07\x00ABC.QPG", subcommand=0x0000)
        self.assertEqual(opened, b"\x0A\x00")

        client.next_response_data = b"\x04\x00"
        written = client.file_write(b"\x01\x00\x00\x00\x02\x00\x12\x34", subcommand=0x0000)
        self.assertEqual(written, b"\x04\x00")

    def test_file_change_state_uses_two_byte_attribute(self) -> None:
        client = FakeClient()
        client.file_change_state_by_name(
            filename="ABC.QPG",
            drive_no=0,
            attribute=1,
            subcommand=0x0000,
            password="1234",
        )
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.FILE_CHANGE_STATE)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"1234\x00\x00\x01\x00\x07\x00ABC.QPG")

    def test_file_close_handle_allows_close_type_zero(self) -> None:
        client = FakeClient()
        client.file_close_handle(0x0010, close_type=0, subcommand=0x0000)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.FILE_CLOSE)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload, b"\x10\x00\x00\x00")

    def test_file_subcommand_matrix_is_enforced(self) -> None:
        client = FakeClient()
        with self.assertRaises(ValueError):
            client.file_read_directory(b"", subcommand=0x0004)
        with self.assertRaises(ValueError):
            client.file_read(b"", subcommand=0x0040)
        with self.assertRaises(ValueError):
            client.file_close(b"", subcommand=0x0040)
        with self.assertRaises(ValueError):
            client.file_delete_by_name(filename="ABC.QPG", drive_no=0, subcommand=0x0040, password="12345")

    def test_ondemand_receives_incoming_command(self) -> None:
        client = FakeReceiveClient()
        client.next_request = SLMPRequest(
            serial=1,
            target=SLMPTarget(),
            monitoring_timer=0x0010,
            command=int(Command.ONDEMAND),
            subcommand=0x0000,
            data=b"ABC",
            raw=b"",
        )
        self.assertEqual(client.ondemand(), b"ABC")

        client.next_request = SLMPRequest(
            serial=1,
            target=SLMPTarget(),
            monitoring_timer=0x0010,
            command=int(Command.FILE_READ),
            subcommand=0x0000,
            data=b"",
            raw=b"",
        )
        with self.assertRaises(SLMPError):
            client.ondemand()

    def test_read_devices_ext(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11"
        ext = ExtensionSpec(
            extension_specification=0x0001,
            extension_specification_modification=0x00,
            device_modification_index=0x00,
            device_modification_flags=0x00,
            direct_memory_specification=0xF9,
        )
        out = client.read_devices_ext("W100", 1, extension=ext, bit_unit=False, series=PLCSeries.QL)
        self.assertEqual(out, [0x1111])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_READ)
        self.assertEqual(subcommand, 0x0080)
        self.assertEqual(payload, b"\x01\x00\x00\x00\x00\x00\x01\x00\xB4\xF9\x01\x00")

    def test_write_block_mixed_split(self) -> None:
        client = FakeClient()
        client.write_block(
            word_blocks=[("D100", [0x1111])],
            bit_blocks=[("M200", [0x0001])],
            series=PLCSeries.QL,
            split_mixed_blocks=True,
        )
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(client.requests[0][0], Command.DEVICE_WRITE_BLOCK)
        self.assertEqual(client.requests[1][0], Command.DEVICE_WRITE_BLOCK)

    def test_write_block_default_keeps_mixed_request(self) -> None:
        client = FakeClient()
        client.write_block(
            word_blocks=[("D100", [0x1111])],
            bit_blocks=[("M200", [0x0001])],
            series=PLCSeries.QL,
        )
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(client.requests[0][0], Command.DEVICE_WRITE_BLOCK)

    def test_read_long_timer_decode(self) -> None:
        client = FakeClient()
        # 2 timer points * 4 words:
        # point0: current=0x00011234, status=0x0003 (contact+coil ON)
        # point1: current=0x0002ABCD, status=0x0002 (contact ON, coil OFF)
        client.next_response_data = (
            b"\x34\x12\x01\x00\x03\x00\x00\x00"
            + b"\xCD\xAB\x02\x00\x02\x00\x00\x00"
        )
        out = client.read_long_timer(head_no=10, points=2, series=PLCSeries.IQR)
        self.assertEqual(len(out), 2)
        self.assertIsInstance(out[0], LongTimerResult)
        self.assertEqual(out[0].device, "LTN10")
        self.assertEqual(out[0].current_value, 0x00011234)
        self.assertTrue(out[0].contact)
        self.assertTrue(out[0].coil)
        self.assertEqual(out[1].device, "LTN11")
        self.assertEqual(out[1].current_value, 0x0002ABCD)
        self.assertTrue(out[1].contact)
        self.assertFalse(out[1].coil)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_READ)
        self.assertEqual(subcommand, 0x0002)
        self.assertEqual(payload[-2:], b"\x08\x00")

    def test_read_long_retentive_timer_decode(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11\x22\x22\x01\x00\x00\x00"
        out = client.read_long_retentive_timer(head_no=0, points=1, series=PLCSeries.IQR)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].device, "LSTN0")
        self.assertEqual(out[0].current_value, 0x22221111)
        self.assertFalse(out[0].contact)
        self.assertTrue(out[0].coil)
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_READ)
        self.assertEqual(subcommand, 0x0002)
        self.assertEqual(payload[-2:], b"\x04\x00")

    def test_long_timer_state_aliases(self) -> None:
        client = FakeClient()
        client.next_response_data = (
            b"\x34\x12\x01\x00\x03\x00\x00\x00"
            + b"\xCD\xAB\x02\x00\x02\x00\x00\x00"
        )
        self.assertEqual(client.read_ltc_states(head_no=10, points=2, series=PLCSeries.IQR), [True, False])
        client.next_response_data = (
            b"\x34\x12\x01\x00\x03\x00\x00\x00"
            + b"\xCD\xAB\x02\x00\x02\x00\x00\x00"
        )
        self.assertEqual(client.read_lts_states(head_no=10, points=2, series=PLCSeries.IQR), [True, True])

        client.next_response_data = (
            b"\x11\x11\x22\x22\x01\x00\x00\x00"
            + b"\x11\x11\x22\x22\x02\x00\x00\x00"
        )
        self.assertEqual(client.read_lstc_states(head_no=0, points=2, series=PLCSeries.IQR), [True, False])
        client.next_response_data = (
            b"\x11\x11\x22\x22\x01\x00\x00\x00"
            + b"\x11\x11\x22\x22\x02\x00\x00\x00"
        )
        self.assertEqual(client.read_lsts_states(head_no=0, points=2, series=PLCSeries.IQR), [False, True])

    def test_read_long_timer_validation(self) -> None:
        client = FakeClient()
        with self.assertRaises(ValueError):
            client.read_long_timer(head_no=-1, points=1)
        with self.assertRaises(ValueError):
            client.read_long_timer(head_no=0, points=0)

    def test_label_payload_builders(self) -> None:
        p041a = SLMP4EClient.build_array_label_read_payload(
            [LabelArrayReadPoint(label="LabelW", unit_specification=1, array_data_length=2)],
            abbreviation_labels=["Typ1"],
        )
        self.assertEqual(
            p041a,
            b"\x01\x00\x01\x00"
            + b"\x04\x00T\x00y\x00p\x001\x00"
            + b"\x06\x00L\x00a\x00b\x00e\x00l\x00W\x00"
            + b"\x01\x00\x02\x00",
        )

        p141a = SLMP4EClient.build_array_label_write_payload(
            [LabelArrayWritePoint(label="LabelW", unit_specification=1, array_data_length=2, data=b"\x31\x00")]
        )
        self.assertEqual(
            p141a,
            b"\x01\x00\x00\x00"
            + b"\x06\x00L\x00a\x00b\x00e\x00l\x00W\x00"
            + b"\x01\x00\x02\x00\x31\x00",
        )

        p041c = SLMP4EClient.build_label_read_random_payload(["LabelB", "LabelW"])
        self.assertEqual(
            p041c,
            b"\x02\x00\x00\x00"
            + b"\x06\x00L\x00a\x00b\x00e\x00l\x00B\x00"
            + b"\x06\x00L\x00a\x00b\x00e\x00l\x00W\x00",
        )

        p141b = SLMP4EClient.build_label_write_random_payload(
            [LabelRandomWritePoint(label="LabelW", data=b"\x31\x00")]
        )
        self.assertEqual(
            p141b,
            b"\x01\x00\x00\x00"
            + b"\x06\x00L\x00a\x00b\x00e\x00l\x00W\x00"
            + b"\x02\x00\x31\x00",
        )

    def test_label_response_parsers(self) -> None:
        array_resp = (
            b"\x02\x00"
            + b"\x02\x01\x02\x00\x44\x00"
            + b"\x01\x00\x01\x00\x01\x00"
        )
        parsed_array = SLMP4EClient.parse_array_label_read_response(array_resp, expected_points=2)
        self.assertEqual(len(parsed_array), 2)
        self.assertIsInstance(parsed_array[0], LabelArrayReadResult)
        self.assertEqual(parsed_array[0].data_type_id, 0x02)
        self.assertEqual(parsed_array[0].unit_specification, 0x01)
        self.assertEqual(parsed_array[0].data, b"\x44\x00")
        self.assertEqual(parsed_array[1].unit_specification, 0x00)
        self.assertEqual(parsed_array[1].data, b"\x01\x00")

        random_resp = (
            b"\x02\x00"
            + b"\x01\x00\x02\x00\x01\x00"
            + b"\x02\x00\x02\x00\x31\x00"
        )
        parsed_random = SLMP4EClient.parse_label_read_random_response(random_resp, expected_points=2)
        self.assertEqual(len(parsed_random), 2)
        self.assertIsInstance(parsed_random[0], LabelRandomReadResult)
        self.assertEqual(parsed_random[0].data_type_id, 0x01)
        self.assertEqual(parsed_random[0].read_data_length, 2)
        self.assertEqual(parsed_random[0].data, b"\x01\x00")
        self.assertEqual(parsed_random[1].data_type_id, 0x02)
        self.assertEqual(parsed_random[1].data, b"\x31\x00")

    def test_label_typed_methods_issue_requests(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x01\x00\x02\x01\x02\x00\x44\x00"
        out = client.array_label_read_points(
            [LabelArrayReadPoint(label="LabelW", unit_specification=1, array_data_length=2)]
        )
        self.assertEqual(out[0].data, b"\x44\x00")
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.LABEL_ARRAY_READ)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload[:4], b"\x01\x00\x00\x00")

        client.array_label_write_points(
            [LabelArrayWritePoint(label="LabelW", unit_specification=1, array_data_length=2, data=b"\x31\x00")]
        )
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.LABEL_ARRAY_WRITE)
        self.assertEqual(subcommand, 0x0000)
        self.assertTrue(payload.endswith(b"\x31\x00"))

        client.next_response_data = b"\x01\x00\x02\x00\x02\x00\x44\x00"
        out2 = client.label_read_random_points(["LabelW"])
        self.assertEqual(out2[0].data, b"\x44\x00")
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.LABEL_READ_RANDOM)
        self.assertEqual(subcommand, 0x0000)
        self.assertEqual(payload[:4], b"\x01\x00\x00\x00")

        client.label_write_random_points([LabelRandomWritePoint(label="LabelW", data=b"\x31\x00")])
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.LABEL_WRITE_RANDOM)
        self.assertEqual(subcommand, 0x0000)
        self.assertTrue(payload.endswith(b"\x02\x00\x31\x00"))

    def test_read_random_returns_typed_result(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x34\x12\x78\x56\xBC\x9A\x00\x00"
        out = client.read_random(word_devices=["D100", "D101"], dword_devices=["D200"], series=PLCSeries.IQR)
        self.assertIsInstance(out, RandomReadResult)
        self.assertEqual(out.word["D100"], 0x1234)
        self.assertEqual(out.word["D101"], 0x5678)
        self.assertEqual(out.dword["D200"], 0x00009ABC)

    def test_execute_monitor_returns_typed_result(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x11\x11\x22\x22\x33\x33\x44\x44"
        out = client.execute_monitor(word_points=2, dword_points=1)
        self.assertIsInstance(out, MonitorResult)
        self.assertEqual(out.word, [0x1111, 0x2222])
        self.assertEqual(out.dword, [0x44443333])

    def test_read_block_returns_typed_result(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x34\x12\x10\x00"
        out = client.read_block(
            word_blocks=[("D100", 1)],
            bit_blocks=[("M200", 1)],
            series=PLCSeries.IQR,
            split_mixed_blocks=False,
        )
        self.assertIsInstance(out, BlockReadResult)
        self.assertEqual(out.word_blocks[0].device, "D100")
        self.assertEqual(out.word_blocks[0].values, [0x1234])
        self.assertEqual(out.bit_blocks[0].device, "M200")
        self.assertEqual(out.bit_blocks[0].values, [0x0010])

    def test_read_block_multi_point_bit_values_are_packed_words(self) -> None:
        client = FakeClient()
        client.next_response_data = b"\x05\x00\x01\x00\x01\x00\x01\x00"
        out = client.read_block(
            word_blocks=(),
            bit_blocks=[("M1000", 4)],
            series=PLCSeries.IQR,
        )
        self.assertEqual(out.bit_blocks[0].device, "M1000")
        self.assertEqual(out.bit_blocks[0].values, [0x0005, 0x0001, 0x0001, 0x0001])

    def test_write_block_multi_point_bit_values_are_packed_words(self) -> None:
        client = FakeClient()
        client.write_block(
            word_blocks=(),
            bit_blocks=[("M1000", [0x0005, 0x0001])],
            series=PLCSeries.IQR,
        )
        command, subcommand, payload, _ = client.last_request
        self.assertEqual(command, Command.DEVICE_WRITE_BLOCK)
        self.assertEqual(subcommand, 0x0002)
        self.assertEqual(
            payload,
            b"\x00\x01"
            + encode_device_spec("M1000", series=PLCSeries.IQR)
            + b"\x02\x00"
            + b"\x05\x00\x01\x00",
        )

    def test_read_type_name_returns_typed_result(self) -> None:
        client = FakeClient()
        client.next_response_data = b"R08CPU".ljust(16, b" ") + b"\x01\x48"
        out = client.read_type_name()
        self.assertIsInstance(out, TypeNameInfo)
        self.assertEqual(out.model, "R08CPU")
        self.assertEqual(out.model_code, 0x4801)


if __name__ == "__main__":
    unittest.main()

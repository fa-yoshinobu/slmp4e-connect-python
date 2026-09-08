"""Exercise the maintained examples' cleanup control flow without PLC I/O."""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ERROR_NAME = "SlmpOutcomeUnknownError"


class UnknownOutcome(Exception):
    pass


def write_call(node: ast.stmt) -> bool:
    if not isinstance(node, ast.Expr):
        return False
    value = node.value.value if isinstance(node.value, ast.Await) else node.value
    if not isinstance(value, ast.Call):
        return False
    name = value.func.attr if isinstance(value.func, ast.Attribute) else getattr(value.func, "id", "")
    return name.startswith("write")


def cases() -> list[tuple[str, ast.Try]]:
    result = []
    paths = [*sorted((ROOT / "samples").glob("*.py")), *sorted((ROOT / "docsrc/user").glob("*.md"))]
    for path in paths:
        if path.name == "API_REFERENCE.md":
            continue
        source = path.read_text(encoding="utf-8-sig")
        blocks = [source] if path.suffix == ".py" else re.findall(r"^```python\n(.*?)^```", source, re.M | re.S)
        for index, block in enumerate(blocks):
            for node in ast.walk(ast.parse(block)):
                if isinstance(node, ast.Try) and any(
                    isinstance(h.type, ast.Name) and h.type.id == ERROR_NAME for h in node.handlers
                ):
                    if any(write_call(n) for s in node.finalbody for n in ast.walk(s)):
                        result.append((f"{path.name}:{index}:{node.lineno}", node))
    return result


CASES = cases()


@pytest.mark.parametrize("label,original", CASES, ids=[label for label, _ in CASES])
def test_confirmed_cleanup_and_unknown_outcome(label: str, original: ast.Try) -> None:
    # Substitute only external work; keep the source's confirmation assignments,
    # exception handler and finally conditions/order. Inject one post-write readback.
    node = copy.deepcopy(original)
    flags = []
    body = []
    for index, stmt in enumerate(node.body):
        if write_call(stmt):
            assignment = node.body[index + 1]
            assert isinstance(assignment, ast.Assign), label
            assert isinstance(assignment.targets[0], ast.Name), label
            flag = assignment.targets[0].id
            flags.append(flag)
            body.extend(ast.parse(f"probe('write', {flag!r})").body)
            body.append(assignment)
    assert flags, label
    body.extend(ast.parse("probe('readback', '')").body)
    node.body = body

    def cleanup(statements: list[ast.stmt], flag: str = "") -> list[ast.stmt]:
        output = []
        for stmt in statements:
            if isinstance(stmt, ast.If):
                current = stmt.test.id if isinstance(stmt.test, ast.Name) else flag
                stmt.body = cleanup(stmt.body, current)
                stmt.orelse = cleanup(stmt.orelse, current)
                if stmt.body:
                    output.append(stmt)
            elif write_call(stmt):
                assert flag in flags, label
                output.extend(ast.parse(f"probe('restore', {flag!r})").body)
        return output

    node.finalbody = cleanup(node.finalbody)
    code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), label, "exec")
    order = list(dict.fromkeys(flags))
    scenarios = [(None, 0, RuntimeError("unused")), ("readback", 1, RuntimeError("readback"))]
    for phase, count in (("write", len(flags)), ("restore", len(order))):
        for index in range(1, count + 1):
            scenarios.extend((phase, index, error) for error in (UnknownOutcome("unknown"), ValueError("rejected")))

    def run_scenario(phase: str | None, failure_at: int, error: Exception) -> None:
        events = []
        completed = []
        counts: dict[str, int] = {}

        def probe(kind: str, flag: str) -> None:
            counts[kind] = counts.get(kind, 0) + 1
            events.append((kind, flag))
            if kind == phase and counts[kind] == failure_at:
                raise error
            if kind == "write" and flag not in completed:
                completed.append(flag)

        namespace = {name: False for name in order}
        namespace.update(outcome_unknown=False, probe=probe, **{ERROR_NAME: UnknownOutcome})
        if phase is None:
            exec(code, namespace)
        else:
            with pytest.raises(type(error)) as caught:
                exec(code, namespace)
            assert caught.value is error, (label, phase, failure_at)
        actual = [flag for kind, flag in events if kind == "restore"]
        expected = list(reversed(completed))
        if phase == "write" and isinstance(error, UnknownOutcome):
            expected = []
        if phase == "restore":
            expected = expected[:failure_at]
        assert actual == expected, (label, phase, failure_at)

    for phase, failure_at, error in scenarios:
        run_scenario(phase, failure_at, error)


def test_cleanup_examples_are_present() -> None:
    assert CASES


def test_named_sample_updates_and_restores_use_supported_routes() -> None:
    from slmp.utils import _compile_named_write

    values = {"D100:U": 1, "D200:F": 2.0, "D202:L": 3, "D50.3": False}
    for filename in ("high_level_async.py", "high_level_sync.py"):
        source = (ROOT / "samples" / filename).read_text(encoding="utf-8-sig")
        checked = 0
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in ("write_named", "write_named_sync"):
                continue
            updates = eval(compile(ast.Expression(body=node.args[1]), filename, "eval"), {"named_values": values})
            words, dwords, bits = _compile_named_write(updates, "melsec:iq-r")
            assert len(words) == 1 and len(dwords) == 2 and not bits
            checked += 1
        assert checked == 2

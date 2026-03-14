# Release Guide

This is the minimum release checklist for this repository.

## 1. Update the Human-Facing Files

Check these before tagging:

- `README.md`
- `USER_GUIDE.md`
- `TESTING.md`
- `STATUS.md`
- `CHANGELOG.md`
- `SLMP_SPECIFICATION.md`
- `internal_docs/open_items.md`
- `internal_docs/communication_test_record.md`

## 2. Run Local Verification

Clean old packaging artifacts first so you do not accidentally publish stale files:

```powershell
Remove-Item -Recurse -Force build, dist, *.egg-info
```

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy slmp4e scripts
python -m build
```

Expected result:

- tests pass
- `ruff` passes
- `mypy` passes
- `dist/` contains a source distribution and wheel

Optional packaging smoke check:

```powershell
python -m venv %TEMP%\\slmp4e_release_smoke
%TEMP%\\slmp4e_release_smoke\\Scripts\\python.exe -m pip install .\\dist\\slmp4e_connect_python-0.1.1-py3-none-any.whl
%TEMP%\\slmp4e_release_smoke\\Scripts\\python.exe -c "import slmp4e; print(slmp4e.__version__)"
%TEMP%\\slmp4e_release_smoke\\Scripts\\slmp4e-connection-check.exe --help
```

## 3. Run the Minimum Live Check

```powershell
python scripts/slmp_connection_check.py --host <host> --port <port> --transport tcp --series <series>
```

If the release changes live behavior, also run the focused script for that area.

Typical examples:

- `scripts/slmp_open_items_recheck.py`
- `scripts/slmp_pending_live_verification.py`
- `scripts/slmp_device_range_probe.py`
- `scripts/slmp_register_boundary_probe.py`
- `scripts/slmp_special_device_probe.py`

## 4. Review Report Updates

If you ran live verification:

- confirm the expected `internal_docs/<series>_<model>/*_latest.md` files changed
- reflect conclusion changes in:
  - `internal_docs/open_items.md`
  - `internal_docs/communication_test_record.md`
  - `internal_docs/manual_implementation_differences.md`

## 5. Artifact Policy

- do not commit build artifacts from `dist/`
- do not commit packet captures or raw communication logs

## 6. Tagging Flow

1. update `version` in `pyproject.toml`
2. update `CHANGELOG.md`
3. finish local and live verification
4. create a normal release commit
5. create the tag

## 7. Publish

If you are publishing artifacts:

```powershell
python -m twine check dist/*
```

Then:

- push the release commit and tag to `https://github.com/fa-yoshinobu/slmp4e-connect-python`
- create the GitHub release entry using `.github/RELEASE_TEMPLATE.md`
- for `v0.1.0`, you can start from `.github/RELEASE_v0.1.0.md`
- upload `dist/` artifacts if you are distributing release packages outside the repository

## 8. Current Baseline

- package version: `0.1.1`
- validated target: Mitsubishi MELSEC iQ-R `R08CPU`

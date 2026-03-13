# SLMP4E Connect Python vX.Y.Z

## Summary

Short summary of this release.

Example:

- package rename aligned to `slmp4e-connect-python`
- documentation refreshed for GitHub-based installation
- release metadata and CI updated

## Highlights

- highlight 1
- highlight 2
- highlight 3

## Packaging

- Repository: `https://github.com/fa-yoshinobu/slmp4e-connect-python`
- Install from GitHub:

```powershell
python -m pip install "git+https://github.com/fa-yoshinobu/slmp4e-connect-python.git@vX.Y.Z"
```

- Source archive: `slmp4e_connect_python-X.Y.Z.tar.gz`
- Wheel: `slmp4e_connect_python-X.Y.Z-py3-none-any.whl`
- License: `MIT`

## Verification

- `python -m unittest discover -s tests -v`
- `python -m ruff check .`
- `python -m mypy slmp4e scripts`
- `python -m build`
- `python -m twine check dist/*`

## Live Validation

- target series/model:
- transport:
- host/port:
- scripts run:
- report updates:

## Breaking Changes

- none

## Upgrade Notes

- existing Python import path remains `slmp4e`
- existing CLI names remain `slmp4e-*`

## Known Limits

- only `4E` frame is supported
- only binary data code is supported
- `3E` frame is out of scope
- ASCII mode is out of scope

## Full Changelog

See `CHANGELOG.md` for the full project history.

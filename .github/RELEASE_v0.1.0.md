# SLMP4E Connect Python v0.1.0

## Summary

Initial packaged release for the current repository scope.

This release publishes the first packaged version of `SLMP4E Connect Python`, a Python library and CLI toolkit for Mitsubishi SLMP communication focused on the `4E` frame and binary data code.

## Highlights

- 4E binary SLMP frame encoder/decoder
- TCP and UDP client support
- typed APIs for normal device, random, block, monitor, memory, extend-unit, label, remote-control, password, self-test, and major file-command operations
- Appendix 1 typed extension builders and helper APIs
- practical helper APIs for long timer / long retentive timer decoding and CPU buffer access through the verified `0601/1601` path
- CLI entry points for connection checks and focused live-verification workflows

## Packaging

- Repository: `https://github.com/fa-yoshinobu/slmp4e-connect-python`
- Install from GitHub:

```powershell
python -m pip install "git+https://github.com/fa-yoshinobu/slmp4e-connect-python.git@v0.1.0"
```

- Source archive: `slmp4e_connect_python-0.1.0.tar.gz`
- Wheel: `slmp4e_connect_python-0.1.0-py3-none-any.whl`
- License: `MIT`

## Verification

The following checks were completed for this release:

- `python -m unittest discover -s tests -v`
- `python -m ruff check .`
- `python -m mypy slmp4e scripts`
- `python -m build`
- `python -m twine check dist/*`

## Validated Environment

- Mitsubishi MELSEC iQ-R `R08CPU`
- host `192.168.250.101`
- `TCP 1025`
- `UDP 1027`
- `series=iqr`

## Breaking Changes

- none

## Upgrade Notes

- package/repository naming is aligned to `slmp4e-connect-python`
- Python import path remains `slmp4e`
- existing CLI names remain `slmp4e-*`

## Known Limits

- only `4E` frame is supported
- only binary data code is supported
- `3E` frame is not implemented
- ASCII mode is not implemented
- some paths remain target-specific on the currently validated iQ-R target
- unresolved target-specific items are tracked in `internal_docs/open_items.md`

## Full Changelog

See `CHANGELOG.md` for the full project history.

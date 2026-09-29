# Changelog

## 1.2.0

- Added `requirements.txt` and `requirements-plot.txt` for installs without
  `pip install -e .` (kept in sync with `pyproject.toml`'s dependency set).
- Added a "Windows vs. Ubuntu" section to the README: FTDI driver, `dialout`
  group permissions, `ModemManager` gotcha, and the port-name difference
  (`COMx` vs `/dev/ttyUSBx`) that the config's port-mismatch prompt already
  handles correctly.

- Added `vdi_pm5/config.py`: YAML configuration (`instrument`, `measurement`,
  `display`, `output`, `metadata` sections), with:
  - Schema validation (unknown keys/sections and wrong types are rejected).
  - Comment-preserving save via `ruamel.yaml` (round-trip mode), since the
    shell rewrites the `instrument.port` field automatically.
  - `resolve_port()`: on first successful autodetection, the port is saved to
    the config; on later mismatches, `instrument.on_port_change` decides
    whether to `ask` (interactive confirmation), `use_detected`, or `fail`.
- `PM5Shell` (`cli.py`) now accepts `--config PATH` and resolves the port
  against it at startup, prompting on mismatch. An explicit `--port` on the
  command line always bypasses the config entirely.
- New shell commands: `config show`, `config init [path]`.
- Added `pm5_config.example.yaml` at the repo root.
- Fixed missing `h5py`/`numpy`/`ruamel.yaml` runtime dependencies in
  `pyproject.toml` (present since 1.1.0's HDF5 logging, but not declared).
  Added `matplotlib` as an optional `[plot]` extra for the upcoming live-plot
  feature.
- Fixed a missing code-fence in the README's "Continuous reading" section.

## 1.1.0

- Continuous reading with HDF5 storage (`vdi_pm5/storage.py`,
  `Hdf5PowerLogger`) and the `log` shell command.

## 1.0.0

- Initial one-off driver script for the PM5 (sensor S/N 347V).

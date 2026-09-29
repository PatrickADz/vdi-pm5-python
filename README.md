# vdi_pm5

Python library to control the **VDI Erickson PM5** power meter (mm/submm,
75 GHz – >3 THz) over USB (FTDI chip exposed as a virtual COM port).

## Installation

```bash
git clone https://github.com/PatrickADz/vdi-pm5-python.git
cd vdi-pm5-python
```

Or, without installing the package (just the runtime dependencies):

```bash
pip install -r requirements.txt
```

`pip install -e .` additionally registers the `vdi-pm5` command and pulls in
version bounds from `pyproject.toml`; `requirements.txt` is the same
dependency set for people who just want to run the code straight from a
clone (e.g. `python -m vdi_pm5.cli`). For the (currently unwired) live-plot
feature, use `requirements-plot.txt` or `pip install -e ".[plot]"` instead.

## Windows vs. Ubuntu

The codebase itself is platform-agnostic no code changes are needed
between the two. `find_port()` matches the PM5 by its FTDI serial number and
manufacturer string rather than by port name, and all file paths go through
`pathlib.Path`. What differs is the environment:

| | Windows | Ubuntu / Linux |
|---|---|---|
| Port name | `COM5`, `COM7`, … | `/dev/ttyUSB0`, `/dev/ttyACM0`, … |
| FTDI driver | Usually auto-installs, or from vadiodes/FTDI's site | Built into the kernel (`ftdi_sio`), loads automatically |
| Permissions | None needed | User must be in the `dialout` group: `sudo usermod -aG dialout $USER` (log out/in to apply) |
| Gotchas | — | `ModemManager` sometimes probes new serial devices and delays/blocks the first open; if the port misbehaves: `sudo systemctl stop ModemManager` |

Since the port is stored in the YAML config (`instrument.port`), moving the
same config file between a Windows machine and an Ubuntu machine will trigger
the port-mismatch prompt described below (`COM5` vs `/dev/ttyUSB0`) — that is
expected, not a bug. Avoid hardcoding OS-specific paths in `output.directory`
(e.g. `C:\Users\...`); use a relative path (`./data`) or `~/pm5_data`, which
resolve correctly on both platforms.

To confirm the manufacturer string your OS reports for the FTDI chip (only
needed if autodetection doesn't find the PM5):

```bash
python3 -m serial.tools.list_ports -v
```

## Library usage

```python
from vdi_pm5 import PM5

with PM5(port="COM5") as pm5:      # or PM5() to autodetect by S/N + FTDI
    print(pm5.get_firmware_version())
    reading = pm5.get_power()
    print(f"{reading.watts*1e6:.3f} uW / {reading.dbm:.2f} dBm "
          f"(range={reading.range_code}, auto={reading.auto_range})")
```

## Continuous reading

```python
from vdi_pm5.storage import Hdf5PowerLogger, read_power_log

with PM5() as pm5, Hdf5PowerLogger("measurement.h5", sensor_serial=pm5.target_serial) as logger:
    for reading in pm5.stream_power(poll_interval=0.5, n=100):
        logger.append(reading)

data = read_power_log("measurement.h5")   # numpy structured array
print(data.dtype.names)                   # ('timestamp','watts','dbm','range_code','auto_range','cal_factor_db')
```

## CLI usage

```bash
python -m vdi_pm5.cli
python -m vdi_pm5.cli --port COM5
python -m vdi_pm5.cli --config pm5_config.yaml
```

This opens an interactive shell (`pm5>`) with commands: `power`, `watch [seconds]`,
`log <file.h5> [seconds] [n]`, `zero`, `version`, `range <code> [hold]`,
`hires`, `connect [port]`, `status`, `config show`, `config init [path]`, `help`, `exit`/`quit`.

(With `pip install -e .`, the `vdi-pm5` command is also available.)

### YAML configuration

Copy `pm5_config.example.yaml` (or run `config init pm5_config.yaml` inside the
shell) and adjust it, then start the shell with `--config`:

```bash
python -m vdi_pm5.cli --config pm5_config.yaml
```

Precedence is **CLI arguments > config file > built-in defaults**. The file has
five sections — `instrument`, `measurement`, `display`, `output`, `metadata` —
see `pm5_config.example.yaml` for every field and its meaning.

Unknown sections/keys and wrong types (e.g. `plot: Ture`) are rejected at load
time rather than silently ignored.

**Port handling.** If `instrument.port` is empty, the first successful
autodetection is written back to the file automatically. On later runs, if the
detected port differs from the one on file, the shell prompts:

```
PM5 was detected on port COM7, which differs from the registered value (COM5).
Connect to COM7? [y/N]
```

`instrument.on_port_change` controls this behavior: `ask` (default), `use_detected`
(switch and persist silently — useful for unattended scripts), or `fail` (raise an
error instead of guessing). An explicit `--port` on the command line always wins
and skips this check entirely.

`display.plot`, `display.window_s`, `output.save_plot`/`save_plot_scope` and
live plotting are read by `config` but not yet wired into `watch`/`log` — that
part is still on the [future upgrades](docs/FUTURE_UPGRADES.md) list.

### Continuous reading with HDF5 storage

```
pm5> log measurement.h5 0.5
Recording to measurement.h5 every 0.5s (Ctrl+C to stop) ...
    42 samples | latest:   12.345 uW (  -19.08 dBm)
^C
Done. 42 samples saved to measurement.h5.
```

The HDF5 file uses an extensible dataset (`/power`), so `log` can be run multiple
times against the same file and samples are appended to the end instead of overwriting.

## Structure

```
.
├── requirements.txt          # plain pip install, no package install
├── requirements-plot.txt     # + matplotlib, for the future live-plot feature
├── pm5_config.example.yaml   # copy and edit, then pass with --config
├── pyproject.toml
├── CHANGELOG.md
└── vdi_pm5/
    ├── __init__.py     # Public API: PM5, PowerReading, exceptions
    ├── protocol.py      # Protocol constants, command framing,
    │                     # parsing of Status Bytes 1-3, counts→Watts formula
    ├── driver.py         # PM5 class: serial connection, set/query commands
    ├── storage.py        # Hdf5PowerLogger: incremental logging to HDF5
    ├── config.py          # PM5Config: YAML config, validation, port resolution
    └── cli.py            # Interactive shell (cmd.Cmd) on top of the library
```

# vdi_pm5

Python library to control the **VDI Erickson PM5** power meter (mm/submm,
75 GHz – >3 THz) over USB (FTDI chip exposed as a virtual COM port).

## Installation (development mode)

```bash
pip install -e .
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

## Continuous reading:

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
```

This opens an interactive shell (`pm5>`) with commands: `power`, `watch [seconds]`,
`log <file.h5> [seconds] [n]`, `zero`, `version`, `range <code> [hold]`,
`hires`, `connect [port]`, `status`, `help`, `exit`/`quit`.

(With `pip install -e .`, the `vdi-pm5` command is also available.)

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
vdi_pm5/
├── __init__.py     # Public API: PM5, PowerReading, exceptions
├── protocol.py      # Protocol constants, command framing,
│                     # parsing of Status Bytes 1-3, counts→Watts formula
├── driver.py         # PM5 class: serial connection, set/query commands
├── storage.py        # Hdf5PowerLogger: incremental logging to HDF5
└── cli.py            # Interactive shell (cmd.Cmd) on top of the library
```

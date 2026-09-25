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

## CLI usage

```bash
python -m vdi_pm5.cli power
python -m vdi_pm5.cli power --watch 1.0
python -m vdi_pm5.cli --port COM5 zero
python -m vdi_pm5.cli version
python -m vdi_pm5.cli range 4
```

(With `pip install -e .`, the `vdi-pm5` command is also available.)

## Structure

```
vdi_pm5/
├── __init__.py     # Public API: PM5, PowerReading, exceptions
├── protocol.py      # Protocol constants, command framing,
│                     # parsing of Status Bytes 1-3, counts→Watts formula
├── driver.py         # PM5 class: serial connection, set/query commands
└── cli.py            # CLI (argparse) built on top of the library
```

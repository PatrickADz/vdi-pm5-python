"""YAML configuration for the PM5 driver: instrument, measurement, display,
output and metadata sections.

Uses ruamel.yaml (round-trip mode) instead of PyYAML because the program
itself updates a single field (instrument.port) once the user confirms a
detected-port change, and a comment-blind dumper would strip the user's own
annotations from the file on every save.

Precedence intended for callers (CLI, scripts): CLI arguments > this file >
built-in defaults. This module only implements the file + defaults part;
merging in CLI overrides is the caller's responsibility.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Optional, Union

from ruamel.yaml import YAML

from .exceptions import PM5Error

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


class ConfigError(PM5Error):
    """The configuration file is missing, malformed, or fails validation."""


DEFAULTS: dict[str, Any] = {
    "instrument": {
        "serial_number": "347VA",
        "manufacturer": "FTDI",
        "port": None,               # e.g. "COM5"; None = always autodetect
        "on_port_change": "ask",    # ask | use_detected | fail
        "baudrate": 115200,
        "timeout": 1.0,
    },
    "measurement": {
        "interval_s": 1.0,
        "duration_s": None,         # stop after this many seconds (None = unlimited)
        "n_samples": None,          # stop after this many samples (None = unlimited)
        "initial_range": None,      # 1-8; requires the front-panel switch on "Remote"
        "range_hold": False,
        "zero_on_start": False,     # only safe with the RF source off, connected to the DUT
    },
    "display": {
        "units": "dBm",             # uW | mW | dBm
        "plot": False,              # live plot while measuring
        "window_s": 60,             # seconds visible before the live plot scrolls
        "y_scale": "auto",          # auto | log
        "refresh_hz": 5,            # plot redraw rate, independent of the sampling rate
    },
    "output": {
        "save": True,
        "formats": ["h5"],          # h5, csv (both can be listed)
        "directory": "./data",
        "filename_template": "{date}_{time}_{name}",
        "save_plot": False,
        "save_plot_scope": "window",  # window (last window_s only) | full (entire run)
        "plot_format": "png",
        "dpi": 150,
    },
    "metadata": {
        "operator": None,
        "source_frequency_ghz": None,
        "taper_band": None,
        "dut": None,
        "notes": None,
    },
}

_VALID_ON_PORT_CHANGE = {"ask", "use_detected", "fail"}
_VALID_UNITS = {"uW", "mW", "dBm"}
_VALID_Y_SCALE = {"auto", "log"}
_VALID_FORMATS = {"h5", "csv"}
_VALID_PLOT_SCOPE = {"window", "full"}

_BOOL_FIELDS = [
    ("measurement", "range_hold"),
    ("measurement", "zero_on_start"),
    ("display", "plot"),
    ("output", "save"),
    ("output", "save_plot"),
]
_NUMERIC_FIELDS = [
    ("instrument", "baudrate"),
    ("instrument", "timeout"),
    ("measurement", "interval_s"),
    ("display", "window_s"),
    ("display", "refresh_hz"),
    ("output", "dpi"),
]


def _deep_merge_defaults(loaded: dict) -> dict:
    merged: dict[str, Any] = {}
    for section, fields in DEFAULTS.items():
        merged[section] = dict(fields)
        if loaded.get(section):
            merged[section].update(loaded[section])
    return merged


def _validate(cfg: dict) -> None:
    for section in cfg:
        if section not in DEFAULTS:
            raise ConfigError(f"Unknown config section: '{section}'")
    for section, fields in cfg.items():
        for key in fields:
            if key not in DEFAULTS[section]:
                raise ConfigError(f"Unknown key '{key}' in section '{section}'")

    for section, key in _BOOL_FIELDS:
        value = cfg[section][key]
        if not isinstance(value, bool):
            raise ConfigError(
                f"{section}.{key} must be a boolean (true/false), got {value!r}"
            )
    for section, key in _NUMERIC_FIELDS:
        value = cfg[section][key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(f"{section}.{key} must be a number, got {value!r}")

    inst = cfg["instrument"]
    if inst["on_port_change"] not in _VALID_ON_PORT_CHANGE:
        raise ConfigError(f"instrument.on_port_change must be one of {_VALID_ON_PORT_CHANGE}")

    disp = cfg["display"]
    if disp["units"] not in _VALID_UNITS:
        raise ConfigError(f"display.units must be one of {_VALID_UNITS}")
    if disp["y_scale"] not in _VALID_Y_SCALE:
        raise ConfigError(f"display.y_scale must be one of {_VALID_Y_SCALE}")
    if disp["refresh_hz"] <= 0:
        raise ConfigError("display.refresh_hz must be positive")
    if disp["window_s"] <= 0:
        raise ConfigError("display.window_s must be positive")

    out = cfg["output"]
    bad_formats = set(out["formats"]) - _VALID_FORMATS
    if bad_formats:
        raise ConfigError(f"output.formats has unknown values: {bad_formats} (valid: {_VALID_FORMATS})")
    if out["save_plot_scope"] not in _VALID_PLOT_SCOPE:
        raise ConfigError(f"output.save_plot_scope must be one of {_VALID_PLOT_SCOPE}")

    meas = cfg["measurement"]
    if meas["initial_range"] is not None and not (1 <= int(meas["initial_range"]) <= 8):
        raise ConfigError("measurement.initial_range must be between 1 and 8")
    if meas["interval_s"] <= 0:
        raise ConfigError("measurement.interval_s must be positive")


class PM5Config:
    """Loads, validates and partially rewrites a PM5 YAML config file.

    Unknown top-level sections or keys are rejected at load time, so a typo
    like `plot: Ture` is not silently ignored. Saving only ever touches the
    keys defined in DEFAULTS, so comments and formatting elsewhere in the
    user's file are preserved (ruamel.yaml round-trip mode).
    """

    def __init__(self, data: dict, path: Optional[Path] = None, yaml_doc: Any = None):
        self.data = data
        self.path = path
        self._yaml_doc = yaml_doc  # ruamel round-trip document, if loaded from a file

    @classmethod
    def load(cls, path: Union[str, Path]) -> "PM5Config":
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            doc = _yaml.load(f) or {}
        merged = _deep_merge_defaults(doc)
        _validate(merged)
        return cls(merged, path=path, yaml_doc=doc)

    @classmethod
    def defaults(cls) -> "PM5Config":
        return cls(copy.deepcopy(DEFAULTS))

    def save(self) -> None:
        """Writes the config back to `self.path`, preserving comments/formatting
        for anything the user added; only known fields are written/updated."""
        if self.path is None:
            raise ConfigError("This config was not loaded from a file; nothing to save to.")
        if self._yaml_doc is None:
            self._yaml_doc = {}
        for section, fields in self.data.items():
            if not self._yaml_doc.get(section):
                self._yaml_doc[section] = {}
            for key, value in fields.items():
                self._yaml_doc[section][key] = value
        with self.path.open("w", encoding="utf-8") as f:
            _yaml.dump(self._yaml_doc, f)

    def set(self, section: str, key: str, value: Any) -> None:
        if section not in DEFAULTS or key not in DEFAULTS[section]:
            raise ConfigError(f"Unknown config field: {section}.{key}")
        self.data[section][key] = value

    @property
    def instrument(self) -> dict:
        return self.data["instrument"]

    @property
    def measurement(self) -> dict:
        return self.data["measurement"]

    @property
    def display(self) -> dict:
        return self.data["display"]

    @property
    def output(self) -> dict:
        return self.data["output"]

    @property
    def metadata(self) -> dict:
        return self.data["metadata"]


def resolve_port(
    cfg: PM5Config,
    detected: Optional[str],
    confirm: Optional[Callable[[str, str], bool]] = None,
) -> Optional[str]:
    """Decide which serial port to use, given the configured and detected ports.

    - No port configured: use whatever was detected (nothing to compare).
    - Configured port matches detected: use it, no prompt.
    - They differ: follow `instrument.on_port_change`:
        * "fail": raise ConfigError.
        * "use_detected": switch silently and persist the new port.
        * "ask" (default): call `confirm(configured, detected)`; if it
          returns True, switch and persist; otherwise keep the configured
          port. If no `confirm` callback is given (non-interactive use),
          the configured port is kept rather than guessing.
    """
    configured = cfg.instrument.get("port")
    if not configured:
        if detected is not None and cfg.path is not None:
            # First time we see this instrument: remember it, no prompt needed
            # since there is nothing to conflict with yet.
            cfg.set("instrument", "port", detected)
            cfg.save()
        return detected
    if detected is None or detected == configured:
        return configured

    policy = cfg.instrument.get("on_port_change", "ask")
    if policy == "fail":
        raise ConfigError(
            f"Configured port '{configured}' does not match the detected port '{detected}'."
        )
    if policy == "use_detected":
        cfg.set("instrument", "port", detected)
        if cfg.path is not None:
            cfg.save()
        return detected

    # policy == "ask"
    if confirm is None:
        return configured
    if confirm(configured, detected):
        cfg.set("instrument", "port", detected)
        if cfg.path is not None:
            cfg.save()
        return detected
    return configured


EXAMPLE_YAML = """\
# PM5 configuration file.
# Precedence: CLI arguments > this file > built-in defaults.

instrument:
  serial_number: "347VA"      # sensor head serial number, used for autodetection
  manufacturer: "FTDI"        # USB chip manufacturer string used for autodetection
  port: null                  # e.g. "COM5"; null = always autodetect, never persisted
  on_port_change: ask         # ask | use_detected | fail
  baudrate: 115200
  timeout: 1.0

measurement:
  interval_s: 1.0             # seconds between samples
  duration_s: null            # stop after this many seconds (null = unlimited)
  n_samples: null             # stop after this many samples (null = unlimited)
  initial_range: null         # 1-8; requires the front-panel switch on "Remote"
  range_hold: false
  zero_on_start: false        # only zero with the RF source off and connected to the DUT

display:
  units: dBm                  # uW | mW | dBm
  plot: false                 # live plot while measuring
  window_s: 60                # seconds visible in the live plot before it scrolls
  y_scale: auto                # auto | log
  refresh_hz: 5                # plot redraw rate (independent of the sampling rate)

output:
  save: true
  formats: [h5]                 # h5, csv (both can be listed)
  directory: "./data"
  filename_template: "{date}_{time}_{name}"
  save_plot: false              # save a plot image when the measurement ends
  save_plot_scope: window       # window (last window_s only) | full (entire run)
  plot_format: png
  dpi: 150

metadata:
  operator: null
  source_frequency_ghz: null
  taper_band: null
  dut: null
  notes: null
"""


def write_example(path: Union[str, Path]) -> Path:
    """Writes a commented example config file to `path` (used by `config init`)."""
    path = Path(path)
    path.write_text(EXAMPLE_YAML, encoding="utf-8")
    return path

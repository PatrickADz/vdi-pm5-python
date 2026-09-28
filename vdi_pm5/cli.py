"""Interactive shell for the PM5 power meter.

Usage:
    python -m vdi_pm5.cli
    python -m vdi_pm5.cli --port COM5
    python -m vdi_pm5.cli --port COM5 --verbose

Inside the shell (prompt "pm5>"):
    power: read power once
    watch [seconds]: continuous polling (Ctrl+C to stop), default 1s
    zero: zero the current range
    version: query firmware version
    range <code> [hold]: set the range (1-4 fixed, 5-8 auto; 'hold' enables range hold)
    hires: high-resolution power reading
    log <file.h5> [seconds] [n] -> continuous reading with HDF5 storage
    connect [port]: (re)connect; autodetects if port is omitted
    status: show current port/connection status
    help [command]: help
    exit / quit / Ctrl+D: exit
"""
from __future__ import annotations

import argparse
import cmd
import logging

from .driver import PM5
from .exceptions import PM5Error
from .storage import Hdf5PowerLogger

logger = logging.getLogger(__name__)


class PM5Shell(cmd.Cmd):
    intro = "PM5 shell. Type 'help' to see the available commands.\n"
    prompt = "pm5> "

    def __init__(self, port: str | None = None, baudrate: int = PM5.DEFAULT_BAUDRATE):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.pm5: PM5 | None = None
        self._try_connect(startup=True)

    def _try_connect(self, startup: bool = False) -> None:
        try:
            self.pm5 = PM5(port=self.port, baudrate=self.baudrate)
            self.port = self.pm5.port
            print(f"Connected on {self.port}.")
        except PM5Error as exc:
            self.pm5 = None
            prefix = "Could not connect on startup" if startup else "Could not connect"
            print(f"{prefix}: {exc}")
            if startup:
                print("Use 'connect [port]' to retry once the hardware is ready.")

    def _require_pm5(self) -> PM5 | None:
        if self.pm5 is None or not self.pm5.is_connected:
            print("There is no active connection to the PM5. Use 'connect [port]' first.")
            return None
        return self.pm5

    def do_connect(self, arg: str) -> None:
        """connect [port]  ->  (re)connect to the PM5; autodetects without an argument."""
        if self.pm5 is not None:
            self.pm5.disconnect()
        self.port = arg.strip() or None
        self._try_connect()

    def do_status(self, arg: str) -> None:
        """status  ->  show the port and whether a connection is active."""
        if self.pm5 is not None and self.pm5.is_connected:
            print(f"Connected on {self.port} (baudrate={self.baudrate}).")
        else:
            print("No active connection.")

    def do_power(self, arg: str) -> None:
        """power  ->  read power once."""
        pm5 = self._require_pm5()
        if not pm5:
            return
        try:
            r = pm5.get_power()
            print(f"{r.watts * 1e6:9.3f} uW  |  {r.dbm:7.2f} dBm  "
                  f"(range={r.range_code}, auto={r.auto_range}, cal={r.cal_factor_db:+.1f} dB)")
        except PM5Error as exc:
            print(f"Error: {exc}")

    def do_watch(self, arg: str) -> None:
        """watch [seconds]  ->  continuous polling (default 1s). Ctrl+C to stop."""
        pm5 = self._require_pm5()
        if not pm5:
            return
        try:
            interval = float(arg.strip()) if arg.strip() else 1.0
        except ValueError:
            print("Invalid interval; for example: watch 0.5")
            return
        print("Press Ctrl+C to stop.")
        try:
            for r in pm5.stream_power(poll_interval=interval):
                print(f"{r.watts * 1e6:9.3f} uW  |  {r.dbm:7.2f} dBm  "
                      f"(range={r.range_code}, auto={r.auto_range})")
        except KeyboardInterrupt:
            print()  # clean line after ^C
        except PM5Error as exc:
            print(f"Error: {exc}")

    def do_zero(self, arg: str) -> None:
        """zero  ->  zero the current range (same as the physical button)."""
        pm5 = self._require_pm5()
        if not pm5:
            return
        try:
            pm5.zero()
            print("Current range zeroed.")
        except PM5Error as exc:
            print(f"Error: {exc}")

    def do_version(self, arg: str) -> None:
        """version  ->  query the firmware version."""
        pm5 = self._require_pm5()
        if not pm5:
            return
        try:
            print(pm5.get_firmware_version())
        except PM5Error as exc:
            print(f"Error: {exc}")

    def do_range(self, arg: str) -> None:
        """range <code> [hold]  ->  set the range (1-4 fixed, 5-8 auto).

        Requires the physical switch to be in 'Remote'. 'hold' enables range
        hold for auto codes (5-8).
        """
        pm5 = self._require_pm5()
        if not pm5:
            return
        parts = arg.split()
        if not parts:
            print("Usage: range <code 1-8> [hold]")
            return
        try:
            code = int(parts[0])
        except ValueError:
            print("The range code must be an integer (1-8).")
            return
        hold = len(parts) > 1 and parts[1].lower() == "hold"
        try:
            pm5.set_range(code, range_hold=hold)
            print(f"Range set to code {code} (hold={hold}).")
        except (PM5Error, ValueError) as exc:
            print(f"Error: {exc}")

    def do_hires(self, arg: str) -> None:
        """hires  ->  high-resolution power reading (mW)."""
        pm5 = self._require_pm5()
        if not pm5:
            return
        try:
            mw = pm5.get_power_high_res()
            print(f"{mw:.6e} mW")
        except PM5Error as exc:
            print(f"Error: {exc}")

    def do_log(self, arg: str) -> None:
        """log <file.h5> [seconds] [n]  ->  continuous reading saved to HDF5.

        seconds: sampling interval (default 1.0).
        n: number of samples to take; if omitted, it runs indefinitely
           until Ctrl+C. If the file already exists, samples are appended
           to the end (it is not overwritten).
        """
        pm5 = self._require_pm5()
        if not pm5:
            return
        parts = arg.split()
        if not parts:
            print("Usage: log <file.h5> [seconds] [n]")
            return
        path = parts[0]
        try:
            interval = float(parts[1]) if len(parts) > 1 else 1.0
            n = int(parts[2]) if len(parts) > 2 else None
        except ValueError:
            print("Invalid arguments. Usage: log <file.h5> [seconds] [n]")
            return

        print(f"Recording to {path} every {interval}s"
              + (f" ({n} samples)" if n else " (Ctrl+C to stop)") + " ...")
        count = 0
        try:
            with Hdf5PowerLogger(path, sensor_serial=pm5.target_serial) as logger:
                for r in pm5.stream_power(n=n, poll_interval=interval):
                    logger.append(r)
                    count += 1
                    print(f"\r{count:6d} samples | latest: {r.watts * 1e6:9.3f} uW "
                          f"({r.dbm:7.2f} dBm)", end="", flush=True)
        except KeyboardInterrupt:
            pass
        except PM5Error as exc:
            print(f"\nError: {exc}")
        finally:
            print(f"\nDone. {count} samples saved to {path}.")

    def do_exit(self, arg: str) -> bool:
        """exit  ->  close the connection and leave the shell."""
        if self.pm5 is not None:
            self.pm5.disconnect()
        print("Bye.")
        return True

    do_quit = do_exit

    def do_EOF(self, arg: str) -> bool:
        """Ctrl+D  ->  same as 'exit'."""
        print()
        return self.do_exit(arg)

    def emptyline(self) -> None:
        # Do not repeat the last command when pressing Enter on an empty line (default of cmd.Cmd).
        pass

    def default(self, line: str) -> None:
        print(f"Unknown command: {line!r}. Type 'help' to see the available commands.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vdi-pm5", description="Interactive shell for a VDI Erickson PM5")
    parser.add_argument("--port", default=None, help="Serial port (autodetected if omitted)")
    parser.add_argument("--baudrate", type=int, default=PM5.DEFAULT_BAUDRATE)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    PM5Shell(port=args.port, baudrate=args.baudrate).cmdloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

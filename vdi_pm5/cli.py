"""Simple CLI for the PM5 power meter.

Examples:
    python -m vdi_pm5.cli power
    python -m vdi_pm5.cli power --watch 1.0
    python -m vdi_pm5.cli --port COM5 zero
    python -m vdi_pm5.cli version
    python -m vdi_pm5.cli range 4
"""
from __future__ import annotations

import argparse
import logging
import sys

from .driver import PM5
from .exceptions import PM5Error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vdi-pm5", description="Controls a VDI Erickson PM5 power meter")
    parser.add_argument("--port", default=None, help="Serial port (autodetected if omitted)")
    parser.add_argument("--baudrate", type=int, default=PM5.DEFAULT_BAUDRATE)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_power = sub.add_parser("power", help="Read power once or repeatedly with --watch")
    p_power.add_argument("--watch", type=float, default=None, metavar="SECONDS",
                          help="Poll continuously every SECONDS")

    sub.add_parser("zero", help="Zero the current range")
    sub.add_parser("version", help="Query firmware version")

    p_range = sub.add_parser("range", help="Set the range (requires front panel in 'Remote'")
    p_range.add_argument("code", type=int, help="1=200uW 2=2mW 3=20mW 4=200mW 5-8=auto variants")
    p_range.add_argument("--hold", action="store_true", help="Enable range hold (auto ranges only)")

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    try:
        with PM5(port=args.port, baudrate=args.baudrate) as pm5:
            if args.command == "power":
                if args.watch:
                    try:
                        for r in pm5.stream_power(poll_interval=args.watch):
                            print(f"{r.watts * 1e6:9.3f} uW  |  {r.dbm:7.2f} dBm  "
                                  f"(range={r.range_code}, auto={r.auto_range})")
                    except KeyboardInterrupt:
                        pass
                else:
                    r = pm5.get_power()
                    print(f"{r.watts * 1e6:.3f} uW  ({r.dbm:.2f} dBm)  range={r.range_code} auto={r.auto_range}")
            elif args.command == "zero":
                pm5.zero()
                print("Current range zeroed.")
            elif args.command == "version":
                print(pm5.get_firmware_version())
            elif args.command == "range":
                pm5.set_range(args.code, range_hold=args.hold)
                print(f"Range set to code {args.code} (hold={args.hold}).")
    except PM5Error as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

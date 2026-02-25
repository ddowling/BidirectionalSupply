#!/usr/bin/env python3
# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
"""Control an ITECH IT85xx DC load over serial."""

import argparse
from itech_serial import IT8500

# op_state bits (1 byte) — from libsigrok itech-it8500/protocol.h
_OP_STATE_BITS = [
    (0, "cal",    "Calibration mode"),
    (1, "wtg",    "Waiting for trigger"),
    (2, "rem",    "Remote control"),
    (3, "out",    "Output on"),
    (4, "local",  "Local sense"),
    (5, "sense",  "Sense active"),
    (6, "lot",    "Load on timer"),
]

# demand_state bits (2 bytes) — from libsigrok itech-it8500/protocol.h
_DEMAND_STATE_BITS = [
    (0, "rv",  "Reverse voltage"),
    (1, "ov",  "Over-voltage protection"),
    (2, "oc",  "Over-current protection"),
    (3, "op",  "Over-power protection"),
    (4, "ot",  "Over-temperature protection"),
    (5, "sv",  "Start voltage"),
    (6, "cc",  "CC mode (constant current)"),
    (7, "cv",  "CV mode (constant voltage)"),
    (8, "cw",  "CW mode (constant power)"),
    (9, "cr",  "CR mode (constant resistance)"),
]


def _decode_bits(value, bit_defs):
    active = [label for bit, label, _ in bit_defs if value & (1 << bit)]
    return ", ".join(active) if active else "none"


def print_measure(m):
    print(f"  Voltage:      {m['voltage']:.3f} V")
    print(f"  Current:      {m['current']:.3f} A")
    print(f"  Power:        {m['power']:.3f} W")
    op = int(m['op_state'], 16)
    ds = int(m['demand_state'], 16)
    print(f"  Op state:     {m['op_state']}  [{_decode_bits(op, _OP_STATE_BITS)}]")
    print(f"  Demand state: {m['demand_state']}  [{_decode_bits(ds, _DEMAND_STATE_BITS)}]")


def main():
    parser = argparse.ArgumentParser(
        description="Control an ITECH IT85xx DC load over serial."
    )
    parser.add_argument(
        "--port", "-p",
        default="/dev/ttyUSB0",
        help="Serial port (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--identify", "-i",
        action="store_true",
        help="Print identify() results",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["local", "remote", "enable", "disable"],
        help="local/remote: set control mode; enable/disable: turn load on or off. "
             "Omit to show measurements only",
    )
    args = parser.parse_args()

    load = IT8500(args.port)

    if args.identify:
        info = load.identify()
        for key, value in info.items():
            print(f"  {key}: {value}")

    m = load.measure()
    print_measure(m)

    if args.mode is None:
        return

    if args.mode == "local":
        load.control_set_local()
        print("Set to local control")
    elif args.mode == "remote":
        load.control_set_remote()
        print("Set to remote control")
    elif args.mode == "enable":
        load.enable()
        print("Load enabled")
    elif args.mode == "disable":
        load.disable()
        print("Load disabled")


if __name__ == "__main__":
    main()

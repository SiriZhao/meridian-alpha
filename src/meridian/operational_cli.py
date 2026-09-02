"""Additive operational-data command while the legacy CLI is being migrated."""

from __future__ import annotations

import argparse
import json

from meridian.operational_data import data_status


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian data-status")
    parser.add_argument("--json", action="store_true", help="emit machine-readable status")
    args = parser.parse_args()
    payload = data_status()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for label, value in payload.items():
            print(f"{label.replace('_', ' ').title():<24} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

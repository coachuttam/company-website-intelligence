"""Command line: python -m wi.render data/runs/razorpay_com.json [-o out.html]"""
from __future__ import annotations

import argparse
import sys

from wi.render.page import render_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render a saved run JSON as a reference profile page.")
    parser.add_argument("run_json", help="path to a data/runs/<site>.json file")
    parser.add_argument("-o", "--output", help="output .html path (default: data/pages/<name>.html)")
    args = parser.parse_args(argv)
    try:
        out = render_file(args.run_json, args.output)
    except (OSError, ValueError) as exc:
        print("Could not render: " + str(exc))
        return 1
    print("Wrote " + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

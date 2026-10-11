"""Command line: python -m wi.render data/runs/razorpay_com.json [-o out.html] [--pdf]"""
from __future__ import annotations

import argparse
import sys

from wi.render.page import render_file, render_pdf_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render a saved run JSON as a reference profile page.")
    parser.add_argument("run_json", help="path to a data/runs/<site>.json file")
    parser.add_argument("-o", "--output", help="output path (default: data/pages/<name>.html, or .pdf with --pdf)")
    parser.add_argument("--pdf", action="store_true",
                        help="write a PDF instead of HTML (needs playwright and its chromium)")
    args = parser.parse_args(argv)
    try:
        if args.pdf:
            out, pages = render_pdf_file(args.run_json, args.output)
            print("Wrote " + str(out) + " (" + str(pages) + " pages)")
            return 0
        out = render_file(args.run_json, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print("Could not render: " + str(exc))
        return 1
    print("Wrote " + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Command line: ``python -m asset_scene render scene.json --out DIR``."""

from __future__ import annotations

import argparse
import json
import sys

from .render import render_all
from .schema import AssetScene
from .style import ColorBy


def main(argv: list[str] | None = None) -> int:
    """Validate and render a scene JSON file."""
    parser = argparse.ArgumentParser(prog="asset_scene")
    sub = parser.add_subparsers(dest="cmd", required=True)
    val = sub.add_parser(
        "validate", help="check a scene file against neqsim_asset_scene.v1"
    )
    val.add_argument("scene")
    ren = sub.add_parser("render", help="write GLB, HTML and PNG views")
    ren.add_argument("scene")
    ren.add_argument("--out", required=True)
    ren.add_argument("--stem", default="asset_scene")
    ren.add_argument("--views", default="iso,plan")
    ren.add_argument("--vertical-exaggeration", type=float, default=1.0)
    ren.add_argument(
        "--color-by",
        help="channel:key, for example results:utilisation or live:pressure",
    )
    ren.add_argument(
        "--mode", default="sequential", choices=["sequential", "utilisation"]
    )
    ren.add_argument("--unit", default="")
    args = parser.parse_args(argv)
    scene = AssetScene.load(args.scene)
    issues = scene.validate()
    if args.cmd == "validate":
        print(json.dumps({"valid": not issues, "issues": issues}, indent=2))
        return 0 if not issues else 1
    if issues:
        print(json.dumps({"valid": False, "issues": issues}, indent=2))
        return 1
    color_by = None
    if args.color_by:
        channel, key = args.color_by.split(":", 1)
        color_by = ColorBy(channel, key, mode=args.mode, unit=args.unit)
    result = render_all(
        scene,
        args.out,
        stem=args.stem,
        color_by=color_by,
        views=[v for v in args.views.split(",") if v],
        vertical_exaggeration=args.vertical_exaggeration,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

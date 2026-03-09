#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from PIL import Image


def add_white_border_then_resize_back(in_path: Path, out_path: Path, pct: float = 0.05):
    img = Image.open(in_path).convert("RGBA")  # 保留透明也行；白边会是白色不透明
    w, h = img.size

    border = int(round(w * pct))  # 按“宽度的5%”计算边框厚度
    new_w, new_h = w + 2 * border, h + 2 * border

    # 白色背景（不透明）
    canvas = Image.new("RGBA", (new_w, new_h), (255, 255, 255, 255))
    canvas.paste(img, (border, border), img)  # 用 img 作为 mask，避免透明区域变黑

    # 再缩回原始大小
    out = canvas.resize((w, h), Image.Resampling.LANCZOS)

    # 如果你想输出为不带透明的 PNG/JPG，可转成 RGB
    if out_path.suffix.lower() in [".jpg", ".jpeg"]:
        out = out.convert("RGB")

    out.save(out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Add 5%% white border on all sides, then resize back to original size."
    )
    parser.add_argument("input", help="Input image path")
    parser.add_argument("-o", "--output", help="Output image path (optional)")
    parser.add_argument("--pct", type=float, default=0.05, help="Border percentage of width (default 0.05)")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = in_path.with_name(in_path.stem + "_padded" + in_path.suffix)

    add_white_border_then_resize_back(in_path, out_path, pct=args.pct)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
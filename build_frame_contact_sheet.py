from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frame", type=int, default=1)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()

    files = sorted(args.frames.glob(f"*_{args.frame:02d}.jpg"))
    thumb_w, thumb_h, label_h = 384, 216, 28
    rows = (len(files) + args.columns - 1) // args.columns
    sheet = Image.new("RGB", (args.columns * thumb_w, rows * (thumb_h + label_h)), "black")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    for number, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = (number % args.columns) * thumb_w
        y = (number // args.columns) * (thumb_h + label_h)
        sheet.paste(image, (x + (thumb_w - image.width) // 2, y))
        label = path.name.split("_", 1)[0]
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + label_h), fill="black")
        draw.text((x + 8, y + thumb_h + 3), label, fill="white", font=font)
    sheet.save(args.output, quality=92)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image


def capture(ffmpeg: Path, url: str, target: Path, seconds: int) -> None:
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-rw_timeout",
            "30000000",
            "-i",
            url,
            "-vf",
            "fps=1,scale=320:180",
            "-frames:v",
            str(seconds),
            "-q:v",
            "3",
            "-y",
            str(target / "%03d.jpg"),
        ],
        check=True,
        timeout=seconds + 45,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def vector(path: Path) -> np.ndarray:
    pixels = np.asarray(Image.open(path).convert("L").resize((64, 36)), dtype=np.float32)
    pixels -= pixels.mean()
    deviation = pixels.std()
    return (pixels / deviation if deviation else pixels).reshape(-1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url_a")
    parser.add_argument("url_b")
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(capture, args.ffmpeg, args.url_a, args.output / "a", args.seconds),
            executor.submit(capture, args.ffmpeg, args.url_b, args.output / "b", args.seconds),
        ]
        for future in futures:
            future.result()

    a = [vector(path) for path in sorted((args.output / "a").glob("*.jpg"))]
    b = [vector(path) for path in sorted((args.output / "b").glob("*.jpg"))]
    best: tuple[float, int, int, int] | None = None
    for offset in range(-12, 13):
        pairs = []
        for index_a in range(len(a)):
            index_b = index_a + offset
            if 0 <= index_b < len(b):
                pairs.append(float(np.dot(a[index_a], b[index_b]) / len(a[index_a])))
        if not pairs:
            continue
        mean = sum(pairs) / len(pairs)
        strong = sum(value >= 0.95 for value in pairs)
        candidate = (mean, strong, len(pairs), offset)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    print(
        {
            "frames_a": len(a),
            "frames_b": len(b),
            "best_mean_correlation": round(best[0], 6) if best else None,
            "strong_matches": best[1] if best else 0,
            "compared_pairs": best[2] if best else 0,
            "offset_seconds": best[3] if best else None,
        }
    )


if __name__ == "__main__":
    main()

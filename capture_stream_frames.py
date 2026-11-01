from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from audit_playlist import parse_playlist


def capture(entry, ffmpeg: Path, output: Path, timeout: int) -> tuple[int, str, bool, str]:
    target = output / f"{entry.index:03d}_{entry.tvg_id or 'noid'}_%02d.jpg"
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-rw_timeout",
        str(max(timeout - 3, 5) * 1_000_000),
    ]
    if entry.user_agent:
        command.extend(["-user_agent", entry.user_agent])
    if entry.referrer:
        command.extend(["-headers", f"Referer: {entry.referrer}\r\n"])
    command.extend(
        [
            "-i",
            entry.url,
            "-vf",
            "fps=1/5,scale=640:-2",
            "-frames:v",
            "3",
            "-q:v",
            "2",
            "-y",
            str(target),
        ]
    )
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        found = any(output.glob(f"{entry.index:03d}_{entry.tvg_id or 'noid'}_*.jpg"))
        return entry.index, entry.name, found, proc.stderr.strip()[-500:]
    except subprocess.TimeoutExpired as exc:
        found = any(output.glob(f"{entry.index:03d}_{entry.tvg_id or 'noid'}_*.jpg"))
        return entry.index, entry.name, found, f"timeout: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("playlist", type=Path)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=35)
    args = parser.parse_args()

    wanted = {int(value) for value in args.indices.split(",") if value.strip()}
    entries = [entry for entry in parse_playlist(args.playlist) if entry.index in wanted]
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(capture, entry, args.ffmpeg, args.output, args.timeout)
            for entry in entries
        ]
        for future in as_completed(futures):
            index, name, found, error = future.result()
            print(f"{index:03d} {'ok' if found else 'failed'} {name}")
            if error and not found:
                print(error)


if __name__ == "__main__":
    main()

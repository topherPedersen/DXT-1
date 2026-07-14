from __future__ import annotations

import argparse
import csv
from pathlib import Path

import soundfile as sf
from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser(
        description="Decode every WAV referenced by the GMD metadata."
    )
    parser.add_argument("dataset_root")
    args = parser.parse_args()

    root = Path(args.dataset_root).expanduser().resolve()
    csv_path = root / "info.csv"
    if not csv_path.is_file():
        raise SystemExit(f"info.csv not found: {csv_path}")

    paths = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("audio_filename") or "").strip()
            if name:
                path = root / name
                if path.is_file():
                    paths.append(path)

    failures = []
    for path in tqdm(paths, desc="checking WAV files"):
        try:
            data, sample_rate = sf.read(
                str(path),
                dtype="float32",
                always_2d=True,
            )
            if data.size == 0:
                raise RuntimeError("empty audio")
        except Exception as exc:
            failures.append((path, str(exc)))

    print(f"\nChecked {len(paths)} WAV files.")
    if failures:
        print(f"Found {len(failures)} unreadable files:")
        for path, error in failures:
            print(f"\n{path}\n  {error}")
        raise SystemExit(1)

    print("All referenced WAV files decoded successfully with soundfile.")


if __name__ == "__main__":
    main()

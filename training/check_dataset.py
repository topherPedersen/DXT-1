from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root")
    args = parser.parse_args()

    root = Path(args.dataset_root).expanduser().resolve()
    csv_path = root / "info.csv"
    if not csv_path.is_file():
        raise SystemExit(f"info.csv not found at {csv_path}")

    counts = Counter()
    bad_examples = []

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        print("Columns:", reader.fieldnames)

        for line_number, row in enumerate(reader, start=2):
            counts["rows"] += 1
            split = (row.get("split") or "").strip()
            counts[f"split:{split or '<blank>'}"] += 1

            audio_name = (row.get("audio_filename") or "").strip()
            midi_name = (row.get("midi_filename") or "").strip()

            if not audio_name:
                counts["blank_audio_filename"] += 1
                if len(bad_examples) < 10:
                    bad_examples.append((line_number, "blank audio_filename", row))
                continue
            if not midi_name:
                counts["blank_midi_filename"] += 1
                if len(bad_examples) < 10:
                    bad_examples.append((line_number, "blank midi_filename", row))
                continue

            audio = root / audio_name
            midi = root / midi_name

            if not audio.is_file():
                counts["missing_audio_file"] += 1
                if len(bad_examples) < 10:
                    bad_examples.append((line_number, f"missing audio: {audio}", row))
            else:
                counts["valid_audio_file"] += 1

            if not midi.is_file():
                counts["missing_midi_file"] += 1
                if len(bad_examples) < 10:
                    bad_examples.append((line_number, f"missing MIDI: {midi}", row))
            else:
                counts["valid_midi_file"] += 1

    print("\nCounts:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")

    if bad_examples:
        print("\nFirst problematic rows:")
        for line, reason, row in bad_examples:
            print(f"  line {line}: {reason}")
            print(f"    audio_filename={row.get('audio_filename')!r}")
            print(f"    midi_filename={row.get('midi_filename')!r}")
            print(f"    split={row.get('split')!r}")
    else:
        print("\nNo malformed or missing file references were found.")


if __name__ == "__main__":
    main()

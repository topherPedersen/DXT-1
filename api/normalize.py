from __future__ import annotations

from pathlib import Path

import mido

# Collapse common GM percussion notes into a stable RD-8-oriented subset.
NOTE_MAP = {
    35: 36, 36: 36,                         # kick
    37: 40, 38: 40, 39: 40, 40: 40,       # snare/clap
    42: 42, 44: 42,                         # closed/pedal hat
    46: 46,                                 # open hat
    41: 45, 43: 45, 45: 45,                # low tom
    47: 47, 48: 47,                         # mid tom
    50: 50,                                 # high tom
    49: 49, 52: 49, 55: 49, 57: 49,        # crash
    51: 51, 53: 51, 59: 51,                # ride
}


def normalize_oaf_midi(source: str | Path, destination: str | Path) -> dict:
    source_mid = mido.MidiFile(source)
    output = mido.MidiFile(type=1, ticks_per_beat=source_mid.ticks_per_beat)
    track = mido.MidiTrack()
    output.tracks.append(track)

    merged = mido.merge_tracks(source_mid.tracks)
    absolute = 0
    timeline: list[tuple[int, int, mido.Message | mido.MetaMessage]] = []
    input_hits = 0
    output_hits = 0
    unmapped: dict[int, int] = {}

    for message in merged:
        absolute += message.time
        if message.is_meta:
            if message.type in {"set_tempo", "time_signature"}:
                timeline.append((absolute, 0, message.copy(time=0)))
            continue

        if message.type not in {"note_on", "note_off"}:
            continue

        input_hits += int(message.type == "note_on" and message.velocity > 0)
        mapped = NOTE_MAP.get(message.note)
        if mapped is None:
            if message.type == "note_on" and message.velocity > 0:
                unmapped[message.note] = unmapped.get(message.note, 0) + 1
            continue

        is_on = message.type == "note_on" and message.velocity > 0
        converted = mido.Message(
            "note_on" if is_on else "note_off",
            channel=9,
            note=mapped,
            velocity=message.velocity if is_on else 0,
            time=0,
        )
        timeline.append((absolute, 2 if is_on else 1, converted))
        output_hits += int(is_on)

    timeline.sort(key=lambda row: (row[0], row[1]))
    previous = 0
    track.append(mido.MetaMessage("track_name", name="OaF RD-8", time=0))
    for tick, _, message in timeline:
        message.time = max(0, tick - previous)
        track.append(message)
        previous = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    output.save(destination)

    return {
        "oaf_input_hits": input_hits,
        "mapped_rd8_hits": output_hits,
        "unmapped_pitch_counts": unmapped,
    }

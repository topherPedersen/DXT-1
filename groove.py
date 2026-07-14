from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mido

# General MIDI percussion notes accepted by the RD-8-oriented player.
ALLOWED_NOTES = {36, 38, 40, 42, 43, 45, 46, 47, 49, 50, 51}
CORE_NOTES = {36, 38, 40, 42, 46}
ORNAMENT_NOTES = ALLOWED_NOTES - CORE_NOTES


@dataclass(frozen=True)
class GrooveOptions:
    bars: int = 2
    quantize_division: int = 16
    complexity: float = 0.55
    output_bars: int = 32
    add_phrase_markers: bool = True
    phrase_every_bars: int = 8


@dataclass(frozen=True)
class Event:
    tick: int
    note: int
    velocity: int
    duration: int


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def read_tempo(mid: mido.MidiFile) -> int:
    for track in mid.tracks:
        for message in track:
            if message.type == "set_tempo":
                return message.tempo
    return 500_000


def read_events(mid: mido.MidiFile) -> tuple[list[Event], int]:
    absolute = 0
    events: list[Event] = []
    for message in mido.merge_tracks(mid.tracks):
        absolute += message.time
        if (
            message.type == "note_on"
            and message.velocity > 0
            and message.note in ALLOWED_NOTES
        ):
            events.append(Event(absolute, message.note, message.velocity, 30))
    return events, absolute


def quantize(
    events: Iterable[Event],
    ticks_per_beat: int,
    division: int,
) -> tuple[list[Event], int]:
    grid = max(1, round(ticks_per_beat / (division / 4)))
    strongest: dict[tuple[int, int], Event] = {}
    for event in events:
        tick = round(event.tick / grid) * grid
        candidate = Event(tick, event.note, event.velocity, max(1, grid // 3))
        key = (tick, event.note)
        if key not in strongest or candidate.velocity > strongest[key].velocity:
            strongest[key] = candidate
    return sorted(strongest.values(), key=lambda e: (e.tick, e.note)), grid


def fingerprint(
    events: Iterable[Event],
    start: int,
    length: int,
    grid: int,
) -> frozenset[tuple[int, int]]:
    return frozenset(
        ((event.tick - start) // grid, event.note)
        for event in events
        if start <= event.tick < start + length
    )


def jaccard_distance(left: frozenset, right: frozenset) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - len(left & right) / len(left | right)


def choose_representative_window(
    events: list[Event],
    total_ticks: int,
    ticks_per_beat: int,
    bars: int,
    grid: int,
) -> tuple[int, int]:
    bar_ticks = ticks_per_beat * 4
    length = bar_ticks * bars
    last_start = max(0, total_ticks - length)
    starts = list(range(0, last_start + 1, bar_ticks)) or [0]
    prints = {start: fingerprint(events, start, length, grid) for start in starts}
    starts = [start for start in starts if prints[start]] or [0]

    densities = sorted(len(prints[start]) for start in starts)
    median_density = densities[len(densities) // 2] if densities else 0

    def score(candidate: int) -> float:
        similarity_cost = sum(
            jaccard_distance(prints[candidate], prints[other])
            for other in starts
        ) / len(starts)
        density = len(prints[candidate])
        fill_penalty = max(0, density - median_density * 1.35) * 0.02
        intro_penalty = 0.03 if candidate == 0 and len(starts) > 2 else 0
        return similarity_cost + fill_penalty + intro_penalty

    return min(starts, key=score), length


def simplify(
    events: list[Event],
    start: int,
    length: int,
    ticks_per_beat: int,
    grid: int,
    complexity: float,
) -> list[Event]:
    relative = [
        Event(
            tick=e.tick - start,
            note=e.note,
            velocity=clamp(e.velocity, 45, 120),
            duration=e.duration,
        )
        for e in events
        if start <= e.tick < start + length
    ]

    kept: list[Event] = []
    for event in relative:
        sixteenth = event.tick // grid
        strong_eighth = sixteenth % 2 == 0
        strong_quarter = sixteenth % 4 == 0

        if event.note in {36, 38, 40}:
            if complexity >= 0.25 or strong_quarter:
                kept.append(event)
        elif event.note in {42, 46}:
            if complexity >= 0.45 or strong_eighth:
                kept.append(event)
        elif complexity >= 0.78:
            kept.append(event)

    by_key: dict[tuple[int, int], Event] = {}
    for event in kept:
        key = (event.tick, event.note)
        if key not in by_key or event.velocity > by_key[key].velocity:
            by_key[key] = event

    bar_ticks = ticks_per_beat * 4
    for bar_start in range(0, length, bar_ticks):
        defaults = (
            Event(bar_start, 36, 112, max(1, grid // 3)),
            Event(bar_start + ticks_per_beat, 40, 102, max(1, grid // 3)),
            Event(bar_start + 2 * ticks_per_beat, 36, 104, max(1, grid // 3)),
            Event(bar_start + 3 * ticks_per_beat, 40, 102, max(1, grid // 3)),
        )
        for event in defaults:
            by_key.setdefault((event.tick, event.note), event)

        hats_in_bar = sum(
            1 for event in by_key.values()
            if event.note in {42, 46}
            and bar_start <= event.tick < bar_start + bar_ticks
        )
        if hats_in_bar < 4:
            for offset in range(0, bar_ticks, ticks_per_beat // 2):
                event = Event(bar_start + offset, 42, 72, max(1, grid // 3))
                by_key.setdefault((event.tick, event.note), event)

    accented = []
    for event in by_key.values():
        velocity = event.velocity
        if event.tick % bar_ticks == 0:
            velocity = clamp(velocity + 10, 1, 127)
        accented.append(Event(event.tick, event.note, velocity, event.duration))

    return sorted(accented, key=lambda e: (e.tick, e.note))


def repeat_pattern(
    pattern: list[Event],
    pattern_ticks: int,
    output_ticks: int,
    ticks_per_beat: int,
    options: GrooveOptions,
) -> list[Event]:
    result: dict[tuple[int, int], Event] = {}
    start = 0
    while start < output_ticks:
        for event in pattern:
            tick = start + event.tick
            if tick < output_ticks:
                copied = Event(tick, event.note, event.velocity, event.duration)
                result[(tick, event.note)] = copied
        start += pattern_ticks

    if options.add_phrase_markers:
        phrase_ticks = ticks_per_beat * 4 * options.phrase_every_bars
        for tick in range(phrase_ticks, output_ticks, phrase_ticks):
            marker = Event(tick, 49, 92, max(1, ticks_per_beat // 6))
            result[(tick, marker.note)] = marker

    return sorted(result.values(), key=lambda e: (e.tick, e.note))


def write_midi(
    events: list[Event],
    output_path: Path,
    ticks_per_beat: int,
    tempo: int,
) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="RD-8 Groove", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    timeline: list[tuple[int, int, mido.Message]] = []
    for event in events:
        timeline.append((
            event.tick,
            1,
            mido.Message(
                "note_on", channel=9, note=event.note,
                velocity=event.velocity, time=0,
            ),
        ))
        timeline.append((
            event.tick + event.duration,
            0,
            mido.Message(
                "note_off", channel=9, note=event.note,
                velocity=0, time=0,
            ),
        ))

    timeline.sort(key=lambda row: (row[0], row[1]))
    previous_tick = 0
    for tick, _, message in timeline:
        message.time = max(0, tick - previous_tick)
        track.append(message)
        previous_tick = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(output_path)


def create_groove_midi(
    source_midi_path: str | Path,
    output_midi_path: str | Path,
    options: GrooveOptions | None = None,
) -> dict:
    options = options or GrooveOptions()
    source = Path(source_midi_path)
    output = Path(output_midi_path)

    mid = mido.MidiFile(source)
    tempo = read_tempo(mid)
    raw_events, total_ticks = read_events(mid)
    if not raw_events:
        raise RuntimeError("The transcription MIDI contains no recognized drum notes.")

    events, grid = quantize(raw_events, mid.ticks_per_beat, options.quantize_division)
    start, pattern_ticks = choose_representative_window(
        events, total_ticks, mid.ticks_per_beat, options.bars, grid
    )
    pattern = simplify(
        events, start, pattern_ticks, mid.ticks_per_beat, grid, options.complexity
    )
    output_ticks = mid.ticks_per_beat * 4 * options.output_bars
    repeated = repeat_pattern(
        pattern, pattern_ticks, output_ticks, mid.ticks_per_beat, options
    )
    write_midi(repeated, output, mid.ticks_per_beat, tempo)

    return {
        "mode": "groove",
        "bpm": round(mido.tempo2bpm(tempo), 2),
        "groove_bars": options.bars,
        "output_bars": options.output_bars,
        "complexity": options.complexity,
        "phrase_markers": options.add_phrase_markers,
        "phrase_every_bars": options.phrase_every_bars,
        "source_window_start_seconds": round(
            mido.tick2second(start, mid.ticks_per_beat, tempo), 3
        ),
        "pattern_hits": len(pattern),
        "output_hits": len(repeated),
    }

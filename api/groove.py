from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import mido

ALLOWED = {36, 40, 42, 45, 46, 47, 49, 50, 51}


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


def read_tempo(mid):
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return msg.tempo
    return 500000


def read_events(mid):
    absolute = 0
    events = []
    for msg in mido.merge_tracks(mid.tracks):
        absolute += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and msg.note in ALLOWED:
            events.append(Event(absolute, msg.note, msg.velocity, 30))
    return events, absolute


def quantize(events, tpq, division):
    grid = max(1, round(tpq / (division / 4)))
    result = {}
    for e in events:
        tick = round(e.tick / grid) * grid
        q = Event(tick, e.note, e.velocity, max(1, grid // 3))
        key = (tick, e.note)
        if key not in result or q.velocity > result[key].velocity:
            result[key] = q
    return sorted(result.values(), key=lambda x: (x.tick, x.note)), grid


def fp(events, start, length, grid):
    return frozenset(
        ((e.tick - start) // grid, e.note)
        for e in events if start <= e.tick < start + length
    )


def distance(a, b):
    return 0 if not a and not b else 1 - len(a & b) / len(a | b)


def choose_window(events, total, tpq, bars, grid):
    bar = tpq * 4
    length = bar * bars
    starts = list(range(0, max(0, total - length) + 1, bar)) or [0]
    prints = {s: fp(events, s, length, grid) for s in starts}
    starts = [s for s in starts if prints[s]] or [0]
    densities = sorted(len(prints[s]) for s in starts)
    median = densities[len(densities)//2] if densities else 0

    def score(s):
        mean_distance = sum(distance(prints[s], prints[o]) for o in starts) / len(starts)
        fill_penalty = max(0, len(prints[s]) - median * 1.35) * .02
        return mean_distance + fill_penalty

    return min(starts, key=score), length


def simplify(events, start, length, tpq, grid, complexity):
    selected = {}
    for e in events:
        if not start <= e.tick < start + length:
            continue
        rel = Event(e.tick-start, e.note, max(45, min(120, e.velocity)), e.duration)
        step = rel.tick // grid
        keep = (
            rel.note in {36, 40} and (complexity >= .25 or step % 4 == 0)
            or rel.note in {42, 46} and (complexity >= .45 or step % 2 == 0)
            or rel.note in {45, 47, 49, 50, 51} and complexity >= .78
        )
        if keep:
            key = (rel.tick, rel.note)
            if key not in selected or rel.velocity > selected[key].velocity:
                selected[key] = rel

    bar = tpq * 4
    for b in range(0, length, bar):
        defaults = [
            Event(b, 36, 115, grid//3),
            Event(b+tpq, 40, 103, grid//3),
            Event(b+2*tpq, 36, 105, grid//3),
            Event(b+3*tpq, 40, 103, grid//3),
        ]
        for e in defaults:
            selected.setdefault((e.tick, e.note), e)
        hats = sum(
            1 for e in selected.values()
            if e.note in {42,46} and b <= e.tick < b+bar
        )
        if hats < 4:
            for offset in range(0, bar, max(1, tpq//2)):
                e = Event(b+offset, 42, 72, grid//3)
                selected.setdefault((e.tick, e.note), e)

    return sorted(selected.values(), key=lambda e: (e.tick, e.note))


def repeat(pattern, pattern_ticks, output_ticks, tpq, options):
    result = {}
    start = 0
    while start < output_ticks:
        for e in pattern:
            tick = start + e.tick
            if tick < output_ticks:
                result[(tick,e.note)] = Event(tick,e.note,e.velocity,e.duration)
        start += pattern_ticks
    if options.add_phrase_markers:
        every = tpq * 4 * options.phrase_every_bars
        for tick in range(every, output_ticks, every):
            result[(tick,49)] = Event(tick,49,92,max(1,tpq//6))
    return sorted(result.values(), key=lambda e:(e.tick,e.note))


def write(events, path, tpq, tempo):
    mid = mido.MidiFile(type=1, ticks_per_beat=tpq)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="OaF Groove", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    timeline = []
    for e in events:
        timeline.append((e.tick,1,mido.Message("note_on",channel=9,note=e.note,velocity=e.velocity,time=0)))
        timeline.append((e.tick+e.duration,0,mido.Message("note_off",channel=9,note=e.note,velocity=0,time=0)))
    timeline.sort(key=lambda x:(x[0],x[1]))
    previous = 0
    for tick,_,msg in timeline:
        msg.time = max(0,tick-previous)
        track.append(msg)
        previous = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(path)


def create_groove_midi(source_midi_path, output_midi_path, options=None):
    options = options or GrooveOptions()
    mid = mido.MidiFile(source_midi_path)
    tempo = read_tempo(mid)
    raw,total = read_events(mid)
    if not raw:
        raise RuntimeError("OaF MIDI contained no recognized RD-8 drum hits.")
    events,grid = quantize(raw,mid.ticks_per_beat,options.quantize_division)
    start,length = choose_window(events,total,mid.ticks_per_beat,options.bars,grid)
    pattern = simplify(events,start,length,mid.ticks_per_beat,grid,options.complexity)
    output_ticks = mid.ticks_per_beat*4*options.output_bars
    generated = repeat(pattern,length,output_ticks,mid.ticks_per_beat,options)
    write(generated,output_midi_path,mid.ticks_per_beat,tempo)
    return {
        "mode":"groove",
        "bpm":round(mido.tempo2bpm(tempo),2),
        "groove_bars":options.bars,
        "output_bars":options.output_bars,
        "complexity":options.complexity,
        "source_window_start_seconds":round(
            mido.tick2second(start,mid.ticks_per_beat,tempo),3
        ),
        "pattern_hits":len(pattern),
        "output_hits":len(generated),
    }

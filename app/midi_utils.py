from __future__ import annotations
from pathlib import Path
import math
import pretty_midi
from .models import DrumEvent

# ADTOF five-class General MIDI output -> RD-8-friendly voices.
# Common ADTOF output notes are kick 36, snare 38, closed hat 42, tom 47, cymbal 49.
RD8_NOTES = {
    "kick": 36,
    "snare": 40,
    "closed_hat": 42,
    "open_hat": 46,
    "low_tom": 45,
    "mid_tom": 47,
    "high_tom": 50,
    "cymbal": 51,
}

GM_TO_DRUM = {
    35: "kick", 36: "kick",
    37: "snare", 38: "snare", 39: "snare", 40: "snare",
    42: "closed_hat", 44: "closed_hat",
    46: "open_hat",
    41: "low_tom", 43: "low_tom", 45: "low_tom",
    47: "mid_tom", 48: "mid_tom",
    50: "high_tom",
    49: "cymbal", 51: "cymbal", 52: "cymbal", 53: "cymbal", 55: "cymbal", 57: "cymbal", 59: "cymbal",
}

def midi_to_events(path: Path) -> list[DrumEvent]:
    midi = pretty_midi.PrettyMIDI(str(path))
    events: list[DrumEvent] = []
    for instrument in midi.instruments:
        for note in instrument.notes:
            drum = GM_TO_DRUM.get(note.pitch)
            if not drum:
                continue
            # ADTOF has one tom class. Keep mid tom as the neutral default.
            if drum in {"low_tom", "high_tom"}:
                drum = "mid_tom"
            events.append(DrumEvent(
                time=round(float(note.start), 5),
                drum=drum,
                note=RD8_NOTES[drum],
                velocity=max(1, min(127, int(note.velocity))),
                duration=max(0.02, min(0.25, float(note.end - note.start))),
            ))
    return sorted(events, key=lambda e: (e.time, e.note))

def events_to_midi(events: list[DrumEvent], output: Path, bpm: float = 120.0, midi_channel: int = 10) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    # pretty_midi chooses channel 10 automatically for is_drum=True.
    instrument = pretty_midi.Instrument(program=0, is_drum=True, name=f"RD-8 drums (requested channel {midi_channel})")
    for event in sorted(events, key=lambda e: e.time):
        instrument.notes.append(pretty_midi.Note(
            velocity=event.velocity,
            pitch=event.note,
            start=event.time,
            end=event.time + event.duration,
        ))
    pm.instruments.append(instrument)
    pm.write(str(output))

def quantize_events(events: list[DrumEvent], bpm: float, subdivision: int, strength: float) -> list[DrumEvent]:
    step = 60.0 / bpm * (4.0 / subdivision)
    result: list[DrumEvent] = []
    for event in events:
        target = round(event.time / step) * step
        new_time = event.time + (target - event.time) * strength
        result.append(event.model_copy(update={"time": round(max(0.0, new_time), 5)}))
    return sorted(result, key=lambda e: (e.time, e.note))

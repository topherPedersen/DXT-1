from __future__ import annotations

import csv
import random
from pathlib import Path

import mido
import torch
from torch.utils.data import Dataset

from training.config import TrainConfig
from training.features import LogMelExtractor, load_audio
from training.mapping import PITCH_TO_CLASS


def midi_onsets_seconds(path: Path) -> list[tuple[float, int, int]]:
    mid = mido.MidiFile(path)
    tempo = 500000
    absolute_ticks = 0
    events = []

    for message in mido.merge_tracks(mid.tracks):
        absolute_ticks += message.time
        if message.type == "set_tempo":
            tempo = message.tempo
        elif message.type == "note_on" and message.velocity > 0:
            class_index = PITCH_TO_CLASS.get(message.note)
            if class_index is not None:
                seconds = mido.tick2second(
                    absolute_ticks, mid.ticks_per_beat, tempo
                )
                events.append((seconds, class_index, message.velocity))
    return events


class GrooveDataset(Dataset):
    def __init__(
        self,
        root: str | Path,
        split: str,
        config: TrainConfig,
        training: bool,
    ):
        self.root = Path(root)
        self.config = config
        self.training = training
        self.extractor = LogMelExtractor(config)

        csv_candidates = [
            self.root / "info.csv",
            self.root / "groove-v1.0.0.csv",
            self.root / "e-gmd-v1.0.0.csv",
        ]
        csv_path = next((p for p in csv_candidates if p.exists()), None)
        if csv_path is None:
            candidates = list(self.root.glob("*.csv"))
            if len(candidates) == 1:
                csv_path = candidates[0]
            else:
                raise FileNotFoundError(
                    f"Could not locate dataset CSV under {self.root}"
                )

        rows = []
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("split") != split:
                    continue
                audio = self.root / row["audio_filename"]
                midi = self.root / row["midi_filename"]
                if audio.exists() and midi.exists():
                    rows.append((audio, midi))
        if not rows:
            raise RuntimeError(f"No usable {split} rows found in {csv_path}")
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        audio_path, midi_path = self.rows[index]
        waveform = load_audio(audio_path, self.config.sample_rate)
        segment_samples = int(
            self.config.sample_rate * self.config.segment_seconds
        )

        if len(waveform) <= segment_samples:
            waveform = torch.nn.functional.pad(
                waveform, (0, segment_samples - len(waveform))
            )
            start_sample = 0
        else:
            if self.training:
                start_sample = random.randint(
                    0, len(waveform) - segment_samples
                )
            else:
                start_sample = max(0, (len(waveform) - segment_samples) // 2)
            waveform = waveform[start_sample:start_sample + segment_samples]

        if self.training:
            gain = 10 ** random.uniform(-4, 3) / 20
            waveform = (waveform * gain).clamp(-1, 1)
            if random.random() < 0.35:
                waveform = waveform + torch.randn_like(waveform) * random.uniform(
                    0.0003, 0.004
                )

        features = self.extractor(waveform.unsqueeze(0)).squeeze(0)
        frames = features.shape[-1]
        targets = torch.zeros(frames, 5)
        velocities = torch.zeros(frames, 5)

        start_seconds = start_sample / self.config.sample_rate
        end_seconds = start_seconds + self.config.segment_seconds
        for seconds, class_index, velocity in midi_onsets_seconds(midi_path):
            if start_seconds <= seconds < end_seconds:
                local = seconds - start_seconds
                frame = round(
                    local * self.config.sample_rate / self.config.hop_length
                )
                for offset in range(
                    -self.config.onset_width_frames,
                    self.config.onset_width_frames + 1,
                ):
                    target_frame = frame + offset
                    if 0 <= target_frame < frames:
                        weight = 1.0 - abs(offset) / (
                            self.config.onset_width_frames + 1
                        )
                        targets[target_frame, class_index] = max(
                            targets[target_frame, class_index], weight
                        )
                        velocities[target_frame, class_index] = max(
                            velocities[target_frame, class_index],
                            velocity / 127.0,
                        )

        return features, targets, velocities

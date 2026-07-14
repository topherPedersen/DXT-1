from __future__ import annotations

from pathlib import Path

import mido
import numpy as np
import torch

from training.config import TrainConfig
from training.features import LogMelExtractor, load_audio
from training.mapping import CLASS_NAMES, CLASS_TO_RD8_NOTE
from training.model import RD8DrumCRNN


class CustomDrumTranscriber:
    def __init__(self, checkpoint_path: str | Path):
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                "No trained model found. Run train.command first: "
                f"{self.checkpoint_path}"
            )

        self.device = self._device()
        checkpoint = torch.load(
            self.checkpoint_path,
            map_location=self.device,
            weights_only=False,
        )
        self.config = TrainConfig(**checkpoint["config"])
        self.thresholds = checkpoint["thresholds"]
        self.model = RD8DrumCRNN(
            self.config.n_mels, len(checkpoint["class_names"])
        ).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()
        self.extractor = LogMelExtractor(self.config).to(self.device)

    @staticmethod
    def _device():
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def transcribe(self, audio_path: str | Path, midi_path: str | Path) -> dict:
        waveform = load_audio(audio_path, self.config.sample_rate)
        # Inference windows overlap to reduce boundary misses.
        segment_samples = int(
            self.config.sample_rate * self.config.segment_seconds
        )
        overlap_samples = segment_samples // 4
        step = segment_samples - overlap_samples

        all_hits = []
        for start in range(0, max(1, len(waveform)), step):
            segment = waveform[start:start + segment_samples]
            if len(segment) < segment_samples:
                segment = torch.nn.functional.pad(
                    segment, (0, segment_samples - len(segment))
                )
            with torch.no_grad():
                features = self.extractor(
                    segment.unsqueeze(0).to(self.device)
                )
                probabilities = torch.sigmoid(
                    self.model(features)
                ).squeeze(0).cpu().numpy()

            offset_seconds = start / self.config.sample_rate
            all_hits.extend(self._peaks(probabilities, offset_seconds))
            if start + segment_samples >= len(waveform):
                break

        hits = self._deduplicate(all_hits)
        self._write_midi(hits, midi_path)
        return {
            "engine": "Custom RD-8 PyTorch CRNN",
            "device": self.device,
            "hits": len(hits),
            "classes": CLASS_NAMES,
        }

    def _peaks(self, probabilities: np.ndarray, offset_seconds: float):
        hits = []
        frame_seconds = self.config.hop_length / self.config.sample_rate
        minimum_gap = {
            0: 0.075,
            1: 0.075,
            2: 0.045,
            3: 0.080,
            4: 0.100,
        }

        for class_index, class_name in enumerate(CLASS_NAMES):
            values = probabilities[:, class_index]
            threshold = self.thresholds[class_name]
            candidates = []
            for frame in range(1, len(values) - 1):
                if (
                    values[frame] >= threshold
                    and values[frame] >= values[frame - 1]
                    and values[frame] > values[frame + 1]
                ):
                    candidates.append((
                        offset_seconds + frame * frame_seconds,
                        class_index,
                        float(values[frame]),
                    ))

            last_time = -999.0
            for hit in candidates:
                if hit[0] - last_time >= minimum_gap[class_index]:
                    hits.append(hit)
                    last_time = hit[0]
                elif hits and hit[2] > hits[-1][2]:
                    hits[-1] = hit
                    last_time = hit[0]
        return hits

    @staticmethod
    def _deduplicate(hits):
        hits = sorted(hits)
        result = []
        for hit in hits:
            if (
                result
                and hit[1] == result[-1][1]
                and abs(hit[0] - result[-1][0]) < 0.035
            ):
                if hit[2] > result[-1][2]:
                    result[-1] = hit
            else:
                result.append(hit)
        return result

    @staticmethod
    def _write_midi(hits, path):
        ticks_per_beat = 480
        tempo = 500000
        mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        track.append(mido.MetaMessage(
            "track_name", name="Custom RD-8 Transcription", time=0
        ))

        timeline = []
        for seconds, class_index, confidence in hits:
            tick = round(
                mido.second2tick(seconds, ticks_per_beat, tempo)
            )
            note = CLASS_TO_RD8_NOTE[class_index]
            velocity = max(55, min(127, round(55 + confidence * 72)))
            timeline.append((tick, 1, mido.Message(
                "note_on", channel=9, note=note, velocity=velocity, time=0
            )))
            timeline.append((tick + 30, 0, mido.Message(
                "note_off", channel=9, note=note, velocity=0, time=0
            )))

        timeline.sort(key=lambda row: (row[0], row[1]))
        previous = 0
        for tick, _, message in timeline:
            message.time = max(0, tick - previous)
            track.append(message)
            previous = tick
        mid.save(path)

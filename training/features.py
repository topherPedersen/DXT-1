from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio

from training.config import TrainConfig


class LogMelExtractor(torch.nn.Module):
    def __init__(self, config: TrainConfig):
        super().__init__()
        self.config = config
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=config.sample_rate,
            n_fft=config.n_fft,
            win_length=config.n_fft,
            hop_length=config.hop_length,
            f_min=config.f_min,
            f_max=config.f_max,
            n_mels=config.n_mels,
            power=2.0,
            normalized=False,
            center=True,
        )

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        # waveform: [batch, samples]
        power = self.mel(waveform)
        log_mel = torch.log1p(power)
        mean = log_mel.mean(dim=(-2, -1), keepdim=True)
        std = log_mel.std(dim=(-2, -1), keepdim=True).clamp_min(1e-5)
        return (log_mel - mean) / std


def load_audio(path, sample_rate: int) -> torch.Tensor:
    """
    Load GMD WAV files with libsndfile instead of torchaudio.load/TorchCodec.

    The Groove MIDI Dataset contains ordinary WAV files. Reading them through
    soundfile avoids TorchCodec's FFmpeg decoder path, which can fail on an
    otherwise valid file with "Invalid data found when processing input".
    """
    path = Path(path)

    if not path.is_file():
        raise RuntimeError(f"Audio path is not a file: {path}")

    try:
        audio, source_rate = sf.read(
            str(path),
            dtype="float32",
            always_2d=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode dataset audio file with soundfile: {path}\n"
            f"Original decoder error: {exc}"
        ) from exc

    if audio.size == 0:
        raise RuntimeError(f"Dataset audio file is empty: {path}")

    # soundfile returns [samples, channels]. Convert to mono.
    mono = np.mean(audio, axis=1, dtype=np.float32)
    waveform = torch.from_numpy(np.ascontiguousarray(mono))

    if int(source_rate) != sample_rate:
        waveform = torchaudio.functional.resample(
            waveform,
            int(source_rate),
            sample_rate,
        )

    return waveform

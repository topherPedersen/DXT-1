from __future__ import annotations

import numpy as np
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
    waveform, source_rate = torchaudio.load(str(path))
    waveform = waveform.mean(dim=0)
    if source_rate != sample_rate:
        waveform = torchaudio.functional.resample(
            waveform, source_rate, sample_rate
        )
    return waveform

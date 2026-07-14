from __future__ import annotations

import torch
from torch import nn


class RD8DrumCRNN(nn.Module):
    def __init__(self, n_mels: int = 96, classes: int = 5):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.GELU(),
            nn.MaxPool2d((2, 1)),
            nn.Dropout(0.1),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.GELU(),
            nn.MaxPool2d((2, 1)),
            nn.Dropout(0.15),

            nn.Conv2d(64, 96, kernel_size=3, padding=1),
            nn.BatchNorm2d(96),
            nn.GELU(),
            nn.MaxPool2d((2, 1)),
            nn.Dropout(0.2),
        )

        reduced_mels = n_mels // 8
        self.gru = nn.GRU(
            input_size=96 * reduced_mels,
            hidden_size=128,
            num_layers=2,
            batch_first=True,
            bidirectional=True,
            dropout=0.2,
        )
        self.head = nn.Sequential(
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(128, classes),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        # [B, mel, time] -> [B, 1, mel, time]
        x = self.conv(features.unsqueeze(1))
        # [B, channels, reduced_mel, time] -> [B, time, features]
        x = x.permute(0, 3, 1, 2).contiguous()
        x = x.flatten(start_dim=2)
        x, _ = self.gru(x)
        return self.head(x)

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainConfig:
    sample_rate: int = 22050
    n_fft: int = 1024
    hop_length: int = 220
    n_mels: int = 96
    f_min: float = 30.0
    f_max: float = 11000.0
    segment_seconds: float = 8.0
    onset_width_frames: int = 2
    batch_size: int = 8
    epochs: int = 12
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    num_workers: int = 0
    seed: int = 42

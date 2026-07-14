from typing import Literal
from pydantic import BaseModel, Field

DrumName = Literal["kick", "snare", "closed_hat", "open_hat", "low_tom", "mid_tom", "high_tom", "cymbal"]

class DrumEvent(BaseModel):
    time: float = Field(ge=0)
    drum: DrumName
    note: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    duration: float = Field(default=0.05, gt=0, le=2)

class ExportRequest(BaseModel):
    events: list[DrumEvent]
    bpm: float = Field(default=120, gt=20, le=400)
    midi_channel: int = Field(default=10, ge=1, le=16)
    filename: str = "rd8-drums.mid"

class QuantizeRequest(BaseModel):
    events: list[DrumEvent]
    bpm: float = Field(default=120, gt=20, le=400)
    subdivision: Literal[4, 8, 16, 32] = 16
    strength: float = Field(default=1.0, ge=0, le=1)

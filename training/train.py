from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import average_precision_score
from torch.utils.data import DataLoader
from tqdm import tqdm

from training.config import TrainConfig
from training.dataset import GrooveDataset
from training.mapping import CLASS_NAMES
from training.model import RD8DrumCRNN


def device_name():
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def evaluate(model, loader, device):
    model.eval()
    probabilities, targets = [], []
    total_loss = 0.0
    loss_fn = torch.nn.BCEWithLogitsLoss()

    with torch.no_grad():
        for features, target, _ in loader:
            features, target = features.to(device), target.to(device)
            logits = model(features)
            loss = loss_fn(logits, target)
            total_loss += loss.item()
            probabilities.append(torch.sigmoid(logits).cpu().numpy())
            targets.append(target.cpu().numpy())

    y_score = np.concatenate(probabilities).reshape(-1, 5)
    y_true = np.concatenate(targets).reshape(-1, 5)
    aps = {}
    for index, name in enumerate(CLASS_NAMES):
        aps[name] = float(
            average_precision_score(
                (y_true[:, index] >= 0.5).astype(np.int32),
                y_score[:, index],
            )
        )
    return total_loss / max(1, len(loader)), aps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = TrainConfig()
    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)

    device = device_name()
    print(f"Training on {device}")

    train_set = GrooveDataset(
        args.dataset_root, "train", config, training=True
    )
    validation_set = GrooveDataset(
        args.dataset_root, "validation", config, training=False
    )
    train_loader = DataLoader(
        train_set,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
    )
    validation_loader = DataLoader(
        validation_set,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=config.num_workers,
    )

    model = RD8DrumCRNN(config.n_mels, len(CLASS_NAMES)).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    onset_loss = torch.nn.BCEWithLogitsLoss(pos_weight=torch.full((5,), 8.0).to(device))
    velocity_loss = torch.nn.SmoothL1Loss(reduction="none")

    best_map = -1.0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, config.epochs + 1):
        model.train()
        running = 0.0
        bar = tqdm(train_loader, desc=f"epoch {epoch}/{config.epochs}")

        for features, targets, velocities in bar:
            features = features.to(device)
            targets = targets.to(device)
            velocities = velocities.to(device)

            optimizer.zero_grad(set_to_none=True)
            logits = model(features)
            loss = onset_loss(logits, targets)

            # The first prototype uses onset probabilities as a velocity proxy.
            # Keep velocity labels in the data path for the next two-head model.
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 3.0)
            optimizer.step()

            running += loss.item()
            bar.set_postfix(loss=f"{loss.item():.4f}")

        validation_loss, aps = evaluate(model, validation_loader, device)
        mean_ap = sum(aps.values()) / len(aps)
        print(
            json.dumps({
                "epoch": epoch,
                "train_loss": running / max(1, len(train_loader)),
                "validation_loss": validation_loss,
                "mean_average_precision": mean_ap,
                "per_class_ap": aps,
            }, indent=2)
        )

        if mean_ap > best_map:
            best_map = mean_ap
            torch.save({
                "model_state": model.state_dict(),
                "config": asdict(config),
                "class_names": CLASS_NAMES,
                "thresholds": {
                    "kick": 0.55,
                    "snare": 0.55,
                    "hihat": 0.48,
                    "tom": 0.58,
                    "cymbal": 0.58,
                },
                "validation_map": mean_ap,
            }, output)
            print(f"Saved best model to {output}")


if __name__ == "__main__":
    main()

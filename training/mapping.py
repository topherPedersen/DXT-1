CLASS_NAMES = ["kick", "snare", "hihat", "tom", "cymbal"]

# GMD/GM-compatible grouping.
PITCH_TO_CLASS = {
    35: 0, 36: 0,
    37: 1, 38: 1, 39: 1, 40: 1,
    42: 2, 44: 2, 46: 2,
    41: 3, 43: 3, 45: 3, 47: 3, 48: 3, 50: 3,
    49: 4, 51: 4, 52: 4, 53: 4, 55: 4, 57: 4, 59: 4,
}

CLASS_TO_RD8_NOTE = {
    0: 36,
    1: 40,
    2: 42,
    3: 45,
    4: 49,
}

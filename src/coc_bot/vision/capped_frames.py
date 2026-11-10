"""Small, game-agnostic checks for the measured 178-level capture cap."""
from __future__ import annotations

import cv2
import numpy as np


def has_exact_cap_178(frame: np.ndarray) -> bool:
    """Require the measured all-channel ceiling in the game viewport."""
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3):
        return False
    h, w = frame.shape[:2]
    if h <= 0 or w <= 0 or not 1.6 < w / h < 1.95:
        return False
    viewport = frame[:max(1, round(h * .94))]
    return (np.array_equal(viewport.reshape(-1, 3).max(axis=0),
                           np.full(3, 178, np.uint8))
            and np.percentile(cv2.cvtColor(viewport, cv2.COLOR_BGR2GRAY), 99.9) >= 170)


def restore_cap_178(frame: np.ndarray) -> np.ndarray:
    """Apply the measured coordinate-preserving gain without mutating source."""
    return cv2.convertScaleAbs(frame, alpha=255.0 / 178.0)

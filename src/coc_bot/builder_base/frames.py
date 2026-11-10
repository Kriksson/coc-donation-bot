"""Builder-only correction for the verified 178-level native rendering cap.

Home Village and shared ADB consumers keep the original pixels. This module
only adapts frames owned by Builder Base runners after both the cap and a
native Builder screen signature have been verified.
"""
from __future__ import annotations

import cv2
import numpy as np

from coc_bot.builder_base.vision import ASSETS
from coc_bot.upgrades.vision import crop
from coc_bot.vision.home_frames import normalize_home_frame

_CAP = 178
_GAIN = 255.0 / _CAP
_SCALES = (.96, 1.0, 1.04)
_TEMPLATES: dict[str, np.ndarray | None] = {}


def _score(frame: np.ndarray, name: str, box: tuple[float, float, float, float]) -> float:
    """Best native template score in the measured Builder scale range."""
    if name not in _TEMPLATES:
        _TEMPLATES[name] = cv2.imread(str(ASSETS / (name + '.png')))
    template = _TEMPLATES[name]
    if template is None:
        return 0.0
    h, w = frame.shape[:2]
    region = crop(frame, box)
    best = 0.0
    for factor in _SCALES:
        scale = w / 1853 * factor
        reference = cv2.resize(template, None, fx=scale, fy=scale)
        if region.shape[0] < reference.shape[0] or region.shape[1] < reference.shape[1]:
            continue
        score = cv2.minMaxLoc(cv2.matchTemplate(region, reference, cv2.TM_CCOEFF_NORMED))[1]
        best = max(best, float(score))
    return best


def _builder_signature(frame: np.ndarray) -> bool:
    # Village HUD persists behind Builder menus and their dialogs. Both anchors
    # are required so Home Village resource screens cannot trigger the gain.
    if (_score(frame, 'builder_gold', (.94, 0, 1, .09)) >= .90
            and _score(frame, 'builder_axes', (0, .80, .13, .98)) >= .90):
        return True

    # The village HUD is replaced during an attack. Require all three native
    # battle labels before normalizing a battlefield frame.
    if (_score(frame, 'defender', (.045, .012, .145, .06)) >= .88
            and _score(frame, 'attacker', (.875, .012, .97, .06)) >= .88
            and max(_score(frame, 'battle_starts', (.43, .012, .57, .055)),
                    _score(frame, 'battle_ends', (.43, .012, .57, .055))) >= .88):
        return True

    # A completed raid has no battle timer or village HUD. Its independent
    # result heading and Return Home button are the native Builder identity.
    if (_score(frame, 'result_heading', (.20, .05, .80, .60)) >= .88
            and _score(frame, 'return_home', (.25, .65, .75, 1)) >= .88):
        return True

    # A native Builder matchmaking menu has a distinctive title and Find Now
    # button; require both, not just a generic purchase-colored control.
    return (_score(frame, 'start_attack', (.38, .14, .66, .24)) >= .80
            and _score(frame, 'find_now', (.65, .60, .84, .72)) >= .90)


def normalize_builder_frame(frame: np.ndarray) -> np.ndarray:
    """Undo only the measured global cap on a positively identified Builder frame.

    The operation is coordinate preserving and does not mutate ``frame``.
    Frames with ordinary 8-bit whites, half-bright transitions, malformed
    shapes, or no native Builder signature are returned unchanged.
    """
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3):
        return frame
    h, w = frame.shape[:2]
    if h <= 0 or w <= 0:
        return frame
    if not 1.6 < w / h < 1.95:
        return frame
    # Android may draw a bright navigation strip below the game viewport. Cap
    # proof comes from the main 94% of the image; any OS dialog over the game
    # remains in this measured area and breaks the exact cap check.
    viewport = frame[:max(1, round(h * .94))]
    if not np.array_equal(viewport.reshape(-1, 3).max(axis=0), np.full(3, _CAP, np.uint8)):
        return frame
    if np.percentile(cv2.cvtColor(viewport, cv2.COLOR_BGR2GRAY), 99.9) < 170:
        return frame
    if not _builder_signature(frame):
        return frame
    return cv2.convertScaleAbs(frame, alpha=_GAIN)


class BuilderFrameCapture:
    """Capture proxy that preserves raw ADB evidence and returns normalized frames."""

    def __new__(cls, capture, navigator=None):
        if isinstance(capture, cls):
            return capture
        return super().__new__(cls)

    def __init__(self, capture, navigator=None):
        # Do not use hasattr: on a fresh proxy it calls __getattr__, which in
        # turn tries to read capture recursively before initialization.
        if 'capture' not in self.__dict__:
            self.capture = capture
            self.navigator = navigator
            self.last_raw_frame: np.ndarray | None = None
            self.last_frame: np.ndarray | None = None
            self.last_normalized = False
        elif self.navigator is None and navigator is not None:
            self.navigator = navigator

    def screenshot(self):
        raw = self.capture.screenshot()
        self.last_raw_frame = raw.copy() if isinstance(raw, np.ndarray) else raw
        home_frame = normalize_home_frame(raw, self.navigator)
        frame = home_frame if home_frame is not raw else normalize_builder_frame(raw)
        self.last_frame = frame
        self.last_normalized = frame is not raw
        return frame

    def raw_screenshot(self):
        """Take and return an unmodified source frame for evidence or diagnosis."""
        raw = self.capture.screenshot()
        self.last_raw_frame = raw.copy() if isinstance(raw, np.ndarray) else raw
        self.last_frame = raw
        self.last_normalized = False
        return raw

    def raw_for(self, frame):
        """Return the retained source only when ``frame`` is this last capture."""
        return self.last_raw_frame if frame is self.last_frame else None

    def was_normalized(self, frame):
        return bool(frame is self.last_frame and self.last_normalized)

    def __getattr__(self, name):
        return getattr(self.capture, name)

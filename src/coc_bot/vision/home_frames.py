"""Home-only normalization for positively identified capped Home captures."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from coc_bot.builder_base.vision import BuilderReader
from coc_bot.upgrades.vision import UpgradeReader, compact, crop
from coc_bot.vision.battle_menu import home_build_control_visible
from coc_bot.vision.capped_frames import has_exact_cap_178, restore_cap_178

ASSETS = Path(__file__).with_name('assets')
# The two icon templates are tight crops from the observed capped
# `tests/fixtures/progression/home-build-menu-capped.png` HUD.
_HUD_ANCHORS = {
    'gold': ((.68, .01, .73, .09), 'home_hud_gold.png'),
    'gems': ((.68, .22, .73, .31), 'home_hud_gem.png'),
}


@lru_cache(maxsize=2)
def _anchor(name):
    return cv2.imread(str(ASSETS / name))


def _bright_template(frame, template, bounds, *, threshold=.90, brightness=.66):
    """Match at the inspected scale range and require native anchor brightness."""
    if template is None:
        return False
    h, w = frame.shape[:2]
    region = crop(frame, bounds)
    for factor in (.96, 1.0, 1.04):
        scale = w / 1920 * factor
        reference = cv2.resize(template, None, fx=scale, fy=scale)
        rh, rw = reference.shape[:2]
        if region.shape[0] < rh or region.shape[1] < rw:
            continue
        scores = cv2.matchTemplate(region, reference, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        observed = region[y:y + rh, x:x + rw]
        if score >= threshold and float(observed.mean()) >= float(reference.mean()) * brightness:
            return True
    return False


def _home_menu_identity(frame):
    """Require Home menu title, red close, and both independent HUD icons."""
    # Builder keeps its own village HUD behind upgrade panels. Shared title and
    # resource icons must not convert its frames into Home frames.
    if BuilderReader().home(frame):
        return False
    h, w = frame.shape[:2]
    close = crop(frame, (.973, .008, .997, .055))
    hsv = cv2.cvtColor(close, cv2.COLOR_BGR2HSV)
    red = (cv2.inRange(hsv, (0, 100, 100), (10, 255, 255))
           | cv2.inRange(hsv, (170, 100, 100), (180, 255, 255)))
    if float(red.mean()) / 255 < .15:
        return False
    if not all(_bright_template(frame, _anchor(asset), bounds)
               for bounds, asset in _HUD_ANCHORS.values()):
        return False
    title = compact(UpgradeReader().label(frame, (.79, .012, .96, .05)))
    return title in ('buildingsheroes', 'buildingheroes')


def _home_filter_identity(frame):
    """Recognize the Home Build filter overlay independently of its dim HUD.

    The filter dialog intentionally dims the menu and resource HUD behind it,
    so the ordinary Home menu gate must fail. Require the exact cap, all three
    dialog headings, and the underlying Home Build menu title; selected-filter
    state is read separately by ProgressionReader before any control is used.
    """
    from coc_bot.progression.reader import ProgressionReader

    if BuilderReader().home(frame):
        return False
    # This modal is a large, centered brown panel. Use its cheap color geometry
    # to reject capped village, menu, and battle frames before running OCR.
    h, w = frame.shape[:2]
    panel = frame[round(h * .10):round(h * .74), round(w * .33):round(w * .80)]
    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
    brown = cv2.inRange(hsv, (5, 50, 50), (25, 255, 255))
    if float(brown.mean()) / 255 < .65:
        return False
    reader = ProgressionReader()
    if not reader.filters_open(frame):
        return False
    title = compact(UpgradeReader().label(frame, (.79, .012, .96, .05)))
    if title not in ('buildingsheroes', 'buildingheroes'):
        return False
    # Cost Min and Cost Max are non-payment sorting controls in the dialog.
    # Requiring both captions avoids treating an unrelated modal as a filter.
    cost_max = compact(reader.label(frame, (.36, .625, .48, .68)))
    cost_min = compact(reader.label(frame, (.50, .625, .62, .68)))
    # The selected yellow button changes OCR on this saved/live font from
    # `Cost Max` to `CostiMax`; allow that observed state so its brightness can
    # be normalized before selected_filter checks the yellow control.
    return cost_max in ('costmax', 'costimax') and cost_min == 'costmin'


def _home_village_identity(frame, navigator):
    """Require the existing Build and calibrated chat anchors, not HUD alone."""
    classifier = getattr(navigator, 'classifier', None)
    if not home_build_control_visible(frame) or classifier is None:
        return False
    if not classifier._open_chat_icon_visible(frame):
        return False
    # The calibrated template matcher is correlation-based. Re-check its matched
    # pixels against its source brightness so a dim background cannot pass merely
    # because an OS/modal foreground happens to reach the cap.
    template = classifier._load('open_chat')
    match = classifier.matcher.find(frame, template) if template is not None else None
    if match is None:
        return False
    observed = frame[match.y:match.y + match.height, match.x:match.x + match.width]
    expected = cv2.resize(template, (match.width, match.height))
    if float(observed.mean()) < float(expected.mean()) * .66:
        return False
    return not BuilderReader().home(frame)


def normalize_home_frame(frame, navigator=None):
    """Normalize only exact-cap frames carrying an independent Home identity."""
    if not has_exact_cap_178(frame):
        return frame
    if (_home_menu_identity(frame) or _home_filter_identity(frame)
            or _home_village_identity(frame, navigator)):
        return restore_cap_178(frame)
    return frame


class HomeFrameCapture:
    """Idempotent capture proxy; unknown and non-Home frames remain untouched."""
    def __new__(cls, capture, navigator=None):
        if isinstance(capture, cls):
            return capture
        return super().__new__(cls)

    def __init__(self, capture, navigator=None):
        if 'capture' not in self.__dict__:
            self.capture = capture
            self.navigator = navigator
            self.last_raw_frame = None
            self.last_frame = None
            self.last_normalized = False
        elif self.navigator is None and navigator is not None:
            self.navigator = navigator

    def screenshot(self):
        raw = self.capture.screenshot()
        self.last_raw_frame = raw.copy() if isinstance(raw, np.ndarray) else raw
        frame = normalize_home_frame(raw, self.navigator)
        self.last_frame = frame
        self.last_normalized = frame is not raw
        return frame

    def raw_for(self, frame):
        return self.last_raw_frame if frame is self.last_frame else None

    def was_normalized(self, frame):
        return bool(frame is self.last_frame and self.last_normalized)

    def __getattr__(self, name):
        return getattr(self.capture, name)


def home_capture(capture, navigator=None):
    """Keep Builder's evidence-aware proxy outermost when already installed."""
    # Local import keeps this Home adapter out of Builder's import graph.
    from coc_bot.builder_base.frames import BuilderFrameCapture
    if isinstance(capture, BuilderFrameCapture):
        if capture.navigator is None and navigator is not None:
            capture.navigator = navigator
        return capture
    return HomeFrameCapture(capture, navigator)

"""Opt-in end of a positively starred unranked battle."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from loguru import logger

from coc_bot.attack.recovery import AttackCheckpoint
from coc_bot.vision.battle_menu import _white_label, active_battle_ready
from coc_bot.vision.matcher import TemplateMatcher


@lru_cache(maxsize=4)
def _reference(name):
    assets = Path(__file__).resolve().parents[1] / 'vision' / 'assets'
    return cv2.imread(str(assets / (name + '.png')))


def star_template():
    frame = _reference('earned_battle_star')
    return _star_mask(frame) if frame is not None else None


def _star_mask(image):
    return ((image.min(axis=2) >= 160) & (np.ptp(image, axis=2) < 70)).astype(np.uint8) * 255


def _color_fraction(frame, region, low, high):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    crop = frame[round(h*y0):round(h*y1), round(w*x0):round(w*x1)]
    if not crop.size:
        return 0.
    return cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), low, high).mean() / 255


def starred_end_button(frame, stop=None):
    h, w = frame.shape[:2]
    template = star_template()
    if template is None:
        return None
    matcher = TemplateMatcher(scale_range=[w/1853 * s for s in (.95, 1., 1.05)])
    # Check the first star position and the native combat headings separately.
    x0, y0, x1, y1 = round(w*.828), round(h*.727), round(w*.869), round(h*.789)
    star = matcher.find(_star_mask(frame[y0:y1,x0:x1]), template, threshold=.93)
    if star is None or not active_battle_ready(frame, stop_check=stop):
        return None
    x, y = star.center
    x, y = x+x0, y+y0
    if frame[y-4:y+5, x-4:x+5].min(axis=2).mean() < 175:
        return None
    if _white_label(frame, (.015,.715,.13,.775), stop) not in ('endbattle','endbattie'):
        return None
    return round(w*.075), round(h*.745)


def finish_confirmation(frame, stop=None):
    """Require End Battle plus both labeled buttons on its modal."""
    if stop and stop():
        return None
    if _color_fraction(frame, (.31,.53,.49,.71), (5,90,90), (32,255,255)) < .20:
        return None
    if _color_fraction(frame, (.53,.55,.67,.69), (34,80,90), (92,255,255)) < .30:
        return None
    scale = frame.shape[1]/1853
    matcher = TemplateMatcher(scale_range=[scale*s for s in (.98,1.,1.02)])
    for name, region in (('star_end_title', (.39,.27,.62,.35)),
                         ('star_end_cancel', (.32,.59,.45,.69)),
                         ('star_end_okay', (.55,.59,.66,.69))):
        template = _reference(name)
        result = matcher.find_in_roi(frame, template, region, threshold=.96) if template is not None else None
        if result is None:
            return None
    return result.center


def finish_star_battle(nav, frame, target):
    checkpoint = AttackCheckpoint(nav.config)
    state = checkpoint.load()
    if (not state or state.get('phase') != 'deployment_finished' or not state.get('deployment_possible')
            or not state.get('journal') or state.get('star_end_intent') or nav._stopping()):
        return
    checkpoint.update(star_end_intent=True)
    nav._save_battle_end_frame(frame, 'earned-star')
    nav.input.tap(*target, jitter=0)
    logger.info('Verified star: tapped End Battle once')
    previous = None
    for _ in range(5):
        if nav._sleep(.5):
            return
        current = nav.capture.observe(timeout_seconds=3, stop_check=nav.stop_check)
        if current is None or nav._stopping():
            return
        if nav.battle_completion.detect(current) is not None:
            return  # The normal results watcher handles Return Home.
        nav._save_battle_end_frame(current, 'star-end-dialog')
        confirm = finish_confirmation(current, nav.stop_check)
        if confirm is not None and confirm == previous and not nav._stopping():
            checkpoint.update(star_confirm_intent=True)
            nav.input.tap(*confirm, jitter=0)
            logger.info('Verified star: confirmed End Battle once')
            return
        previous = confirm

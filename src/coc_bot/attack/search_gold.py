"""Recover a Home Village search fee using only verified mine collection."""
from functools import lru_cache
from math import dist
from pathlib import Path

import cv2
from loguru import logger

from coc_bot.progression.reader import balance_amount
from coc_bot.progression.resources import HUD
from coc_bot.upgrades.vision import crop
from coc_bot.vision.battle_menu import home_build_control_visible
from coc_bot.vision.matcher import TemplateMatcher
from coc_bot.vision.screens import BotMode, ScreenType


@lru_cache(maxsize=3)
def _reference(name):
    path = Path(__file__).resolve().parents[1] / 'vision' / 'assets' / (name + '.png')
    return TemplateMatcher.load_template(str(path))


def _match(frame, name, region, scales, threshold):
    width_scale = frame.shape[1] / 1853
    matcher = TemplateMatcher(scale_range=[width_scale * scale for scale in scales])
    result = matcher.find_in_roi(frame, _reference(name), region, threshold=threshold)
    return result.center if result else None


def gold_shortfall_close(frame):
    """The fee shortfall title and its red X authorize only closing the offer."""
    scales = (.98, 1, 1.02)
    if _match(frame, 'matchmaking_gold_title', (.32,.265,.68,.355), scales, .96) is None:
        return None
    return _match(frame, 'matchmaking_gold_close', (.67,.25,.74,.365), scales, .96)


def gold_bubble(frame):
    # Exclude Home's fixed controls, including the gold HUD and store button.
    return _match(frame, 'home_gold_collection', (.14,.17,.906,.80), (.88,.94,1,1.06,1.12), .96)


def collect_search_gold(nav):
    """Tap one mine bubble on two matching Home frames, then verify the gain."""
    hall = getattr(nav.config, 'account_town_hall', None)
    if type(hall) is not int or not 2 <= hall <= 18:
        return False
    gem_y = (.235,.276) if hall >= 7 else (.165,.207)

    def observe():
        frame = nav.capture.screenshot()
        if (nav._stopping() or nav.classify(frame, mode=BotMode.ATTACK) != ScreenType.HOME
                or not home_build_control_visible(frame)):
            return None, None, None
        gold = balance_amount(crop(frame, HUD['gold']), nav.stop_check)
        gems = balance_amount(crop(frame, (.905,gem_y[0],.954,gem_y[1])), nav.stop_check)
        return frame, gold, gems

    first, gold, gems = observe()
    if first is None or gold is None or gems is None:
        return False
    point = gold_bubble(first)
    if point is None:
        return False
    second, confirmed_gold, confirmed_gems = observe()
    if second is None or (gold, gems) != (confirmed_gold, confirmed_gems):
        return False
    confirmed = gold_bubble(second)
    if confirmed is None or dist(point, confirmed) > 6 or nav._stopping():
        return False
    nav.input.tap(*confirmed, jitter=0)

    previous = None
    for _ in range(5):
        if nav._sleep(.45):
            return False
        _, after, after_gems = observe()
        if after is not None and after > gold and after_gems == gems:
            if after == previous:
                logger.info('Matchmaking gold collected: {} → {}, gems unchanged', gold, after)
                return True
            previous = after
        else:
            previous = None
    return False

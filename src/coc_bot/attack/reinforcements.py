"""Recognize the native Clan Castle card, not an account's clan emblem.

The Castle and siege machines share a single deployment choice. Represent the
Castle as a single-use siege entry so existing geometry and verification apply.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


CLAN_CASTLE = 'clan_castle'
SIEGE_UNITS = frozenset({'wall_wrecker', 'battle_blimp', 'stone_slammer',
                       'siege_barracks', 'log_launcher', 'flame_flinger', 'battle_drill'})


@lru_cache(maxsize=1)
def badge_reference():
    with np.load(Path(__file__).with_name('assets')/'clan_castle_badge.npz',
                 allow_pickle=False) as archive:
        return cv2.cvtColor(archive['image'], cv2.COLOR_BGR2GRAY), archive['mask']


def castle_card_quantity(cell):
    """Return 1 (available), 0 (greyed out), or None (not positively identified).

    Only use on a freshly segmented battle army card. The native shield rim and
    the empty background surrounding it must both match. Interior clan artwork,
    card position, troop levels and unreadable count badges grant no permission.
    """
    h, w = cell.shape[:2]
    if min(h, w) < 40 or not .6 < w/h < .9:
        return None
    # A Castle has no troop/level badge in any of these background patches.
    hsv = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
    patches = [hsv[round(h*a):round(h*b), round(w*c):round(w*d)]
               for a,b,c,d in ((.12,.22,.15,.85), (.77,.88,.15,.85),
                               (.3,.7,.08,.17), (.3,.7,.83,.92))]
    active = all(((p[:,:,0] >= 85) & (p[:,:,0] <= 100) &
                  (p[:,:,1] > 100) & (p[:,:,2] > 130)).mean() > .90 for p in patches)
    depleted = all(((p[:,:,1] < 45) & (p[:,:,2] < 145)).mean() > .90 for p in patches)
    if not active and not depleted:
        return None
    ref, mask = badge_reference()
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    # Small size changes come from selection outlines and display scaling.
    region = gray[round(h*.18):round(h*.75), round(w*.12):round(w*.88)]
    best = 0.
    for factor in (.90, .95, 1., 1.05, 1.10):
        scale = w/130 * factor
        size = (round(ref.shape[1]*scale), round(ref.shape[0]*scale))
        if size[0] > region.shape[1] or size[1] > region.shape[0]:
            continue
        template = cv2.resize(ref, size, interpolation=cv2.INTER_AREA)
        stencil = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
        scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED, mask=stencil)
        scores[~np.isfinite(scores)] = 0
        best = max(best, float(scores.max()))
    return int(active) if best >= .95 else None


def available_castle(card):
    return (card.unit_id == CLAN_CASTLE and card.kind == 'siege' and card.stable
            and type(card.quantity) is int and card.quantity == 1)

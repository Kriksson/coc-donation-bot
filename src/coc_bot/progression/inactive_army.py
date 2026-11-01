"""Recognize expired Super Troops without ever touching their paid Activate action."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


@lru_cache(maxsize=8)
def reference(name):
    return cv2.imread(str(Path(__file__).with_name('assets') / (name+'.png')))


def match(frame, name, bounds):
    if not isinstance(frame, np.ndarray):return None
    ref=reference(name)
    if ref is None:return None
    original_h,original_w=frame.shape[:2]
    frame=cv2.resize(frame,(1853,1048))
    h,w=frame.shape[:2];x0,y0,x1,y1=[round(v*n) for v,n in zip(bounds,(w,h,w,h))]
    area=frame[y0:y1,x0:x1];rh,rw=ref.shape[:2]
    if area.shape[0]<rh or area.shape[1]<rw:return None
    # Smooth one raster pixel after normalization so thin trash strokes survive
    # screenshot scaling. The same strict score and brightness gates remain.
    _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(
        cv2.GaussianBlur(area,(3,3),0),cv2.GaussianBlur(ref,(3,3),0),cv2.TM_CCOEFF_NORMED))
    if score<.97 or area[y:y+rh,x:x+rw].mean()<ref.mean()*.9:return None
    return round((x0+x+rw/2)*original_w/w),round((y0+y+rh/2)*original_h/h)


def inactive_clear(frame, stop=None):
    from coc_bot.progression.preparation import capacity,army_heading_visible
    if stop and stop():return None
    space=capacity(frame,stop)
    if not space or space[0]<=0 or not army_heading_visible(frame,stop):return None
    # Activate is evidence only. Never use its coordinates for input.
    if not match(frame,'inactive_super_activate',(.435,.27,.98,.425)):return None
    point=match(frame,'troop_clear',(.95,.21,.98,.26))
    return (point,space) if point else None


def clear_confirmation(frame, stop=None):
    if stop and stop():return None
    for name,box in [('remove_troops_title',(.35,.27,.65,.35)),
                     ('remove_troops_message',(.29,.42,.71,.49))]:
        if not match(frame,name,box):return None
    okay=match(frame,'remove_troops_okay',(.55,.60,.66,.68))
    cancel=match(frame,'remove_troops_cancel',(.33,.60,.45,.68))
    return (okay,cancel) if okay and cancel else None


def clear_inactive(prep):
    """One troop-only clear, with two fresh proofs before each input."""
    from coc_bot.progression.preparation import capacity,army_page
    first=inactive_clear(prep.frame(),prep.stop)
    if first is None:return False
    if inactive_clear(prep.frame(),prep.stop)!=first:
        raise ValueError('Inactive Super Troop army changed; no clearing input sent')
    point,space=first
    prep.tap(point)
    dialog=clear_confirmation(prep.frame(),prep.stop)
    if dialog is None or clear_confirmation(prep.frame(),prep.stop)!=dialog:
        raise ValueError('Troop-only removal confirmation is unverified; no confirmation sent')
    prep.tap(dialog[0])
    for _ in range(3):
        a,b=prep.frame(),prep.frame()
        if (army_page(a,prep.stop) and army_page(b,prep.stop)
                and capacity(a,prep.stop)==capacity(b,prep.stop)==(0,space[1])):
            return True
        prep.s._sleep(.3)
    raise ValueError('Cleared troop capacity was not verified; no removal tap will be replayed')

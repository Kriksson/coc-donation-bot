"""Recognize the native connection failure, requiring its message and action."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=3)
def _anchor(name):
    return cv2.imread(str(Path(__file__).with_name('assets')/('connection_'+name+'.png')),cv2.IMREAD_GRAYSCALE)


def connection_retry_button(frame):
    if not isinstance(frame,np.ndarray) or frame.ndim!=3:return None
    h,w=frame.shape[:2]
    if not 1.5<=w/h<=2.1:return None
    canvas=cv2.resize(frame,(1853,1048))
    gray=cv2.cvtColor(canvas,cv2.COLOR_BGR2GRAY)
    region=gray[350:660,400:1460]
    matches=[]
    for name in ('title','message','retry'):
        template=_anchor(name)
        if template is None:return None
        _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(region,template,cv2.TM_CCOEFF_NORMED))
        if score<.94:return None
        matches.append((400+point[0],350+point[1],template.shape[1],template.shape[0]))
    (tx,ty,_,th),(mx,my,_,mh),(rx,ry,rw,rh)=matches
    if max(tx,mx,rx)-min(tx,mx,rx)>12 or not 8<=my-ty-th<=35 or not 35<=ry-my-mh<=90:return None
    action=cv2.cvtColor(canvas[ry:ry+rh,rx:rx+rw],cv2.COLOR_BGR2HSV)
    cyan=cv2.inRange(action,(75,60,170),(110,255,255))
    if np.count_nonzero(cyan)/cyan.size<.04:return None
    return round((rx+rw/2)*w/1853),round((ry+rh/2)*h/1048)


def recover_connection_error(nav,frame):
    """Three independently verified retries per two minutes; Stop always wins."""
    import time
    from loguru import logger
    point=connection_retry_button(frame)
    if point is None or nav._stopping():return False
    now=time.monotonic()
    retries=[at for at in nav.__dict__.get('_connection_retry_times',[]) if now-at<120]
    nav._connection_retry_times=retries
    # Recognized but cooling down: consume this frame so no fallback chat or
    # corner tap can target the underlying loading screen.
    if len(retries)>=3 or retries and now-retries[-1]<10:return True
    if connection_retry_button(nav.capture.screenshot())!=point or nav._stopping():return False
    logger.warning('Clash connection error — retrying game connection ({}/3)',len(retries)+1)
    nav.input.tap(*point,jitter=0)
    retries.append(now)
    return True

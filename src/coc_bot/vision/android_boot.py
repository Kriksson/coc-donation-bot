"""The inspected Waydroid boot logo over an otherwise black Android frame."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=1)
def _logo():
    return cv2.imread(str(Path(__file__).with_name('assets')/'android_boot_logo.png'))


def android_boot_frame(frame):
    if (not isinstance(frame,np.ndarray) or frame.ndim!=3 or frame.shape[2]!=3
            or frame.dtype!=np.uint8 or not 1.6<frame.shape[1]/frame.shape[0]<1.95):return False
    if float((frame[::16,::16].max(axis=2)<10).mean())<.97:return False
    image=cv2.resize(frame,(1920,1080))
    if float((image.max(axis=2)<10).mean())<.98:return False
    reference=_logo()
    if reference is None:return False
    region=image[430:690,650:1270]
    score=cv2.minMaxLoc(cv2.matchTemplate(region,reference,cv2.TM_CCOEFF_NORMED))[1]
    return score>=.98

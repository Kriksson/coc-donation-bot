"""Default-scenery outer deployment ring, registered afresh for this opponent.

Scenery being cosmetic does not make arbitrary screen-edge pixels deployable.
Only the supported default terrain can use its measured 44-tile build square.
Unknown scenery, moving cameras and contradictory red boundaries fail closed.
The executor verifies one native troop-count change before sending a burst.
"""
import numpy as np

from coc_bot.attack.army import check_stop
from coc_bot.attack.camera import compare_camera
from coc_bot.attack.mapping import observe_boundary
from coc_bot.attack.projection import Projection
from coc_bot.layouts.grid import camera, zone, tiles


SOURCE = 'registered_default_outer_ring'


def outer_projection(previous, frame, *, stop=None):
    check_stop(stop)
    if previous.shape != frame.shape:return None
    motion=compare_camera(previous,frame)
    if (not motion.get('verified') or abs(motion['scale']-1)>.003 or
            np.linalg.norm(np.asarray(motion['transform'])[:,2])>2):return None
    registrations=[]
    for image in (previous,frame):
        check_stop(stop)
        registered=camera(image,stop or (lambda:False))
        if not registered.get('registered'):return None
        registrations.append(registered)
    corners=[zone(r,0) for r in registrations]
    if np.max(np.linalg.norm(corners[0]-corners[1],axis=1))>3:return None
    # Visible red fragments may refute a terrain fit; they cannot certify a
    # missing side. Permit the game's footprint border just beyond build tiles.
    for image,registered in zip((previous,frame),registrations):
        observed=observe_boundary(image,frame if image is previous else previous,
                                  battle_confirmed=True,stop_check=stop)
        for segment in observed.segments:
            h,w=image.shape[:2]
            uv=tiles(registered,np.asarray(segment['points'])*[w,h])
            if (uv < -1.5).any() or (uv > 45.5).any():return None
    projection=Projection(tuple(map(tuple,corners[1])),source=SOURCE)
    try:projection.validate()
    except ValueError:return None
    return projection

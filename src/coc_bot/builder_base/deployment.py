"""Spread air camps over observed boundary segments in the current camera view.

Spacing is a conservative screen-space constraint for the inspected zoom; it
is not a live troop tracker and cannot guarantee separation after units move.
"""
import cv2
import numpy as np
from coc_bot.attack.mapping import observe_boundary


def air_deployment_points(frame, fallback=()):
    h,w=frame.shape[:2]
    observation=observe_boundary(frame,battle_confirmed=True)
    segments=observation.segments
    if not segments:return list(fallback)
    endpoints=np.array([p for s in segments for p in s['points']])*[w,h]
    center=(endpoints.min(axis=0)+endpoints.max(axis=0))/2
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    points=list(fallback)
    for segment in segments:
        start,end=np.array(segment['points'])*[w,h]
        delta=end-start;length=float(np.linalg.norm(delta))
        if length<w*.04:continue
        normal=np.array([-delta[1],delta[0]])/length
        if np.dot(normal,(start+end)/2-center)<0:normal=-normal
        for fraction in (.18,.5,.82):
            point=np.rint(start+delta*fraction+normal*w*.022).astype(int)
            x,y=point
            if not w*.15<x<w*.84 or not h*.15<y<h*.76:continue
            if x<w*.28 and y<h*.29 or x>w*.76 and y<h*.23:continue
            patch=hsv[y-8:y+9,x-8:x+9]
            turf=(cv2.inRange(patch,(65,20,35),(120,170,180))
                  |cv2.inRange(patch,(108,25,80),(140,150,225)))
            if turf.mean()/255>.75 and gray[y-8:y+9,x-8:x+9].std()<22:
                candidate=(int(x),int(y))
                if candidate not in points:points.append(candidate)
    return points


def air_distance(a,b):
    # Compensate for the vertically compressed isometric ground plane.
    return float(np.hypot(a[0]-b[0],(a[1]-b[1])/.70))


def separated_air_target(points, occupied, width, attempt=0):
    """Never fall back to a clustered point when the observed view is too small."""
    if not points:return None
    eligible=[p for p in points if all(air_distance(p,q)>=width*.12 for q in occupied)]
    if not eligible:return None
    if occupied:
        eligible.sort(key=lambda p:min(air_distance(p,q) for q in occupied),reverse=True)
    else:
        # Start at an extreme that leaves room for the following camps.
        eligible.sort(key=lambda p:max(air_distance(p,q) for q in points),reverse=True)
    return eligible[attempt%len(eligible)]

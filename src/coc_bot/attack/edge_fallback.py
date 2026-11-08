"""A legacy-style deployment line backed by a single observed red edge."""
from dataclasses import dataclass

import cv2
import numpy as np

from coc_bot.attack.mapping import boundary_mask
from coc_bot.attack.projection import input_area


SOURCE = 'verified_local_edge'


@dataclass(frozen=True)
class LocalEdge:
    start: tuple[float, float]
    end: tuple[float, float]
    source: str = SOURCE

    def validate(self):
        if not np.isfinite((self.start, self.end)).all() or np.linalg.norm(np.subtract(self.end, self.start)) < 30:
            raise ValueError('A visible deployment edge is required')

    def pixel(self, point):
        # No interior, alternate side or synthetic missing corner is available.
        if abs(point.x - .055) > .001 or not 0 <= point.y <= 1:
            raise ValueError('Fallback deployment must stay on the observed edge')
        return tuple(np.asarray(self.start) * (1 - point.y) + np.asarray(self.end) * point.y)


def local_edge(previous, frame, observation, center, motion):
    """Keep a continuous, repeated, outward-facing line clear of controls."""
    if (previous.shape != frame.shape or abs(np.linalg.norm(motion[:2, 0]) - 1) > .003
            or np.linalg.norm(motion[:2, 2]) > 2):
        return None
    h, w = frame.shape[:2]
    older = cv2.dilate(boundary_mask(previous, allow_fading=True), np.ones((5,5), np.uint8))
    candidates = []
    for segment in observation.segments:
        a, b = np.asarray(segment['points']) * [w, h]
        delta = b - a
        length = np.linalg.norm(delta)
        if length < .055 * w or segment['support'] < .88:
            continue
        samples = np.rint(np.linspace(a, b, 50)).astype(int)
        if (older[samples[:,1], samples[:,0]] > 0).mean() < .90:
            continue
        normal = np.array([-delta[1], delta[0]]) / length
        outward = np.dot((a+b)/2 - center, normal)
        if abs(outward) < .18 * h:
            continue
        offset = normal * np.sign(outward) * h * .022
        start, end = a + delta * .18 + offset, b - delta * .18 + offset
        if all(input_area(*point, w, h) for point in np.linspace(start, end, 12)):
            candidates.append((length, LocalEdge(tuple(start), tuple(end))))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

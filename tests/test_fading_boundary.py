from pathlib import Path
from unittest import TestCase
import cv2
import numpy as np
from coc_bot.attack.mapping import observe_boundary
from coc_bot.attack.projection import fit_projection
from coc_bot.attack.plans import MapPoint

ROOT=Path(__file__).parent/'fixtures/attack'


class FadingBoundaryTests(TestCase):
    def test_pulsing_default_scenery_keeps_actual_outer_ring_not_interior_walls(self):
        frames=[cv2.imread(str(ROOT/name)) for name in ('boundary-bright.png','boundary-fading.png')]
        for previous,current in (frames,frames[::-1]):
            observed=observe_boundary(current,previous,battle_confirmed=True)
            self.assertTrue(observed.stable)
            projection=fit_projection(observed.segments,1853,1048)
            self.assertIsNotNone(projection)
            # Independently inspected red perimeter. The broken fit put the
            # left corner at x385 and every dragon tap inside the village.
            np.testing.assert_allclose(projection.corners,[(924,-51),(1600,457),(924,965),(249,457)],atol=4)
            for y in np.linspace(.27,.73,11):
                x,py=projection.pixel(MapPoint(.055,float(y)))
                # The native top-left boundary is y=-.752*x+644.
                self.assertLess(py+.752*x-644,-15)

    def test_darkened_or_obscured_outline_never_establishes_this_map(self):
        frame=cv2.imread(str(ROOT/'boundary-fading.png'))
        empty=np.zeros_like(frame)
        observed=observe_boundary(empty,frame,battle_confirmed=True)
        self.assertFalse(observed.stable)
        self.assertFalse(observed.segments)
        self.assertFalse(observe_boundary(frame,frame.copy()).segments)

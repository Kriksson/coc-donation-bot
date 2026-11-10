import unittest
from pathlib import Path
from unittest.mock import patch

import cv2

from coc_bot.builder_base.vision import BuilderReader


class BuilderBoatTargetTests(unittest.TestCase):
    def setUp(self):
        self.reader=BuilderReader()
        root=Path(__file__).parent/'fixtures'/'builder_base'
        self.info=cv2.imread(str(root/'home-wall-selected-info-context.png'))
        self.boat=cv2.imread(str(root/'home-forward-boat.png'))

    def test_forward_boat_requires_visible_striped_sail(self):
        point=self.reader.boat_target(self.boat,returning=False)
        self.assertIsNotNone(point)

    def test_selected_wall_info_cannot_be_accepted_even_if_template_match_reports_it(self):
        # Cache the real template, then simulate the false point reported by
        # the earlier run. Also probe the visible center of the Info button.
        self.reader.find(self.info,'boat',(.14,.12,.90,.80),threshold=.01)
        for point in ((479,830),(544,830)):
            with self.subTest(point=point), patch.object(self.reader,'find',return_value=point):
                self.assertIsNone(self.reader.boat_target(self.info,returning=False))

    def test_return_template_uses_the_same_sail_proof_on_dark_water(self):
        # This saved transition frame shows the striped boat against the dark
        # Builder coastline; its slight motion blur needs a lower test-only
        # correlation threshold, while the sail proof remains unchanged.
        frame=cv2.imread(str(Path(__file__).parent/'fixtures'/'builder_base'/'dark-coast-boat-transition.png'))
        point=self.reader.boat_target(frame,returning=True,threshold=.30)
        self.assertIsNotNone(point)
        self.assertTrue(1420<=point[0]<=1580)
        self.assertTrue(220<=point[1]<=380)


if __name__=='__main__':
    unittest.main()

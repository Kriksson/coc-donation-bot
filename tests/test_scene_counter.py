from pathlib import Path
from unittest import TestCase
import cv2
from coc_bot.progression.reader import balance_amount


class SceneCounterTests(TestCase):
    def frame(self):
        return cv2.imread(str(Path(__file__).parent/'fixtures/progression/scene-elixir-counter.png'))

    def test_native_scenery_does_not_hide_the_complete_counter(self):
        self.assertEqual(balance_amount(self.frame()),4_864_686)

    def test_leading_digit_is_retained_as_the_number_grows_left(self):
        frame=self.frame()
        frame[6:28,87:106]=frame[6:28,118:137].copy()
        self.assertEqual(balance_amount(frame),44_864_686)

    def test_uncertain_adjacent_leading_shape_cannot_be_discarded(self):
        frame=self.frame()
        frame[15:28,102:112]=255
        self.assertIsNone(balance_amount(frame))

    def test_an_unrecognized_character_on_the_same_baseline_blocks(self):
        frame=self.frame()
        frame[6:28,35:53]=255
        self.assertIsNone(balance_amount(frame))

from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from coc_bot.upgrades.vision import Candidate, UpgradeReader
from coc_bot.vision.capped_frames import has_exact_cap_178


FIXTURE = (Path(__file__).with_name('fixtures') / 'progression'
           / 'home-candidate-confirmation-capped.png')


class HomeUpgradeConfirmationCapTests(unittest.TestCase):
    def setUp(self):
        self.frame = cv2.imread(str(FIXTURE))
        if self.frame is None:
            self.fail(f'could not read fixture: {FIXTURE}')
        self.reader = UpgradeReader()
        self.candidate = Candidate('Elixir Collector', 1_500, 'gold', (1, 1))

    def test_capped_home_confirmation_reads_discounted_payable_price(self):
        self.assertTrue(has_exact_cap_178(self.frame))
        h, w = self.frame.shape[:2]
        # This fixture has a deliberately dimmed background while the modal is
        # at the measured cap. The local modal parse must remain price-specific.
        background = self.frame[round(h * .20):round(h * .90), round(w * .92):]
        self.assertLess(float(np.percentile(cv2.cvtColor(
            background, cv2.COLOR_BGR2GRAY), 99)), 100)
        raw = self.frame.copy()

        result = self.reader.confirmation(self.frame, self.candidate)

        self.assertEqual(result['name'], 'Elixir Collector')
        self.assertEqual(result['cost'], 1_500)
        self.assertEqual(result['currency'], 'gold')
        self.assertEqual(result['point'], (1348, 936))
        self.assertTrue(np.array_equal(self.frame, raw))
        self.assertIsNone(self.reader.confirmation(
            self.frame, Candidate('Elixir Collector', 3_000, 'gold', (1, 1))))

    def test_capped_home_dialog_close_requires_candidate_title_and_complete_x(self):
        self.assertEqual(self.reader.detail_close(self.frame, self.candidate), (1701, 81))
        self.assertIsNone(self.reader.detail_close(self.frame))
        self.assertIsNone(self.reader.detail_close(
            self.frame, Candidate('Elixir Storage', 1_500, 'gold', (1, 1))))

        h, w = self.frame.shape[:2]
        no_x = self.frame.copy()
        no_x[round(h * .052):round(h * .096),
             round(w * .875):round(w * .900)] = (89, 89, 89)
        self.assertIsNone(self.reader.detail_close(no_x, self.candidate))

        incomplete_title = self.frame.copy()
        incomplete_title[round(h * .035):round(h * .095),
                         round(w * .26):round(w * .73)] = (89, 89, 89)
        self.assertIsNone(self.reader.detail_close(incomplete_title, self.candidate))

        dim = (self.frame.astype(np.float32) * .75).astype(np.uint8)
        self.assertIsNone(self.reader.detail_close(dim, self.candidate))

        from coc_bot.vision.capped_frames import restore_cap_178
        self.assertEqual(self.reader.detail_close(restore_cap_178(self.frame), self.candidate),
                         (1701, 81))

    def test_wrong_title_or_currency_does_not_authorize_cap_restoration(self):
        wrong_title = Candidate('Elixir Storage', 1_500, 'gold', (1, 1))
        self.assertIs(self.reader._restore_capped_home_confirmation(
            self.frame, wrong_title), self.frame)
        self.assertIsNone(self.reader.confirmation(self.frame, wrong_title))

        with patch.object(self.reader, 'label',
                          return_value='Upgrade Elixir Collector to Level 5 gold'):
            self.assertIs(self.reader._restore_capped_home_confirmation(
                self.frame, self.candidate), self.frame)

        wrong_resource = Candidate('Elixir Collector', 1_500, 'elixir', (1, 1))
        self.assertIs(self.reader._restore_capped_home_confirmation(
            self.frame, wrong_resource), self.frame)
        self.assertIsNone(self.reader.confirmation(self.frame, wrong_resource))

    def test_missing_resource_icon_does_not_use_blue_hammer_button(self):
        frame = self.frame.copy()
        # The green Confirm resource icon is separate from the blue Hammer of
        # Building button. Remove only the gold icon and retain both controls.
        h, w = frame.shape[:2]
        frame[round(h * .845):round(h * .922),
              round(w * .748):round(w * .779)] = (89, 89, 89)

        self.assertIs(self.reader._restore_capped_home_confirmation(
            frame, self.candidate), frame)
        self.assertIsNone(self.reader.confirmation(frame, self.candidate))

    def test_missing_close_x_or_confirm_button_keeps_modal_unrestored(self):
        no_x = self.frame.copy()
        h, w = no_x.shape[:2]
        no_x[round(h * .052):round(h * .096),
             round(w * .875):round(w * .900)] = (89, 89, 89)
        self.assertIs(self.reader._restore_capped_home_confirmation(
            no_x, self.candidate), no_x)
        self.assertIsNone(self.reader.confirmation(no_x, self.candidate))

        blue_only = self.frame.copy()
        blue_only[round(h * .80):round(h * .95),
                  round(w * .62):round(w * .79)] = (89, 89, 89)
        self.assertIs(self.reader._restore_capped_home_confirmation(
            blue_only, self.candidate), blue_only)
        self.assertIsNone(self.reader.confirmation(blue_only, self.candidate))

    def test_half_bright_transition_is_not_normalized(self):
        frame = (self.frame.astype(np.float32) * .75).astype(np.uint8)
        self.assertFalse(has_exact_cap_178(frame))
        self.assertIs(self.reader._restore_capped_home_confirmation(
            frame, self.candidate), frame)
        self.assertIsNone(self.reader.confirmation(frame, self.candidate))

    def test_255_range_frame_is_left_unchanged(self):
        from coc_bot.vision.capped_frames import restore_cap_178
        frame = restore_cap_178(self.frame)
        self.assertGreater(int(frame.max()), 250)
        self.assertIs(self.reader._restore_capped_home_confirmation(
            frame, self.candidate), frame)
        result = self.reader.confirmation(frame, self.candidate)
        self.assertEqual(result['cost'], 1_500)


if __name__ == '__main__':
    unittest.main()

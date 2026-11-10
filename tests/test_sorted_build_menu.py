import unittest
from pathlib import Path
from unittest.mock import MagicMock
import cv2
import numpy as np
from coc_bot.progression.runner import ProgressionRunner
from coc_bot.progression.reader import ProgressionReader


class SortedBuildMenuTests(unittest.TestCase):
    def test_cost_sort_selection_is_detected_in_the_saved_filter_panel(self):
        fixture=Path(__file__).parent/'fixtures'/'progression'/'filters.png'
        frame=cv2.imread(str(fixture))
        self.assertIsNotNone(frame)
        reader=ProgressionReader()
        self.assertIsNone(reader.selected_filter(frame))
        selected=frame.copy()
        center=(round(frame.shape[1]*.561),round(frame.shape[0]*.65))
        cv2.rectangle(selected,(center[0]-76,center[1]-24),(center[0]+76,center[1]+24),(0,190,255),-1)
        self.assertEqual(reader.selected_filter(selected),center)

    def runner(self):
        runner = ProgressionRunner.__new__(ProgressionRunner)
        runner.stopped = lambda: False
        runner.wait = lambda: False
        runner.reader = MagicMock()
        runner.reader.filters_open.return_value = True
        runner.reader.selected_filter.return_value = None
        runner.reader.unfiltered_top.return_value = False
        runner.reader.menu_kind.return_value = 'buildings'
        runner.capture = MagicMock()
        runner.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        runner.capture.screenshot.return_value = runner.frame
        runner.input = MagicMock()
        return runner

    def test_selected_cost_sort_is_cleared_and_suggested_order_is_confirmed_twice(self):
        runner = self.runner()
        cost_min=(round(1920*.561),round(1080*.65))
        runner.reader.selected_filter.side_effect=[cost_min,None,None]
        runner.reader.unfiltered_top.return_value=True
        self.assertIs(runner.clear_filters(runner.frame),runner.frame)
        runner.input.tap.assert_any_call(*cost_min,jitter=0)
        runner.input.swipe.assert_not_called()
        self.assertEqual(runner.reader.selected_filter.call_count,3)
        self.assertEqual(runner.reader.unfiltered_top.call_count,2)

    def test_missing_suggested_order_proof_never_accepts_stationary_swipes(self):
        runner=self.runner()
        with self.assertRaisesRegex(ValueError,'Suggested upgrades ordering'):
            runner.clear_filters(runner.frame)
        runner.input.swipe.assert_not_called()

    def test_changed_filter_blocks_accepting_a_complete_inventory(self):
        runner = self.runner()
        runner.reader.selected_filter.side_effect = [None, (800, 260)]
        with self.assertRaisesRegex(ValueError, 'filter state changed'):
            runner.clear_filters(runner.frame)
        runner.input.tap.assert_not_called()
        runner.input.swipe.assert_not_called()

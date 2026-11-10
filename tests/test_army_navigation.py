from unittest import TestCase
from unittest.mock import MagicMock, patch
from pathlib import Path
import cv2
import numpy as np
from coc_bot.progression.preparation import ArmyPreparation, edit_army_button


class EditArmyButtonTests(TestCase):
    def frame(self,name='attack-menu-1920.png'):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/progression'/name))
        self.assertIsNotNone(frame)
        return frame

    def test_live_button_is_recognized_without_ocr(self):
        frame=self.frame();before=frame.copy()
        with patch('coc_bot.progression.preparation._white_label',side_effect=AssertionError('OCR must not be needed')):
            self.assertEqual(edit_army_button(frame),(225,1027))
        self.assertTrue(np.array_equal(frame,before))

    def test_previous_native_layout_still_reads(self):
        self.assertEqual(edit_army_button(self.frame('attack-menu.png')),(217,997))

    def test_artwork_needs_visible_green_button_and_correct_location(self):
        native=self.frame()
        blank_label=native.copy();blank_label[999:1058,169:355]=(75,180,100)
        no_green=native.copy();no_green[988:1070,86:371]=0
        no_green[1005:1042,172:351]=native[1005:1042,172:351]
        moved=np.zeros_like(native);moved[705:742,172:351]=native[1005:1042,172:351]
        for name,frame in [('blank label',blank_label),('no green',no_green),
                           ('wrong location',moved),('dimmed',cv2.convertScaleAbs(native,alpha=.5))]:
            with self.subTest(name=name),patch('coc_bot.progression.preparation._white_label',return_value=''):
                self.assertIsNone(edit_army_button(frame))

    def test_stop_prevents_button_detection(self):
        self.assertIsNone(edit_army_button(self.frame(),lambda:True))


class ArmyNavigationTests(TestCase):
    def prep(self):
        prep = ArmyPreparation.__new__(ArmyPreparation)
        prep.stop = None
        prep.s = MagicMock()
        prep.frame = MagicMock(return_value=np.zeros((1080,1920,3),dtype=np.uint8))
        prep.tap = MagicMock()
        return prep

    def test_lost_navigation_input_retries_only_on_verified_match_menu(self):
        prep=self.prep()
        with patch('coc_bot.progression.preparation.army_page',side_effect=[False]*6+[True]), \
             patch('coc_bot.progression.preparation.edit_army_button',return_value=(225,1027)), \
             patch('coc_bot.progression.preparation.direct_match_button',return_value=(328,799)):
            prep.open()
        self.assertEqual(prep.tap.call_count,2)

    def test_unknown_screen_never_gets_a_retry(self):
        prep=self.prep()
        with patch('coc_bot.progression.preparation.army_page',return_value=False), \
             patch('coc_bot.progression.preparation.edit_army_button',return_value=(225,1027)), \
             patch('coc_bot.progression.preparation.direct_match_button',return_value=None):
            with self.assertRaisesRegex(ValueError,'My Army did not open'):prep.open()
        prep.tap.assert_called_once_with((225,1027))

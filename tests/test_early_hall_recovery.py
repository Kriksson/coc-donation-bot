from pathlib import Path
import shutil
from unittest import skipUnless
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
import cv2
import numpy as np
from coc_bot.attack.navigator import AttackNavigator
from coc_bot.config import load_config
from coc_bot.progression.resources import HomeResources
from coc_bot.upgrades.vision import crop,currency
from coc_bot.vision.auxiliary import AuxiliaryPageDetector
from coc_bot.vision.screens import ScreenClassifier,ScreenType,BotMode

ROOT=Path(__file__).parent/'fixtures'


class EarlyHallRecoveryTests(TestCase):
    def shop(self):return cv2.imread(str(ROOT/'auxiliary/treasure-early-hall.png'))

    @skipUnless(shutil.which('tesseract'),'Native Home button OCR is required')
    def test_verified_th2_never_checks_gems_as_dark_elixir(self):
        frame=cv2.imread(str(ROOT/'progression/early-hall-resource-controls.png'))
        self.assertEqual(currency(crop(frame,(.963,.158,.998,.225))),'dark_elixir')
        nav=Mock();nav._stopping=Mock(return_value=False)
        nav.classifier._open_chat_icon_visible.return_value=True
        nav.capture.screenshot.return_value=frame
        reader=HomeResources(nav);self.assertTrue(reader.home(frame))
        reader.storage_capacity=Mock(side_effect=lambda f,r:8500 if r in ('gold','elixir') else None)
        # Model the tooltip appearing after each row tap and disappearing after
        # its verified close; capacity OCR itself is mocked independently.
        reader.storage_tooltip_visible=Mock(side_effect=[False,False,False,True,True,True,False,
                                                          False,False,False,True,True,True,False,
                                                          False,False,False,False])
        with patch('coc_bot.progression.home.ensure_home',return_value=True),patch('coc_bot.stop.interrupted_sleep'):
            result=reader.observe(SimpleNamespace(account_town_hall=2))
        self.assertEqual(result['resources'],['gold','elixir'])
        self.assertEqual(result['balances'],{'gold':4708,'elixir':6058})
        self.assertTrue(all(c.args[1] in ('gold','elixir') for c in reader.storage_capacity.call_args_list))
        self.assertTrue(all(c.args[1]!=round(frame.shape[0]*.19) for c in nav.input.tap.call_args_list))

    def test_native_five_tab_treasure_shop_wins_in_every_mode(self):
        frame=self.shop();page=AuxiliaryPageDetector().detect(frame)
        self.assertEqual(page.screen,'shop');self.assertIsNotNone(page.close)
        self.assertLess(abs(page.close[0]-1783),4);self.assertLess(abs(page.close[1]-77),4)
        classifier=ScreenClassifier(load_config())
        for mode in (BotMode.ANY,BotMode.ATTACK,BotMode.DONATE,BotMode.HOME):
            self.assertEqual(classifier.classify(frame,mode),ScreenType.SHOP)

    def test_obscured_close_or_one_remaining_category_cannot_authorize_input(self):
        frame=self.shop();dim=AuxiliaryPageDetector().detect((frame*.4).astype(np.uint8))
        self.assertEqual(dim.screen,'shop');self.assertIsNone(dim.close)
        for y0,y1,x0,x1 in [(35,160,850,1010),(35,160,1000,1160)]:
            bad=frame.copy();bad[y0:y1,x0:x1]=0
            with patch('coc_bot.upgrades.vision.UpgradeReader.menu_kind',return_value=None):
                self.assertIsNone(AuxiliaryPageDetector().detect(bad))

    def navigator(self):
        nav=AttackNavigator(load_config(),Mock(),Mock());nav._sleep=Mock(return_value=False)
        nav.classify=Mock(return_value=ScreenType.BATTLE_RESULTS);nav.classifier=Mock()
        nav.classifier.find_reload_game_button.return_value=None
        nav.classifier.auxiliary_page.return_value=None
        nav.classifier.looks_like_live_replay.return_value=False
        nav.classifier.looks_like_surrender_dialog.return_value=False
        nav._village_home_anchors_visible=Mock(return_value=False)
        nav._tap_return_home_coords=Mock()
        return nav

    def invoke(self,nav):
        with patch('coc_bot.progression.home.recover_home_bonus',return_value=False), \
             patch('coc_bot.vision.battle_menu.reward_continue_button',return_value=None):
            return nav.return_home_from_attack()

    def test_false_results_shop_cannot_receive_a_calibrated_return_tap(self):
        nav=self.navigator();nav.capture.screenshot.return_value=self.shop()
        self.assertFalse(self.invoke(nav));nav.input.tap.assert_not_called()
        nav._tap_return_home_coords.assert_not_called()

    def test_real_results_require_two_frames_before_one_detected_target_tap(self):
        frame=cv2.imread(str(ROOT/'battle_completion/one-star-victory.png'))
        nav=self.navigator();target=nav.battle_completion.detect(frame)
        nav.capture.screenshot.side_effect=[frame,frame.copy(),np.zeros_like(frame)]
        nav._village_home_anchors_visible.side_effect=[False,True]
        nav._confirm_leave_via_clan_chat=Mock(return_value='confirmed')
        self.assertTrue(self.invoke(nav));nav.input.tap.assert_called_once_with(*target,jitter=0)
        nav._tap_return_home_coords.assert_not_called()

    def test_changed_second_results_frame_blocks_all_taps(self):
        frame=cv2.imread(str(ROOT/'battle_completion/one-star-victory.png'))
        nav=self.navigator();nav.capture.screenshot.side_effect=[frame,np.zeros_like(frame)]
        self.assertFalse(self.invoke(nav));nav.input.tap.assert_not_called()

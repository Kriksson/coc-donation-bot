from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
import cv2
import shutil
from unittest import skipUnless
from coc_bot.vision.notices import free_chest_tap_point
from coc_bot.progression.home import recover_free_chest

ROOT=Path(__file__).parent/'fixtures/accounts'


class FreeChestTests(TestCase):
    def frame(self):return cv2.imread(str(ROOT/'free-chest.png'))

    def test_known_reward_requires_native_prompt_and_independent_backdrop(self):
        self.assertEqual(free_chest_tap_point(self.frame()),(926,566))
        self.assertIsNotNone(free_chest_tap_point(cv2.resize(self.frame(),(1280,724))))
        for x,y,w,h in ((240,280,110,385),(1340,275,125,380),(730,825,370,105)):
            frame=self.frame();frame[y:y+h,x:x+w]=0
            self.assertIsNone(free_chest_tap_point(frame))
        self.assertIsNone(free_chest_tap_point((self.frame()*.4).astype('uint8')))
        for name in ('hammer-jam.png','connection-error.png','defense-results.png'):
            self.assertIsNone(free_chest_tap_point(cv2.imread(str(ROOT/name))))

    def test_after_first_strike_requires_readable_rarity_and_remaining_hammer(self):
        frame=cv2.imread(str(ROOT/'free-chest-struck.png'))
        from unittest.mock import patch
        with patch('coc_bot.upgrades.vision.text',return_value='Common'):
            self.assertIsNotNone(free_chest_tap_point(frame))
            frame[825:930,730:1100]=0
            self.assertIsNone(free_chest_tap_point(frame))
        frame=cv2.imread(str(ROOT/'free-chest-struck.png'))
        with patch('coc_bot.upgrades.vision.text',return_value='Buy'):
            self.assertIsNone(free_chest_tap_point(frame))

    @skipUnless(shutil.which('tesseract'),'Tesseract is required')
    def test_real_common_rarity_after_first_strike(self):
        self.assertIsNotNone(free_chest_tap_point(cv2.imread(str(ROOT/'free-chest-struck.png'))))

    def test_delivered_cosmetic_summary_requires_both_actions_and_reward_hall(self):
        from coc_bot.vision.notices import free_reward_skip_button
        frame=cv2.imread(str(ROOT/'free-reward-skin.png'))
        self.assertEqual(free_reward_skip_button(frame),(1730,952))
        self.assertIsNotNone(free_reward_skip_button(cv2.resize(frame,(1280,724))))
        for x,y,w,h in ((808,900,270,93),(1620,916,219,72),(40,820,300,205)):
            bad=frame.copy();bad[y:y+h,x:x+w]=0
            self.assertIsNone(free_reward_skip_button(bad))
        self.assertIsNone(free_reward_skip_button((frame*.4).astype('uint8')))
        for name in ('free-chest.png','hammer-jam.png','connection-error.png'):
            self.assertIsNone(free_reward_skip_button(cv2.imread(str(ROOT/name))))

    def test_skip_confirmation_requires_specific_non_spending_title_message_and_yes(self):
        from coc_bot.vision.notices import free_reward_skip_confirm_button,free_reward_skip_button
        frame=cv2.imread(str(ROOT/'skip-chest-confirm.png'))
        self.assertEqual(free_reward_skip_confirm_button(frame),(1128,676))
        self.assertIsNotNone(free_reward_skip_confirm_button(cv2.resize(frame,(1280,724))))
        self.assertIsNone(free_reward_skip_button(frame),'Dimmed underlying action must not be tapped')
        for x,y,w,h in ((644,296,566,64),(559,432,750,88),(951,595,355,163)):
            bad=frame.copy();bad[y:y+h,x:x+w]=0
            self.assertIsNone(free_reward_skip_confirm_button(bad))
        self.assertIsNone(free_reward_skip_confirm_button((frame*.4).astype('uint8')))

    def test_native_season_bank_is_distinct_from_openable_chests_and_announcements(self):
        from coc_bot.vision.notices import stalled_season_bank_visible
        frame=cv2.imread(str(ROOT/'season-bank-stalled.png'))
        self.assertTrue(stalled_season_bank_visible(frame))
        for name in ('free-chest.png','hammer-jam.png','connection-error.png'):
            self.assertFalse(stalled_season_bank_visible(cv2.imread(str(ROOT/name))))
        self.assertFalse(stalled_season_bank_visible((frame*.4).astype('uint8')))

    def test_native_reward_animation_wait_never_recognizes_dimmed_modal_or_village(self):
        from coc_bot.vision.notices import reward_reveal_visible
        for name in ('free-chest.png','free-chest-struck.png','free-reward-skin.png'):
            self.assertTrue(reward_reveal_visible(cv2.imread(str(ROOT/name))),name)
        for name in ('skip-chest-confirm.png','hammer-jam.png','season-bank-stalled.png','defense-results.png'):
            self.assertFalse(reward_reveal_visible(cv2.imread(str(ROOT/name))),name)

    def test_stalled_bank_relaunch_requires_time_fresh_proof_and_no_unresolved_action(self):
        from coc_bot.accounts.navigation import AccountNavigator
        from unittest.mock import patch
        session=SimpleNamespace(capture=Mock(),input=Mock(),config=Mock(),app=Mock(),navigator=Mock())
        frame=cv2.imread(str(ROOT/'season-bank-stalled.png'));session.capture.screenshot.return_value=frame
        nav=AccountNavigator(session)
        with patch('coc_bot.accounts.startup.unresolved',return_value=False):
            self.assertFalse(nav.recover_stalled_bank(frame,29));session.app.force_stop.assert_not_called()
            self.assertTrue(nav.recover_stalled_bank(frame,31))
            self.assertFalse(nav.recover_stalled_bank(frame,90))
        session.app.force_stop.assert_called_once();session.app.launch.assert_called_once()
        nav=AccountNavigator(session);session.app.reset_mock()
        with patch('coc_bot.accounts.startup.unresolved',return_value=True):
            self.assertFalse(nav.recover_stalled_bank(frame,90))
        session.app.force_stop.assert_not_called()

    def test_fresh_prompt_stop_and_limit_prevent_unverified_extra_taps(self):
        nav=SimpleNamespace(_stopping=Mock(return_value=False),capture=Mock(),input=Mock())
        nav.capture.screenshot.return_value=self.frame()
        self.assertTrue(recover_free_chest(nav,self.frame()))
        nav._free_chest_taps=60;self.assertFalse(recover_free_chest(nav,self.frame()))
        nav._free_chest_taps=0;nav.capture.screenshot.return_value=self.frame()*0
        self.assertFalse(recover_free_chest(nav,self.frame()))
        nav._stopping.return_value=True;self.assertFalse(recover_free_chest(nav,self.frame()))
        nav.input.tap.assert_called_once_with(926,566,jitter=0)

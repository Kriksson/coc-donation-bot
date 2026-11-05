import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from coc_bot.progression.construction import Construction
from coc_bot.progression.space import SpaceMaker
from coc_bot.upgrades.runner import UpgradeRunner


class ConstructionCleanupTests(unittest.TestCase):
    def runner(self):
        r=Mock()
        r.config=SimpleNamespace(progression_rearrange=False,progression_clear_obstacles=True)
        r.stopped.return_value=False;r.wait.return_value=False
        r.capture.screenshot.return_value=np.zeros((1048,1853,3),np.uint8)
        r.construction_controls=Mock(return_value={'cancel':(100,100),'confirm':None,'ghost':(120,120)})
        return r

    def test_held_preview_blocks_obstacle_search_after_cancel_tap(self):
        r=self.runner()
        with patch('coc_bot.runtime.verification.save_frame') as save:
            with self.assertRaisesRegex(ValueError,'cancellation was not verified'):
                Construction(r).locate_space()
        r.input.tap.assert_called_once_with(100,100,jitter=0)
        save.assert_called_once()
        r.input.client.run.assert_not_called()

    def test_changed_preview_is_never_cancelled_using_stale_coordinates(self):
        r=self.runner();calls=[0]
        def observed(_):
            calls[0]+=1
            return {'cancel':(100 if calls[0]<=10 else 200,100),'confirm':None,'ghost':(120,120)}
        r.construction_controls.side_effect=observed
        with self.assertRaisesRegex(ValueError,'changed before cancellation'):
            Construction(r).locate_space()
        r.input.tap.assert_not_called()

    def test_cancelled_preview_can_return_to_normal_navigation(self):
        r=self.runner();value=r.construction_controls.return_value
        r.construction_controls.side_effect=[value]*11+[None]
        self.assertIsNone(Construction(r).locate_space())
        r.input.tap.assert_called_once_with(100,100,jitter=0)

    def test_no_room_does_not_tap_an_arbitrary_map_position(self):
        r=self.runner()
        with patch('coc_bot.progression.space.home_build_control_visible',return_value=True),\
             patch('coc_bot.progression.space.candidates',return_value=[]),\
             patch('coc_bot.runtime.verification.save_frame') as save:
            self.assertEqual(SpaceMaker(r).run()['status'],'no_room')
        r.input.tap.assert_not_called();save.assert_called_once()

    def test_upgrade_cleanup_closes_known_details_then_verifies_home(self):
        r=UpgradeRunner.__new__(UpgradeRunner)
        r.stopped=Mock(return_value=False);r.wait=Mock(return_value=False)
        r.capture=Mock();r.capture.screenshot.return_value=np.zeros((1048,1853,3),np.uint8)
        r.reader=Mock();r.reader.menu_kind.return_value=None
        r.reader.detail_close.side_effect=[(100,20),None]
        r.state=Mock(return_value={});r.input=Mock();r.nav=Mock()
        r.nav.ensure_clan_chat.return_value=True
        r.close()
        r.input.tap.assert_called_once_with(100,20,jitter=0)
        r.nav.ensure_clan_chat.assert_called_once()

    def test_failed_home_cleanup_is_not_silently_treated_as_ready(self):
        r=UpgradeRunner.__new__(UpgradeRunner)
        r.stopped=Mock(return_value=False);r.capture=Mock();r.reader=Mock()
        r.reader.menu_kind.return_value=None;r.reader.detail_close.return_value=None
        r.nav=Mock();r.nav.ensure_clan_chat.return_value=False;r.input=Mock()
        with self.assertRaisesRegex(ValueError,'Home navigation was not verified'):r.close()
        r.input.tap.assert_not_called()

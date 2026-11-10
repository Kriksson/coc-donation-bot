import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
import cv2
import numpy as np

from coc_bot.config import load_config
from coc_bot.donation.navigator import Navigator
from coc_bot.progression.home import recover_known_overlay
from coc_bot.accounts.store import read,write
from coc_bot.builder_base.runner import BuilderBaseRunner

FIXTURES=Path(__file__).parent/'fixtures'


class SharedOverlayTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config=replace(load_config(),data_dir=Path(self.temp.name))
        self.nav=Navigator(self.config,Mock(),Mock())

    def test_unknown_window_never_uses_corner_or_configured_tap(self):
        self.config.tap_points['dismiss_popup']=(40,50)
        frame=np.zeros((1080,1920,3),np.uint8)
        self.assertFalse(self.nav._dismiss_popup(frame))
        self.nav.input.tap.assert_not_called();self.nav.input.back.assert_not_called()
        self.assertTrue((self.config.data_dir/'verification/unknown-overlay.png').exists())
        self.assertEqual(json.loads((self.config.data_dir/'verification/failures.json').read_text())[0]['feature'],'overlay.unknown')

    def test_reload_requires_same_notice_on_fresh_frame(self):
        from tests.test_idle_dialog import dialog_frame
        frame=dialog_frame()
        self.nav.capture.screenshot.return_value=np.zeros_like(frame)
        self.assertFalse(self.nav._dismiss_popup(frame))
        self.nav.input.tap.assert_not_called()
        self.assertEqual(self.nav._idle_reload_times,[])

    def test_welcome_and_event_notices_stop_after_two_acknowledgements(self):
        for fixture in ('welcome-after-defense.png','event-ended.png'):
            with self.subTest(fixture=fixture):
                nav=Navigator(self.config,Mock(),Mock())
                frame=cv2.imread(str(FIXTURES/'accounts'/fixture))
                nav.capture.screenshot.return_value=frame
                self.assertTrue(recover_known_overlay(nav,frame))
                self.assertTrue(recover_known_overlay(nav,frame))
                self.assertFalse(recover_known_overlay(nav,frame))
                self.assertEqual(nav.input.tap.call_count,2)

    def test_builder_collection_clears_known_announcement_before_reading_village(self):
        from coc_bot.builder_base.resources import ResourceCollector
        frame=cv2.imread(str(FIXTURES/'accounts/hammer-jam.png'))
        self.nav.capture.screenshot.return_value=frame
        clean=np.zeros_like(frame)
        r=SimpleNamespace(reader=Mock(),nav=self.nav,settle_village=Mock(return_value=clean))
        r.reader.reward_button.return_value=None
        collector=ResourceCollector(r)
        self.assertIs(collector.clear_overlay(frame),clean)
        self.nav.input.tap.assert_called_once()
        r.settle_village.assert_called_once_with(r.reader.home)

    def test_normal_frame_does_not_run_welcome_ocr_or_send_input(self):
        frame=np.zeros((1080,1920,3),np.uint8)
        with patch('coc_bot.progression.home._white_label',side_effect=AssertionError('unexpected OCR')):
            self.assertFalse(recover_known_overlay(self.nav,frame))
        self.nav.input.tap.assert_not_called()

    def test_unreadable_resources_retry_in_one_minute_but_no_loot_in_fifteen(self):
        r=BuilderBaseRunner.__new__(BuilderBaseRunner);r.config=self.config
        r.reader=Mock();r.reader.storage_tooltip_visible.return_value=False
        r.frame=Mock(return_value=np.zeros((1080,1920,3),np.uint8));r.attack=Mock()
        path=self.config.data_dir/'resources/builder.json'
        for capacities,balances,no_progress,delay in [({}, {'gold':10},0,60),
                ({'gold':1000,'elixir':1000},{'gold':10,'elixir':10},3,900)]:
            with self.subTest(delay=delay):
                r.reader.storage_capacities.return_value=capacities
                write(path,{'no_progress':no_progress})
                with patch('coc_bot.builder_base.resources.ResourceReader') as reader, \
                     patch('coc_bot.builder_base.runner.time.time',return_value=10000):
                    reader.return_value.balances.return_value=balances
                    r.refill_resources({})
                self.assertEqual(read(path,{})['retry_at'],10000+delay)
        r.attack.assert_not_called()

"""Watchdog acceptance: ineffective input, passive waits, Stop, bounded recovery."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np

from coc_bot.runtime.watchdog import ProgressWatchdog, StalledScreen, RecoveryBudget, RecoveryLimit
from coc_bot.adb.capture import ScreenCapture
from coc_bot.adb.input import InputController
from coc_bot.bot import DonationBot


class WatchdogTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config = SimpleNamespace(data_dir=Path(self.temp.name), account_tag='#TEST')
        self.now = 0
        self.stopped = False
        self.monitor = ProgressWatchdog(self.config, lambda:self.stopped, clock=lambda:self.now)
        self.frame = np.full((108,192,3), 100, np.uint8)

    def stall(self):
        self.monitor.observe(self.frame)
        for _ in range(3):self.monitor.action()
        self.now = 91

    def test_stall_saves_real_frame_and_remains_blocked_until_recovery(self):
        self.stall()
        with self.assertRaises(StalledScreen):self.monitor.observe(self.frame)
        self.assertTrue((self.config.data_dir/'verification/watchdog-stalled.png').exists())
        record=json.loads((self.config.data_dir/'verification/failures.json').read_text())[0]
        self.assertEqual(record['feature'],'watchdog')
        with self.assertRaises(StalledScreen):self.monitor.observe(self.frame+20)
        with self.monitor.recovery():self.monitor.observe(self.frame)
        self.monitor.observe(self.frame)
        self.assertFalse(self.monitor.blocked)

    def test_passive_village_or_battle_wait_never_trips(self):
        self.monitor.observe(self.frame)
        self.now=3600;self.monitor.observe(self.frame)
        self.assertFalse(self.monitor.blocked)
        self.monitor.action();self.now=7200;self.monitor.observe(self.frame)
        self.assertFalse(self.monitor.blocked)

    def test_spaced_anti_idle_actions_do_not_accumulate(self):
        self.monitor.observe(self.frame)
        for n in range(5):
            self.now=n*600;self.monitor.action();self.monitor.observe(self.frame)
        self.now+=91;self.monitor.observe(self.frame)
        self.assertFalse(self.monitor.blocked)

    def test_visible_progress_resets_deadline_but_small_clock_change_does_not(self):
        self.stall()
        changed=self.frame.copy();changed[20:90,20:90]=0
        self.monitor.observe(changed)
        self.assertEqual(self.monitor.actions,0)
        self.setUp_frame_for_small_change()

    def setUp_frame_for_small_change(self):
        self.monitor.reference=None;self.now=0;self.stall()
        changed=self.frame.copy();changed[0:2,0:2]=105
        with self.assertRaises(StalledScreen):self.monitor.observe(changed)

    def test_stop_prevents_detection_and_recovery_input(self):
        self.stall();self.stopped=True;self.monitor.observe(self.frame)
        bot=DonationBot.__new__(DonationBot);bot.should_stop=lambda:True
        bot._recover_once=Mock();bot._recover();bot._recover_once.assert_not_called()

    def test_recovery_is_suspended_and_next_action_gets_new_deadline(self):
        self.stall()
        with self.monitor.recovery():
            self.monitor.observe(self.frame);self.monitor.action()
        self.monitor.observe(self.frame);self.monitor.action()
        self.now+=100;self.monitor.observe(self.frame)
        self.assertFalse(self.monitor.blocked)

    def test_budget_survives_new_worker_and_expires(self):
        budget=lambda:RecoveryBudget(self.config,clock=lambda:self.now)
        self.assertEqual(budget().reserve('screen'),1)
        self.assertEqual(budget().reserve('adb'),2)
        with self.assertRaises(RecoveryLimit):budget().reserve('screen')
        self.now=901;self.assertEqual(budget().reserve('screen'),1)

    def test_corrupt_budget_and_future_attempts_cannot_bypass_limit(self):
        budget=RecoveryBudget(self.config,clock=lambda:self.now)
        budget.path.parent.mkdir(parents=True)
        for value in ('[]','{"attempts":["bad"]}','{"attempts":[NaN]}'):
            budget.path.write_text(value)
            with self.assertRaises(RecoveryLimit):budget.reserve('screen')
        budget.path.write_text('{"attempts":[999,999]}')
        with self.assertRaises(RecoveryLimit):budget.reserve('screen')

    def test_recovery_budget_blocks_third_navigation_and_unwinds_monitor(self):
        bot=DonationBot.__new__(DonationBot);bot.config=self.config;bot.should_stop=lambda:False
        bot.progress_watchdog=self.monitor;bot.recovery_budget=RecoveryBudget(self.config,clock=lambda:self.now)
        bot._recover_once=Mock();bot._recover();bot._recover()
        with self.assertRaises(RecoveryLimit):bot._recover()
        self.assertEqual(bot._recover_once.call_count,2)
        self.assertIsNone(self.monitor.status)
        self.assertEqual(self.monitor.suspended,0)

    def test_failed_recovery_cannot_reenter_itself(self):
        bot=DonationBot.__new__(DonationBot);bot.config=self.config;bot.should_stop=lambda:False
        bot.progress_watchdog=self.monitor;bot.recovery_budget=RecoveryBudget(self.config,clock=lambda:self.now)
        bot._recover_once=Mock(side_effect=RuntimeError('unknown screen'))
        with self.assertRaisesRegex(RuntimeError,'unknown screen'):bot._recover()
        self.assertEqual(bot._recover_once.call_count,1)
        self.assertEqual(self.monitor.suspended,0)

    def test_capture_observer_failure_is_not_retried_as_an_adb_failure(self):
        client=Mock(device='watchdog-test',stop_check=None)
        capture=ScreenCapture(client);capture.frame_observer=Mock(side_effect=StalledScreen('stalled'))
        with patch.object(capture,'_capture_png_exec_out',return_value=self.frame) as grab:
            with self.assertRaises(StalledScreen):capture.screenshot()
        grab.assert_called_once()

    def test_only_successful_real_inputs_count_and_stop_stays_responsive(self):
        client=Mock(stop_check=None);client.wm_size.return_value=(192,108)
        inp=InputController(client,delay_ms=(0,0));inp.action_listener=Mock()
        inp.tap(30,40);inp.swipe(0,0,10,10);inp.back();inp.tap_many([(10,10)],settle_ms=0)
        self.assertEqual(inp.action_listener.call_count,4)
        inp.dry_run=True;inp.tap(30,40);self.assertEqual(inp.action_listener.call_count,4)
        inp.dry_run=False;client.run_shell.side_effect=RuntimeError('adb failed')
        with self.assertRaises(RuntimeError):inp.tap(30,40)
        self.assertEqual(inp.action_listener.call_count,4)

    def test_verified_idle_chat_does_not_spend_recovery_budget(self):
        bot=DonationBot.__new__(DonationBot);bot._state='scan_chat';bot.last_screen='clan_chat'
        bot._unknown_streak=0;bot._recover=Mock();bot._state_entered=0
        bot.config=SimpleNamespace(state_watchdog_seconds=90)
        with patch('coc_bot.bot.time.monotonic',return_value=10000):bot._check_watchdog()
        bot._recover.assert_not_called()
        bot.last_screen='loading';bot._unknown_streak=2;bot.game_state=Mock()
        with patch('coc_bot.bot.time.monotonic',return_value=10000):bot._check_watchdog()
        bot._recover.assert_called_once()

    def recovery_bot(self):
        bot=DonationBot.__new__(DonationBot);bot.config=self.config;bot.should_stop=lambda:False
        bot._state='scan_chat';bot._stop_requested=False;bot.game_state=Mock()
        bot.navigator=Mock();bot.nav_input=Mock();bot.capture=Mock();bot.client=Mock()
        bot.capture.screenshot.return_value=self.frame
        bot.set_mode=Mock();bot._set_state=Mock();bot._has_donate_request=Mock()
        return bot

    def test_unknown_window_is_saved_and_never_receives_back_or_purchase_input(self):
        from coc_bot.vision.screens import ScreenType
        bot=self.recovery_bot();bot.navigator.classify.return_value=ScreenType.UNKNOWN
        bot.navigator.classifier.find_reload_game_button.return_value=None
        with patch('coc_bot.upgrades.runner.UpgradeRunner.state',return_value={}), \
             patch('coc_bot.builder_base.runner.pending',return_value=False), \
             patch('coc_bot.attack.recovery.pending',return_value=False), \
             patch('coc_bot.progression.home.recover_home_overlay',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'Неизвестное окно'):bot._recover_once()
        bot.nav_input.back.assert_not_called();bot.nav_input.tap.assert_not_called()
        self.assertTrue((self.config.data_dir/'verification/watchdog-unknown.png').exists())

    def test_known_overlay_is_closed_before_verifying_home(self):
        from coc_bot.vision.screens import ScreenType
        bot=self.recovery_bot();bot.navigator.classify.return_value=ScreenType.HOME
        with patch('coc_bot.upgrades.runner.UpgradeRunner.state',return_value={}), \
             patch('coc_bot.builder_base.runner.pending',return_value=False), \
             patch('coc_bot.attack.recovery.pending',return_value=False), \
             patch('coc_bot.progression.home.recover_home_overlay',side_effect=[True,False]) as overlay, \
             patch('coc_bot.bot.interrupted_sleep',return_value=False):
            bot._recover_once()
        self.assertEqual(overlay.call_count,2)
        bot.navigator.ensure_clan_chat.assert_called_once()
        bot.nav_input.back.assert_not_called()

    def test_builder_checkpoint_uses_existing_recovery_without_starting_new_attack(self):
        bot=self.recovery_bot()
        with patch('coc_bot.upgrades.runner.UpgradeRunner.state',return_value={}), \
             patch('coc_bot.builder_base.runner.pending',return_value=True), \
             patch('coc_bot.builder_base.runner.BuilderBaseRunner') as runner:
            bot._recover_once()
        runner.return_value.recover.assert_called_once()
        runner.return_value.run.assert_not_called()
        bot.nav_input.back.assert_not_called()

    def test_russian_recovery_state_is_visible_in_site_status(self):
        from coc_bot.control.event_labels import activity_label, present_event
        message='Восстанавливаю игру — попытка 1/2'
        self.assertEqual(activity_label(message),message)
        self.assertEqual(present_event('WARNING',message)['summary'],message)

    def test_programming_error_stops_with_original_cause_without_recovery(self):
        for error in (AttributeError('missing stop'),TypeError('wrong interface')):
            with self.subTest(error=type(error).__name__):
                bot=self.recovery_bot();bot.config.adb_device='program-error-test'
                bot._settings_stop_ready=lambda:False;bot._recover=Mock()
                bot.farmer=Mock();bot.tracker=Mock()
                bot._loop_tick=Mock(side_effect=error)
                with patch('coc_bot.builder_base.runner.pending',return_value=False), \
                     patch('coc_bot.attack.recovery.pending',return_value=False), \
                     patch('coc_bot.attack.recovery.recover_attack'), \
                     patch('coc_bot.runtime.screenshot_retention.prune_attack_diagnostics'):
                    with self.assertRaisesRegex(RuntimeError,'Ошибка программы') as result:bot._run_inner()
                self.assertIs(result.exception.__cause__,error)
                bot._recover.assert_not_called()
                bot.tracker.pause.assert_called_once()

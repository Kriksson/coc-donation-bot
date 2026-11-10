from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from coc_bot.bot import DonationBot
from coc_bot.runtime.tracker import RuntimeTracker


class FarmTriggerTests(TestCase):
    def test_config_mode_and_interval_are_strict_and_supported(self):
        from coc_bot.config import _farm_interval_seconds, _farm_trigger_mode
        self.assertEqual(_farm_trigger_mode('resources'),'resources')
        self.assertEqual(_farm_trigger_mode('interval'),'interval')
        self.assertEqual(_farm_interval_seconds(3600),3600)
        for mode in ('unknown',None,True):
            with self.assertRaises(ValueError):_farm_trigger_mode(mode)
        for seconds in (59,86401,True,3600.0):
            with self.assertRaises(ValueError):_farm_interval_seconds(seconds)

    def test_interval_tracker_uses_last_fought_battle_and_rejects_bad_timestamps(self):
        tracker=RuntimeTracker.__new__(RuntimeTracker)
        tracker.state=SimpleNamespace(last_farm_at=None)
        now=datetime(2026,11,9,tzinfo=timezone.utc)
        self.assertTrue(tracker.farm_interval_due(3600,now=now))
        tracker.state.last_farm_at=(now-timedelta(seconds=3599)).isoformat()
        self.assertFalse(tracker.farm_interval_due(3600,now=now))
        tracker.state.last_farm_at=(now-timedelta(seconds=3600)).isoformat()
        self.assertTrue(tracker.farm_interval_due(3600,now=now))
        for bad in ('not-a-date', (now+timedelta(seconds=1)).isoformat(), '2026-11-09T00:00:00'):
            tracker.state.last_farm_at=bad
            self.assertIsNone(tracker.farm_interval_due(3600,now=now))
        for interval in (59,86401,True):
            with self.assertRaises(ValueError):tracker.farm_interval_due(interval,now=now)

    def test_interval_single_account_due_never_reads_resource_observation(self):
        bot=SimpleNamespace(_farm_requested=False,
            config=SimpleNamespace(farm_enabled=True,farm_calibrated=True,dry_run=False,
                                   farm_trigger_mode='interval',farm_interval_seconds=3600),
            _farm_fail_cooldown_until=0.0,tracker=Mock(),_resource_farm_due=Mock())
        bot.tracker.farm_interval_due.return_value=False
        self.assertFalse(DonationBot._farm_due(bot))
        bot._resource_farm_due.assert_not_called()
        bot.tracker.farm_interval_due.return_value=True
        self.assertTrue(DonationBot._farm_due(bot))
        bot._resource_farm_due.assert_not_called()

    def test_fleet_due_overrides_single_account_trigger_mode(self):
        fleet_due=Mock(return_value=True)
        bot=SimpleNamespace(_farm_requested=False,
            config=SimpleNamespace(farm_enabled=True,farm_calibrated=True,dry_run=False,
                                   farm_trigger_mode='interval',farm_interval_seconds=3600),
            _farm_fail_cooldown_until=0.0,tracker=Mock(),_resource_farm_due=Mock(),
            _fleet_farm_due=fleet_due)
        self.assertTrue(DonationBot._farm_due(bot))
        fleet_due.assert_called_once_with()
        bot.tracker.farm_interval_due.assert_not_called()
        bot._resource_farm_due.assert_not_called()

    def test_interval_attack_refreshes_display_without_resource_trigger(self):
        from coc_bot.attack.farmer import FarmResult
        bot=SimpleNamespace(_state='scan_chat',_farm_requested=False,
            config=SimpleNamespace(farm_trigger_mode='interval',farm_calibrated=True,
                farm_engine='planner',farm_enabled=True,dry_run=False,donation_enabled=False,
                farm_retry_cooldown_seconds=300,account_tag='test'),
            _farm_due=Mock(return_value=True),_maybe_request_reinforcements=Mock(),
            should_stop=Mock(return_value=False),_stop_requested=False,
            _set_state=Mock(),set_mode=Mock(),game_state=Mock(),farmer=Mock(),
            tracker=Mock(),navigator=Mock(),_has_donate_request=Mock(),
            _resource_state=Mock(side_effect=AssertionError('interval mode must not load resource state')),
            _observe_resources=Mock(side_effect=AssertionError('interval mode must not observe resources')),
            _refresh_interval_balances=Mock(),
            _farm_fail_cooldown_until=0.0)
        bot.farmer.run_one_attack.return_value=FarmResult(True,'battle complete',True)
        with patch('coc_bot.attack.recovery.pending',return_value=None):
            self.assertTrue(DonationBot._maybe_run_farm(bot))
        bot._resource_state.assert_not_called()
        bot._observe_resources.assert_not_called()
        bot._refresh_interval_balances.assert_called_once_with()
        bot.tracker.mark_farm_success.assert_called_once_with()

    def test_display_balance_refresh_preserves_stop_and_ignores_failed_reads(self):
        from coc_bot.adb.client import AdbError,AdbStopped
        bot=SimpleNamespace(config=SimpleNamespace(),navigator=Mock(),
                            _resource_state=Mock(return_value={}),_save_resource_state=Mock())
        with patch('coc_bot.progression.resources.HomeResources') as reader:
            reader.return_value.observe.side_effect=AdbError('capture failed')
            DonationBot._refresh_interval_balances(bot)
            bot._save_resource_state.assert_not_called()
            reader.return_value.observe.side_effect=AdbStopped('stop')
            with self.assertRaises(AdbStopped):DonationBot._refresh_interval_balances(bot)
            bot._save_resource_state.assert_not_called()

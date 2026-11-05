import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from coc_bot.accounts.watch import DonorWatch
from coc_bot.bot import DonationBot


class DonorWatchTests(unittest.TestCase):
    def test_maintenance_does_not_complete_chat_window(self):
        now=[0]
        watch=DonorWatch(lambda:now[0])
        now[0]=300  # A Builder Base visit, without any chat.
        self.assertFalse(watch.ready(300))
        self.assertFalse(watch.funded())
        now[0]=600;watch.credit(300)
        self.assertFalse(watch.ready(300))  # Still below the two-to-one ratio.
        now[0]=900;watch.credit(300)
        self.assertTrue(watch.ready(300))

    def test_travel_and_other_accounts_are_repaid_before_more_maintenance(self):
        now=[0];watch=DonorWatch(lambda:now[0])
        now[0]=300;watch.credit(300)
        now[0]=500;watch.begin_visit()  # Travel and another account's checklist.
        self.assertFalse(watch.funded())
        self.assertFalse(watch.ready(300))  # Earlier chat cannot finish this visit.
        now[0]=600;watch.credit(100)
        self.assertTrue(watch.funded())
        self.assertFalse(watch.ready(300))
        now[0]=800;watch.credit(200)
        self.assertTrue(watch.ready(300))

    def test_invalid_credit_and_new_session_cannot_inherit_watch_time(self):
        now=[0];watch=DonorWatch(lambda:now[0])
        for invalid in (-1,True,float('nan'),float('inf'),'300'):
            watch.credit(invalid)
        self.assertEqual(watch.seconds,0)
        now[0]=10;watch.credit(100)
        self.assertEqual(watch.seconds,10)
        self.assertFalse(DonorWatch(lambda:now[0]).ready(300))

    def test_only_verified_chat_ticks_earn_time(self):
        for verified in (True,False):
            bot=DonationBot.__new__(DonationBot)
            bot._state='scan_chat';bot._stop_requested=False
            bot.should_stop=lambda:False
            bot.config=SimpleNamespace(scan_interval_ms=(0,0))
            bot._do_scan_chat=Mock(return_value=verified)
            bot._fleet_chat_seconds=Mock();bot.tracker=Mock()
            with patch('coc_bot.bot.time.monotonic',side_effect=[10,13]),\
                 patch('coc_bot.bot.interrupted_sleep',return_value=False):
                bot._chat_tick()
            if verified:bot._fleet_chat_seconds.assert_called_once_with(3)
            else:bot._fleet_chat_seconds.assert_not_called()

    def test_failed_or_interrupted_chat_does_not_earn_time(self):
        bot=DonationBot.__new__(DonationBot)
        bot._state='scan_chat';bot._stop_requested=False
        bot.should_stop=lambda:True
        bot.config=SimpleNamespace(scan_interval_ms=(0,0))
        bot._do_scan_chat=Mock(return_value=True)
        bot._fleet_chat_seconds=Mock();bot.tracker=Mock()
        with patch('coc_bot.bot.interrupted_sleep',return_value=True):bot._chat_tick()
        bot._fleet_chat_seconds.assert_not_called()
        bot._do_scan_chat.side_effect=ValueError('unverified')
        with self.assertRaises(ValueError):bot._chat_tick()
        bot._fleet_chat_seconds.assert_not_called()

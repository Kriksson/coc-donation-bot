import unittest
from unittest.mock import patch

from coc_bot.control.events import EventHistory
from coc_bot.control.event_labels import present_event


class ReadableEventsTests(unittest.TestCase):
    def test_failed_attack_explains_actual_gate_and_preserves_diagnostic(self):
        history=EventHistory()
        raw='Farm failed before deploy (Army preparation: Edit Army control was not verified) — retry cooldown 300s'
        history.append('WARNING',raw)
        event=history.since()['entries'][0]
        self.assertIn('Изменить армию',event['summary'])
        self.assertIn('5 мин',event['summary'])
        self.assertFalse(event['technical'])
        self.assertEqual(event['text'],raw)

    def test_repeated_errors_keep_a_stable_group_for_missed_socket_updates(self):
        history=EventHistory()
        with patch('coc_bot.control.events.time.monotonic',return_value=100):
            for _ in range(4):history.append('ERROR','No route to host')
        entries=history.since(1)['entries']
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]['id'],4)
        self.assertEqual(entries[0]['group'],1)
        self.assertEqual(entries[0]['count'],4)
        self.assertEqual(entries[0]['text'],'No route to host')

    def test_new_errors_stay_visible_and_raw_commands_are_technical(self):
        self.assertFalse(present_event('ERROR','A new unexpected failure')['technical'])
        self.assertTrue(present_event('DEBUG','ADB: shell input tap 1 2')['technical'])
        self.assertTrue(present_event('INFO','Screencap OK via pull png')['technical'])

    def test_confirmed_upgrade_is_named_and_resource_price_is_readable(self):
        event=present_event('INFO','Starting recommended buildings upgrade: Spell Factory for 600000 elixir')
        self.assertIn('Фабрика заклинаний',event['summary'])
        self.assertIn('600 000 эликсира',event['summary'])
        self.assertFalse(event['technical'])

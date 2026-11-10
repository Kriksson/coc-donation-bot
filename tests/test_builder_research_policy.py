import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from coc_bot.builder_base.progression import BuilderProgressionRunner
from coc_bot.builder_base.research import supports_progression_research
from coc_bot.builder_base.runner import BuilderBaseRunner
from coc_bot.upgrades.vision import Candidate


class BuilderResearchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.runner = BuilderProgressionRunner.__new__(BuilderProgressionRunner)
        self.runner.config = SimpleNamespace(
            upgrade_excluded_names='',
            builder_base_elixir_reserve=100_000,
        )
        self.runner._research_rows = {}

    def row(self, name='Sneaky Archer', target_level=9, cost=500_000,
            currency='elixir', point=(10, 20)):
        return {'name': name, 'target_level': target_level, 'cost': cost,
                'currency': currency, 'point': point}

    def candidate(self, row):
        return Candidate(row['name'], row['cost'], row['currency'], row['point'])

    def test_supported_rows_require_sneaky_archer_target_level_but_keep_night_witch(self):
        self.assertTrue(supports_progression_research(self.row(target_level=2)))
        self.assertTrue(supports_progression_research(self.row(target_level=9)))
        self.assertTrue(supports_progression_research(self.row(name='Night Witch', target_level=None)))
        for level in (None, 1, 31, True, '9'):
            with self.subTest(level=level):
                self.assertFalse(supports_progression_research(self.row(target_level=level)))
        self.assertFalse(supports_progression_research(self.row(name='Raged Barbarian', target_level=9)))
        self.assertFalse(supports_progression_research(self.row(currency='gems')))

    def test_eligibility_uses_fresh_row_level_and_rejects_unknown_or_unsupported_research(self):
        for level in (2, 9):
            row = self.row(target_level=level)
            self.runner._research_rows = {
                ('sneakyarcher', row['cost'], row['currency'], row['point']): row,
            }
            with self.subTest(level=level):
                self.assertIsNone(self.runner.eligibility(
                    'research', self.candidate(row), {'elixir': 1_000_000}, (1, 1)))

        invalid = self.row(target_level=None)
        self.runner._research_rows = {
            ('sneakyarcher', invalid['cost'], invalid['currency'], invalid['point']): invalid,
        }
        self.assertIsNotNone(self.runner.eligibility(
            'research', self.candidate(invalid), {'elixir': 1_000_000}, (1, 1)))

        raged = self.row(name='Raged Barbarian', target_level=9)
        self.runner._research_rows = {
            ('ragedbarbarian', raged['cost'], raged['currency'], raged['point']): raged,
        }
        self.assertIsNotNone(self.runner.eligibility(
            'research', self.candidate(raged), {'elixir': 1_000_000}, (1, 1)))

    def test_busy_lab_and_reserve_still_block_supported_target(self):
        row = self.row(target_level=9)
        self.runner._research_rows = {
            ('sneakyarcher', row['cost'], row['currency'], row['point']): row,
        }
        candidate = self.candidate(row)
        self.assertIsNotNone(self.runner.eligibility(
            'research', candidate, {'elixir': 1_000_000}, (0, 1)))
        self.assertIsNotNone(self.runner.eligibility(
            'research', candidate, {'elixir': 599_999}, (1, 1)))

    def test_each_inspection_replaces_target_level_evidence_from_its_frame(self):
        candidate = Candidate('Sneaky Archer', 500_000, 'elixir', (10, 20))
        row = self.row(target_level=9)
        self.runner.reader = Mock()
        self.runner.reader.rows.return_value = [row]
        self.runner.reader.availability.return_value = (1, 1)
        self.runner.reader.balances.return_value = {'elixir': 1_000_000}
        self.runner.reader.candidates.return_value = ([candidate], False)

        first = self.runner.inspect('research', object())
        self.assertIsNone(first['recommendations'][0]['skip'])

        unreadable = self.row(target_level=None)
        self.runner.reader.rows.return_value = [unreadable]
        second = self.runner.inspect('research', object())
        self.assertIn('target level is not verified', second['recommendations'][0]['skip'])

    def test_payment_receipt_must_match_the_fresh_row_target_before_purchase(self):
        candidate = Candidate('Sneaky Archer', 500_000, 'elixir', (10, 20))
        report = {'selected': {'target_level': 9}, 'balances': {'elixir': 1_000_000}}
        row = self.row(target_level=9, point=candidate.point)
        self.runner._research_rows = {
            ('sneakyarcher', row['cost'], row['currency'], row['point']): row,
        }
        self.runner.research_gems = 297
        receipt = self.runner.payment_receipt(
            'research', candidate, {'target_level': 9}, report, object())
        self.assertEqual(receipt, {
            'target_level': 9,
            'balances_before': {'elixir': 1_000_000},
            'gems_before': 297,
        })
        for selected, confirmed in ((8, 9), (None, 9)):
            with self.subTest(selected=selected, confirmed=confirmed):
                report['selected'] = {'target_level': selected}
                with self.assertRaisesRegex(ValueError, 'target changed'):
                    self.runner.payment_receipt(
                        'research', candidate, {'target_level': confirmed}, report, object())

        report['selected'] = {'target_level': 9}
        self.runner._research_rows[('sneakyarcher', 500_000, 'elixir', candidate.point)] = self.row(
            target_level=10, point=candidate.point)
        with self.assertRaisesRegex(ValueError, 'target changed'):
            self.runner.payment_receipt(
                'research', candidate, {'target_level': 9}, report, object())
        self.runner._research_rows[('sneakyarcher', 500_000, 'elixir', candidate.point)] = row

        report['selected'] = {'target_level': 9}
        for invalid in ({}, {'target_level': None}, {'target_level': 1}, {'target_level': 31},
                        {'target_level': True}):
            with self.subTest(invalid_modal=invalid):
                with self.assertRaisesRegex(ValueError, 'target level'):
                    self.runner.payment_receipt('research', candidate, invalid, report, object())

        self.runner.research_gems = None
        with self.assertRaisesRegex(ValueError, 'before-Elixir and gem'):
            self.runner.payment_receipt(
                'research', candidate, {'target_level': 9}, report, object())

        self.runner.research_gems = 297
        report['balances'] = {'elixir': None}
        with self.assertRaisesRegex(ValueError, 'before-Elixir and gem'):
            self.runner.payment_receipt(
                'research', candidate, {'target_level': 9}, report, object())

    def resource_demand(self, row, fresh=None):
        config = SimpleNamespace(
            builder_base_progression_enabled=True,
            builder_base_upgrades_enabled=False,
            builder_base_research_enabled=True,
            builder_base_elixir_reserve=0,
            upgrade_excluded_names='',
            account_tag='test',
        )
        base = BuilderBaseRunner.__new__(BuilderBaseRunner)
        base.config=config;base.capture=Mock();base.input=Mock();base.nav=Mock();base.stop=None
        base.frame=Mock(return_value=object());base.reader=Mock()
        base.reader.storage_capacities.return_value={}

        upgrade = Mock()
        frame=object()
        upgrade.open_menu.return_value=frame
        observation={'availability':(1,1),'balances':{'elixir':100}}
        upgrade.inspect.side_effect=[observation,observation]
        upgrade.scan.return_value={'complete':True,'rows':[row]}
        upgrade.find_row.return_value=(row,frame)
        upgrade.reader.rows.return_value=[fresh if fresh is not None else row]
        with patch('coc_bot.builder_base.progression.BuilderProgressionRunner',return_value=upgrade):
            return base.resource_demand()

    def test_resource_demand_uses_shared_policy_and_requires_fresh_matching_level(self):
        for level in (2,9):
            row=self.row(target_level=level,cost=500)
            with self.subTest(target=level):
                result=self.resource_demand(row)
                self.assertEqual(len(result['targets']),1)
                self.assertEqual(result['targets'][0]['target_level'],level)
        invalid=self.row(target_level=None,cost=500)
        self.assertEqual(self.resource_demand(invalid)['targets'],[])
        mismatch=self.row(target_level=9,cost=500)
        fresh=self.row(target_level=10,cost=500)
        self.assertEqual(self.resource_demand(mismatch,fresh)['targets'],[])


if __name__ == '__main__':
    unittest.main()

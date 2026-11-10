import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from coc_bot.control.resource_status import resource_status

class BuilderResourceStatusTests(unittest.TestCase):
    def test_builder_snapshot_stays_distinct_from_home_interval_and_account(self):
        with TemporaryDirectory() as folder:
            config=SimpleNamespace(data_dir=Path(folder),farm_enabled=True,farm_trigger_mode='interval',
                farm_interval_seconds=1200,farm_resource_start_percent=75,farm_resource_target_percent=95,
                builder_base_attacks_enabled=True,account_tag='#A')
            resources=config.data_dir/'resources';resources.mkdir()
            observation={'resources':['gold','elixir'],'balances':{'gold':700,'elixir':300},
                         'capacities':{'gold':1000,'elixir':1000}}
            saved={'account':'#A','observation':observation,'observed_at':123,'status':'refilling',
                   'message':'Refilling gold, elixir','retry_at':456}
            (resources/'builder.json').write_text(json.dumps(saved))
            result=resource_status(config,'builder')
            self.assertEqual(result['observation'],observation)
            self.assertEqual(result['trigger_mode'],'resources')
            self.assertEqual(result['status'],'refilling')
            self.assertEqual(result['retry_at'],456)
            self.assertIsNone(resource_status(config)['observation'])
            config.account_tag='#B'
            self.assertIsNone(resource_status(config,'builder')['observation'])

    def test_corrupt_builder_readings_do_not_break_status(self):
        with TemporaryDirectory() as folder:
            config=SimpleNamespace(data_dir=Path(folder),farm_enabled=True,
                farm_resource_start_percent=75,farm_resource_target_percent=95)
            (config.data_dir/'resources').mkdir()
            (config.data_dir/'resources/builder.json').write_text('{invalid')
            self.assertEqual(resource_status(config,'builder')['status'],'unverified')

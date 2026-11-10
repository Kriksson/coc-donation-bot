from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import json
import numpy as np

from coc_bot.runtime.battle_history import tracked_battle,note_battle,note_deployment,history
from coc_bot.control.task_status import task_status
from coc_bot.accounts.store import write


class BattleHistoryTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config=SimpleNamespace(data_dir=Path(self.temp.name),account_tag='#TEST',farm_enabled=True,farm_calibrated=True,
                                    farm_trigger_mode='interval',farm_interval_seconds=1200)
        self.owner=SimpleNamespace(config=self.config)
        self.frame=np.full((100,200,3),60,np.uint8)

    def test_verified_deployments_image_and_results_are_persisted_without_changing_frame(self):
        @tracked_battle('home')
        def run(owner):
            note_battle(entered_battle=True,army=[{'unit':'dragon','count':2}])
            note_deployment('dragon',2,points=[(40,40),(70,40)],frame=self.frame)
            note_battle(result_confirmed=True)
            return SimpleNamespace(success=True,reason='ok')
        original=self.frame.copy();result=run(self.owner);entry=history(self.config)[0]
        self.assertTrue(result.success);self.assertTrue(np.array_equal(self.frame,original))
        self.assertEqual(entry['deployments'],{'dragon':2});self.assertEqual(entry['status'],'returned')
        self.assertTrue(entry['result_confirmed']);self.assertIsNone(entry['loot'])
        self.assertTrue((self.config.data_dir/'battles'/f'{entry["id"]}.png').exists())

    def test_preparation_failure_is_not_reported_as_a_fought_battle(self):
        @tracked_battle('home')
        def run(owner):return SimpleNamespace(success=False,reason='army unavailable')
        run(self.owner);self.assertEqual(history(self.config),[])

    def test_interruption_keeps_original_error_and_is_not_a_victory(self):
        @tracked_battle('builder')
        def run(owner):
            note_battle(entered_battle=True)
            raise ValueError('lost frame')
        with self.assertRaisesRegex(ValueError,'lost frame'):run(self.owner,)
        entry=history(self.config)[0]
        self.assertEqual(entry['status'],'interrupted');self.assertFalse(entry['result_confirmed'])
        self.assertTrue(entry['recovery'])
        note_deployment('dragon')
        self.assertEqual(history(self.config)[0]['deployments'],{})

    def test_corrupt_history_or_other_account_cannot_interrupt_attack_or_be_overwritten(self):
        path=self.config.data_dir/'battles/history.json';path.parent.mkdir()
        @tracked_battle('home')
        def run(owner):
            note_battle(entered_battle=True)
            return SimpleNamespace(success=True,reason='ok')
        for value in ('{broken','{"version":1,"account":"#OTHER","entries":[]}'):
            path.write_text(value);self.assertTrue(run(self.owner).success)
            self.assertEqual(path.read_text(),value);self.assertEqual(history(self.config),[])

    def test_retention_only_removes_images_of_expired_reports(self):
        @tracked_battle('builder')
        def run(owner):
            note_deployment('baby_dragon',points=[(40,40)],frame=self.frame)
            return {'status':'returned'}
        with patch('coc_bot.runtime.battle_history.LIMIT',2):
            run(self.owner);first=history(self.config)[0]['id'];run(self.owner);run(self.owner)
        self.assertEqual(len(history(self.config)),2)
        self.assertFalse((self.config.data_dir/'battles'/f'{first}.png').exists())

    def test_status_explains_interval_and_read_only_queue(self):
        write(self.config.data_dir/'runtime_state.json',{'last_farm_at':'2026-11-10T10:00:00+00:00'})
        bot=SimpleNamespace(game_state=SimpleNamespace(state=SimpleNamespace(value='home')))
        active={'active':True,'state':'running','error':None}
        with patch('coc_bot.control.task_status.time.time',return_value=1794305400):
            result=task_status(self.config,active,bot,{}, {'status':'unverified'},None)
        self.assertIn('До следующей атаки',result['reason'])
        self.assertEqual(result['queue'][0]['task'],'farm')
        self.assertIn('повторного чтения',result['builder_reason'])
        self.assertFalse((self.config.data_dir/'visits/state.json').exists())
        bot.game_state.state.value='builder_base'
        result=task_status(self.config,active,bot,{}, {},None)
        self.assertIn('деревни строителя',result['reason'])
        active['active']=False;active['error']='Потерян ADB'
        result=task_status(self.config,active,bot,{}, {},None)
        self.assertIn('Потерян ADB',result['reason'])

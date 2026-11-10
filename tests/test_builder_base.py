import json
import tempfile
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from coc_bot.adb.client import AdbStopped
from coc_bot.builder_base.runner import BuilderBaseRunner, pending
from coc_bot.builder_base.frames import normalize_builder_frame
from coc_bot.builder_base.upgrades import eligibility
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.upgrades.vision import Candidate
from coc_bot.runtime.screenshot_retention import RetentionPolicy, prune_attack_diagnostics


class BuilderVisionTests(unittest.TestCase):
    def test_live_star_laboratory_confirmation_ocr_variant_keeps_price_and_resource_checks(self):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/lab-level-five-confirm-native.png'))
        reader=BuilderReader();candidate=Candidate('Star Laboratory',700_000,'elixir',(1,1))
        result=reader.confirmation(frame,candidate)
        self.assertIsNotNone(result)
        self.assertEqual((result['point'],result['name'],result['cost'],result['currency']),
                         ((round(frame.shape[1]*.504),round(frame.shape[0]*.875)),
                          'Star Laboratory',700_000,'elixir'))
        self.assertIsNone(reader.confirmation(frame,Candidate('Star Laboratory',70_000,'elixir',(1,1))))
        self.assertIsNone(reader.confirmation(frame,Candidate('Star Laboratory',700_000,'gold',(1,1))))

    def test_native_level_five_dialog_can_close_with_optional_candidate(self):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/lab-level-five-confirm-native.png'))
        reader=BuilderReader();candidate=Candidate('Star Laboratory',700000,'elixir',(1,2))
        point=reader.detail_close(frame,candidate)
        self.assertIsNotNone(point)
        self.assertEqual(reader.detail_close(frame),point)
        missing=frame.copy();missing[20:120,1550:1665]=0
        self.assertIsNone(reader.detail_close(missing,candidate))
        missing=frame.copy();missing[30:110,575:1250]=0
        self.assertIsNone(reader.detail_close(missing,candidate))

    def test_shared_transaction_closes_blocked_builder_dialog_without_payment(self):
        from coc_bot.upgrades.runner import UpgradeRunner
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/lab-upgrade-confirm.png'))
        candidate=Candidate('Star Laboratory',1,'elixir',(100,200))
        # The actual dialog costs 15,000; selecting a row may never authorize
        # payment when that independent price check fails.
        with tempfile.TemporaryDirectory() as folder:
            runner=UpgradeRunner.__new__(UpgradeRunner)
            runner.config=SimpleNamespace(upgrade_lab_priority=False)
            runner.path=Path(folder)/'state.json';runner.stop=None
            runner.reader=reader;runner.input=MagicMock();runner.capture=MagicMock()
            runner.capture.screenshot.return_value=frame
            runner.open_menu=MagicMock(return_value=frame)
            runner.close=MagicMock();runner.wait=MagicMock(return_value=False)
            runner.inspect=MagicMock(return_value={'kind':'buildings','availability':(1,1),
                'balances':{'elixir':100000},'section_complete':True,
                'recommendations':[candidate.public()|{'skip':None}]})
            with patch.object(reader,'menu_kind',return_value='buildings'), \
                 patch.object(reader,'active_names',return_value=[]):
                result=runner.run('buildings',execute=True)
            self.assertEqual(result['status'],'blocked')
            self.assertFalse(runner.path.exists())
            self.assertEqual(runner.input.tap.call_count,2)
            self.assertEqual(runner.input.tap.call_args.args,reader.detail_close(frame,candidate))
            runner.close.assert_called_once_with()
        self.assertIsNone(reader.detail_close(np.zeros_like(frame),candidate))

    @unittest.skipUnless(shutil.which('tesseract'),'OCR executable is required')
    def test_lab_confirmation_uses_native_title_without_guessing_name_or_price(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/lab-upgrade-confirm.png'))
        candidate=Candidate('Star Laboratory',15000,'elixir',(1,2))
        self.assertIsNotNone(reader.confirmation(frame,candidate))
        for name,cost,resource in [('Cannon',15000,'elixir'),('Star Laboratory',1500,'elixir'),
                                  ('Star Laboratory',15000,'gold'),('Star Laboratory',1,'gems')]:
            self.assertIsNone(reader.confirmation(frame,Candidate(name,cost,resource,(1,2))))
        masked=frame.copy();masked[145:200,325:735]=0
        self.assertIsNone(reader.confirmation(masked,candidate))
        self.assertIsNone(reader.confirmation((frame*.5).astype('uint8'),candidate))

    def test_daily_reward_close_needs_independent_bright_title_footer_and_close(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/daily-reward.png'))
        self.assertIsNotNone(reader.daily_reward_close(frame))
        self.assertIsNotNone(reader.daily_reward_claim(frame))
        gray=frame.copy();gray[400:480,550:790]=127
        self.assertIsNone(reader.daily_reward_claim(gray))
        for x0,y0,x1,y1 in ((720,130,1090,190),(590,925,1270,975),(1520,110,1610,190)):
            changed=frame.copy();changed[y0:y1,x0:x1]=0
            self.assertIsNone(reader.daily_reward_close(changed))
        self.assertIsNone(reader.daily_reward_close((frame*.5).astype('uint8')))
        claimed=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/daily-reward-claimed.png'))
        self.assertIsNotNone(reader.daily_reward_close(claimed))
        self.assertIsNone(reader.daily_reward_claim(claimed))

    def test_calendar_day_three_survives_a_different_village_background(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/daily-reward-day-three.png'))
        self.assertEqual(reader.daily_reward_close(frame),(1565,150))
        self.assertEqual(reader.daily_reward_claim(frame),(956,440))
        for x0,y0,x1,y1 in ((720,130,1090,190),(590,925,1270,975),(1520,110,1610,190)):
            changed=frame.copy();changed[y0:y1,x0:x1]=0
            self.assertIsNone(reader.daily_reward_close(changed))

    def test_free_boat_setup_requires_rebuild_title_description_and_free_price(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/setup-boat.png'))
        self.assertIsNotNone(reader.free_boat_confirmation(frame))
        for box in ((718,83,1136,144),(654,642,1215,683),(1743,400,1819,428)):
            bad=frame.copy();x0,y0,x1,y1=box;bad[y0:y1,x0:x1]=0
            self.assertIsNone(reader.free_boat_confirmation(bad))
        self.assertIsNone(reader.free_boat_confirmation((frame*.5).astype(np.uint8)))

    def frame(self, n):
        return cv2.imread(str(Path(__file__).parent/'fixtures/builder_base'/f'controls-{n}.png'))

    def test_battle_and_results_are_distinct(self):
        reader=BuilderReader()
        for n in (17,18,20):
            self.assertTrue(reader.battle(self.frame(n)),n)
            self.assertIsNone(reader.result_button(self.frame(n)))
        self.assertFalse(reader.battle(self.frame(23)))
        self.assertIsNotNone(reader.result_button(self.frame(23)))
        self.assertFalse(reader.battle(self.frame(14)))

    def test_army_preflight_rejects_missing_or_different_camp(self):
        reader=BuilderReader(); frame=self.frame(14)
        self.assertTrue(reader.supported_army(frame))
        frame[400:510,530:630]=0
        self.assertFalse(reader.supported_army(frame))

    def test_baby_dragon_preflight_requires_four_single_camps_and_battle_machine(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/army-baby-dragon-menu.png'))
        self.assertEqual(reader.supported_army_kind(frame),'baby_dragon')
        self.assertTrue(reader.attack_menu(frame))
        # Losing any one camp, its x1 marker, or the hero card invalidates the
        # exact inspected composition; a dim transition also cannot pass.
        for box in ((435,421,545,523),(548,421,657,523),(660,421,770,523),
                    (772,421,883,523),(304,410,432,525)):
            changed=frame.copy();x0,y0,x1,y1=box;changed[y0:y1,x0:x1]=0
            self.assertIsNone(reader.supported_army_kind(changed),box)
        self.assertIsNone(reader.supported_army_kind((frame*.5).astype(np.uint8)))

    def test_baby_dragon_battle_cards_need_current_troop_art(self):
        reader=BuilderReader();frame=self.frame(17)
        # This is a verified Battle Machine plus Night Witch attack. The Baby
        # Dragon menu receipt cannot relabel those troop pictures by slot.
        cards=reader.cards(frame,army='baby_dragon')
        self.assertEqual([c['unit'] for c in cards],['battle_machine'])
        self.assertEqual(reader.cards(frame,army='unknown'),[])
        self.assertTrue(reader.battle_army_ready('night_witch'))

    def test_baby_dragon_cards_use_live_art_and_missing_ability_stays_unauthorized(self):
        raw=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/battle-baby-dragon-predeploy-capped.png'))
        frame=normalize_builder_frame(raw)
        reader=BuilderReader()
        cards=reader.cards(frame,army='baby_dragon')
        self.assertEqual([(c['slot'],c['unit']) for c in cards],
                         [(0,'battle_machine'),(1,'baby_dragon'),(2,'baby_dragon'),
                          (3,'baby_dragon'),(4,'baby_dragon')])
        self.assertFalse(any(c['deployed'] for c in cards))
        self.assertFalse(any(c['ability_ready'] for c in cards))
        self.assertTrue(reader.battle_army_ready('baby_dragon'))
        self.assertFalse((Path(__file__).parents[1]/'src/coc_bot/builder_base/assets/baby_dragon_ability_ready.png').exists())

        # A Night Witch control cannot be relabeled from the menu army receipt.
        control=reader.cards(normalize_builder_frame(self.frame(17)),army='baby_dragon')
        self.assertEqual([c['unit'] for c in control],['battle_machine'])
        self.assertFalse(any(c['unit']=='baby_dragon' for c in control))

        # Masking one portrait removes exactly that card while other live cards remain.
        masked=frame.copy();masked[934:1036, round(frame.shape[1]*.249):round(frame.shape[1]*.290)]=0
        self.assertEqual([c['slot'] for c in reader.cards(masked,army='baby_dragon')],[0,1,3,4])

        # The troop template is head-only: level digits and the lower card/ability area
        # may change without affecting troop identity.
        changing_badge=frame.copy()
        x0,x1=round(frame.shape[1]*.155),round(frame.shape[1]*.222)
        changing_badge[round(frame.shape[0]*.92):round(frame.shape[0]*.99),x0:x1]=0
        self.assertEqual([c['slot'] for c in reader.cards(changing_badge,army='baby_dragon')],
                         [0,1,2,3,4])

        # Empty card slots are rejected even while the native battle HUD remains.
        empty=frame.copy();empty[round(frame.shape[0]*.80):]=0
        self.assertEqual(reader.cards(empty,army='baby_dragon'),[])

        # Readiness needs troop art, but never requires or invents ability art.
        with tempfile.TemporaryDirectory() as directory:
            assets=Path(directory)
            (assets/'baby_dragon.png').write_bytes((Path(__file__).parents[1]/'src/coc_bot/builder_base/assets/baby_dragon.png').read_bytes())
            with patch('coc_bot.builder_base.vision.ASSETS',assets):
                self.assertTrue(BuilderReader().battle_army_ready('baby_dragon'))
                (assets/'baby_dragon.png').unlink()
                self.assertFalse(BuilderReader().battle_army_ready('baby_dragon'))

    def test_deployed_baby_dragon_cards_keep_face_and_green_health_receipts(self):
        reader=BuilderReader()
        expected=((0,0,0,0),(1,0,0,0),(1,1,0,0),(1,1,1,0),(1,1,1,1))
        for deployed_count, states in enumerate(expected):
            with self.subTest(deployed=deployed_count):
                frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base'/
                                     f'battle-baby-dragon-deployed-{deployed_count:02}.png'))
                cards=reader.cards(frame,army='baby_dragon')
                dragon_cards={c['slot']:c for c in cards if c['unit']=='baby_dragon'}
                self.assertEqual(sorted(dragon_cards),[1,2,3,4])
                for slot,state in zip((1,2,3,4),states):
                    self.assertEqual(dragon_cards[slot]['deployed'],bool(state),slot)
                self.assertFalse(any(c['ability_ready'] for c in dragon_cards.values()))

        deployed=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/'
                                'battle-baby-dragon-deployed-04.png'))
        h,w=deployed.shape[:2]
        for slot,cx in zip((1,2,3,4),(.189,.268,.347,.426)):
            with self.subTest(erased_portrait_slot=slot):
                masked=deployed.copy();x=round(w*cx)
                # Preserve raised-number and health bars while erasing the
                # actual face region: colored UI alone must never identify a troop.
                masked[round(h*.88):round(h*.97),x-round(w*.025):x+round(w*.025)]=0
                cards=reader.cards(masked,army='baby_dragon')
                self.assertNotIn(slot,[c['slot'] for c in cards if c['unit']=='baby_dragon'])

        # Flat synthetic blue/green bands on a different troop-art control do
        # not manufacture Baby Dragon identities without a matching face.
        control=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/controls-17.png'))
        h,w=control.shape[:2]
        for cx in (.189,.268,.347,.426):
            cv2.rectangle(control,(round(w*(cx-.01)),round(h*.796)),
                          (round(w*(cx+.025)),round(h*.822)),(255,0,0),-1)
            cv2.rectangle(control,(round(w*(cx-.025)),round(h*.831)),
                          (round(w*(cx+.025)),round(h*.858)),(0,255,0),-1)
        self.assertFalse(any(c['unit']=='baby_dragon' for c in reader.cards(control,army='baby_dragon')))

    def test_builder_deployment_points_follow_observed_outer_red_boundary(self):
        from coc_bot.builder_base.runner import deployment_points
        raw=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/battle-baby-dragon-predeploy-capped.png'))
        frame=normalize_builder_frame(raw)
        points=deployment_points(frame)
        self.assertGreaterEqual(len(points),4)
        self.assertTrue(all(25 < x < 300 and 270 < y < 450 for x,y in points))
        self.assertLess(abs(points[0][0]-82),8)
        self.assertLess(abs(points[0][1]-427),8)

        # No boundary or battlefield means the observed-edge path authorizes nothing.
        empty=np.zeros_like(frame)
        self.assertEqual(deployment_points(empty),[])
        control=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/controls-17.png'))
        self.assertEqual(deployment_points(normalize_builder_frame(control)),[])
        result=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/result-capped.png'))
        self.assertEqual(deployment_points(normalize_builder_frame(result)),[])

    def test_reward_requires_both_headings_and_button(self):
        reader=BuilderReader();frame=self.frame(28)
        self.assertIsNotNone(reader.reward_button(frame))
        frame[550:605]=0
        self.assertIsNone(reader.reward_button(frame))
        self.assertIsNone(reader.reward_button(self.frame(23)))

    def test_cards_and_second_stage_survivors(self):
        reader=BuilderReader()
        first=reader.cards(self.frame(17))
        self.assertEqual(len(first),7)
        self.assertFalse(any(c['deployed'] for c in first))
        active=reader.cards(self.frame(18))
        self.assertEqual(len(active),7)
        self.assertTrue(all(c['deployed'] for c in active))
        survivors=reader.cards(self.frame(20))
        self.assertEqual([c['slot'] for c in survivors],[0,2,3,5,6,7])
        self.assertFalse(any(c['deployed'] for c in survivors))
        self.assertEqual(survivors[0]['unit'],'battle_copter')

    def test_dimmed_home_controls_do_not_establish_village(self):
        reader=BuilderReader();frame=self.frame(24)
        self.assertTrue(reader.home(frame))
        self.assertFalse(reader.home((frame*.5).astype(np.uint8)))

    def test_current_dim_builder_hud_is_distinct_from_home_and_modal_screens(self):
        reader=BuilderReader()
        root=Path(__file__).parent/'fixtures'
        builder=cv2.imread(str(root/'builder_base/home-dark-scene.png'))
        self.assertTrue(reader.home(builder))
        self.assertFalse(reader.home((builder*.5).astype(np.uint8)))

        for path in (root/'progression/home-preview-red-roof.png',
                     root/'progression/laboratory-confirmation.png',
                     root/'builder_base/lab-upgrade-confirm.png'):
            with self.subTest(screen=path.name):
                self.assertFalse(reader.home(cv2.imread(str(path))))

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR executable is required')
    def test_gold_confirmation_requires_matching_price_name_and_resource(self):
        reader=BuilderReader();frame=self.frame(8)
        candidate=Candidate('Elixir Collector',5000,'gold',(1,2))
        # The saved title template must rescue this stylized heading when OCR
        # misses it, while amount and currency remain independently checked.
        with patch.object(reader,'white_text',return_value=''):
            self.assertIsNotNone(reader.confirmation(frame,candidate))
        for name,price,currency in [('Elixir Collector',50000,'gold'),('Gold Mine',5000,'gold'),
                                     ('Elixir Collector',5000,'gems')]:
            with patch.object(reader,'white_text',return_value=''):
                self.assertIsNone(reader.confirmation(frame,Candidate(name,price,currency,(1,2))))

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR executable is required')
    def test_early_barracks_confirmation_requires_elixir_price_and_name(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/barracks-elixir-confirm.png'))
        self.assertIsNotNone(reader.confirmation(frame,Candidate('Builder Barracks',4000,'elixir',(1,2))))
        for name,price,resource in [('Builder Barracks',4000,'gold'),('Builder Barracks',400,'elixir'),
                                    ('Star Laboratory',4000,'elixir'),('Builder Barracks',4000,'gems')]:
            self.assertIsNone(reader.confirmation(frame,Candidate(name,price,resource,(1,2))))

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR executable is required')
    def test_early_menu_prioritizes_lab_and_excludes_unbuilt_rows(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/early-upgrade-menu.png'))
        rows,complete=reader.candidates(frame)
        self.assertEqual([(c.name,c.cost,c.currency) for c in rows],
                         [('Star Laboratory',15000,'elixir'),('Builder Barracks',4000,'elixir')])
        self.assertFalse(complete)
        frame[0:160,1240:1345]=0  # Home menu headings alone cannot establish Builder Base.
        self.assertEqual(reader.candidates(frame),([],False))

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR executable is required')
    def test_full_row_parser_preserves_the_existing_night_witch_recommendation(self):
        reader=BuilderReader()
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/progression-research.png'))
        rows,_=reader.candidates(frame)
        from coc_bot.upgrades.vision import compact
        self.assertTrue(any(compact(c.name)=='nightwitch' and c.cost==2500000 and c.currency=='elixir' for c in rows))

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR executable is required')
    def test_research_confirmation_and_running_modal(self):
        reader=BuilderReader()
        root=Path(__file__).parent/'fixtures/builder_base'
        frame=cv2.imread(str(root/'progression-research-confirm.png'))
        c=Candidate('Night Witch',2500000,'elixir',(1,2))
        self.assertIsNotNone(reader.confirmation(frame,c))
        for name,price,resource in [('Night Witch',250000,'elixir'),('Night Witch',2500000,'gems'),
                                    ('Baby Dragon',2500000,'elixir')]:
            self.assertIsNone(reader.confirmation(frame,Candidate(name,price,resource,(1,2))))
        frame[770:810,400:600]=0
        self.assertIsNone(reader.confirmation(frame,c))
        running=cv2.imread(str(root/'progression-research-after.png'))
        self.assertIsNotNone(reader.detail_close(running))
        self.assertTrue(reader.running_detail(running,c))
        self.assertIsNone(reader.confirmation(running,c))


class BuilderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config=SimpleNamespace(data_dir=Path(self.temp.name),dry_run=False,
            builder_base_builders_reserved=0,builder_base_gold_reserve=100_000,
            builder_base_elixir_reserve=100_000,upgrade_excluded_names='')

    def runner(self, stop=None):
        return BuilderBaseRunner(self.config,MagicMock(),MagicMock(),MagicMock(),MagicMock(),stop)

    def test_policy_reserves_busy_builders_and_no_gems(self):
        c=Candidate('Elixir Collector',5000,'gold',(1,2))
        self.assertIsNone(eligibility(self.config,c,{'gold':200_000},(1,2)))
        for availability in (None,(0,2),(2,6)):
            self.assertIsNotNone(eligibility(self.config,c,{'gold':200_000},availability))
        self.assertIsNotNone(eligibility(self.config,c,{'gold':104_999},(2,2)))
        for name,resource in [('Builder Hall','gold'),('Battle Machine','elixir'),('Wall','gold'),('Cannon','gems')]:
            self.assertIsNotNone(eligibility(self.config,Candidate(name,1,resource,(1,2)),{resource:200_000},(2,2)))

    def test_early_army_buildings_use_the_correct_resource_reserve(self):
        for name,resource in [('Builder Barracks','elixir'),('Star Laboratory','gold')]:
            candidate=Candidate(name,4000,resource,(1,2))
            self.assertIsNone(eligibility(self.config,candidate,{resource:104_000},(1,1)))
            self.assertIsNotNone(eligibility(self.config,candidate,{resource:103_999},(1,1)))
            self.assertIsNotNone(eligibility(self.config,candidate,{resource:104_000},(0,1)))

    def test_stop_after_screenshot_prevents_next_tap(self):
        stopped=[False];r=self.runner(lambda:stopped[0])
        r.capture.capture.screenshot.side_effect=lambda:stopped.__setitem__(0,True)
        with self.assertRaises(AdbStopped):r.frame()
        with self.assertRaises(AdbStopped):r.tap((1,2))
        r.input.tap.assert_not_called()

    def test_practice_never_enters_or_spends(self):
        self.config.dry_run=True;r=self.runner()
        self.assertEqual(r.run()['status'],'practice_skipped')
        r.capture.capture.screenshot.assert_not_called();r.input.tap.assert_not_called()

    def test_recovery_observes_battle_without_deployment(self):
        r=self.runner();r.phase('battle');r.reader=MagicMock();r.reader.reward_button.return_value=None
        r.reader.battle.return_value=True
        r.watch_battle=MagicMock();r.finish=MagicMock()
        r.recover();r.watch_battle.assert_called_once_with(deploy=False)
        r.finish.assert_called_once();self.assertTrue(pending(self.config))

    def test_corrupt_journal_blocks_unsafe_home_recovery(self):
        p=self.config.data_dir/'builder_base/visit.json';p.parent.mkdir();p.write_text('')
        with self.assertRaises(RuntimeError):pending(self.config)

    def test_builder_retention_protects_pending_and_unknown_files(self):
        r=self.runner();r.phase('battle')
        p=self.config.data_dir/'debug/builder-base'/('a'*32);p.mkdir(parents=True)
        shot=p/'001-stage-view.png';shot.write_bytes(b'evidence')
        policy=RetentionPolicy(days=0,keep_recent=0,max_groups=0)
        self.assertTrue(prune_attack_diagnostics(self.config.data_dir,policy=policy)['skipped_pending'])
        r.record.pop('phase');r.phase('')
        keep=p/'human-review.txt';keep.write_text('keep')
        prune_attack_diagnostics(self.config.data_dir,policy=policy);self.assertTrue(shot.exists())
        keep.unlink();prune_attack_diagnostics(self.config.data_dir,policy=policy)
        self.assertFalse(shot.exists())

    def test_scheduler_defers_to_donations_and_future_visit(self):
        from coc_bot.bot import DonationBot
        b=DonationBot.__new__(DonationBot);b.config=self.config
        b.config.builder_base_attacks_enabled=True;b.config.builder_base_upgrades_enabled=False
        b._state='scan_chat';b.should_stop=MagicMock(return_value=False)
        b.capture=MagicMock();b._has_donate_request=MagicMock(return_value=True)
        with patch('coc_bot.builder_base.runner.BuilderBaseRunner') as runner:
            self.assertFalse(b._maybe_run_builder_base());runner.assert_not_called()
            b._has_donate_request.return_value=False
            with patch('coc_bot.builder_base.runner.state',return_value={'next_visit_at':1e20}):
                self.assertFalse(b._maybe_run_builder_base());runner.assert_not_called()

    def test_settings_restart_waits_for_builder_visit_but_stop_does_not(self):
        from coc_bot.bot import DonationBot
        b=DonationBot.__new__(DonationBot);b._finish_action_requested=True;b._state='builder_base'
        self.assertFalse(b._settings_stop_ready())
        b._state='scan_chat';self.assertTrue(b._settings_stop_ready())

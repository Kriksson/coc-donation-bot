from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from coc_bot.attack.army import (ArmyCard, UnitCatalog, agree_cards, card_boxes,
                                read_army, resolve_live_card, resolve_just_depleted)
from coc_bot.attack.automatic import automatic_plan, scan_army
from coc_bot.attack.reinforcements import CLAN_CASTLE, castle_card_quantity
from coc_bot.attack.executor import VerifiedExecutor
from coc_bot.attack.plans import ArmyEntry, AttackPlan, MapPoint, PlanStep
from coc_bot.attack.projection import Projection
from coc_bot.adb.client import AdbStopped


FIXTURES = Path(__file__).parent/'fixtures/attack'


def battle(name='clan-castle-bar'):
    row = cv2.imread(str(FIXTURES/(name+'.png')))
    frame = np.zeros((1048,1853,3), np.uint8)
    frame[850:] = row
    return frame


def castle(quantity=1, stable=True):
    return ArmyCard('castle', (428,860,130,170), CLAN_CASTLE, 'siege', quantity, stable=stable)


def troop(name='electro_dragon', quantity=11):
    return ArmyCard('troop', (130,867,130,170), name, 'troop', quantity, stable=True)


def darkened(cell):
    return cv2.cvtColor((cv2.cvtColor(cell,cv2.COLOR_BGR2GRAY)*.45).astype(np.uint8),
                        cv2.COLOR_GRAY2BGR)


class CastleRecognitionTests(TestCase):
    def setUp(self):
        self.frame = battle()
        self.cell = self.frame[860:1030,428:558].copy()
        self.catalog = UnitCatalog(Path('missing-icon-pack'))

    def test_native_available_card_needs_no_calibration_or_ocr(self):
        with patch('coc_bot.attack.army.visible_card_boxes',return_value=[castle().box]), \
                patch('coc_bot.attack.army.read_badge',side_effect=AssertionError('No xN badge')):
            first = read_army(self.frame,'battle',self.catalog)
            second = read_army(self.frame,'battle',self.catalog)
        observed = agree_cards(first,second)
        self.assertEqual([(c.unit_id,c.kind,c.quantity,c.stable) for c in observed],
                         [(CLAN_CASTLE,'siege',1,True)])
        self.assertEqual(resolve_live_card(self.frame,self.catalog,CLAN_CASTLE).quantity,1)

    def test_resized_or_moved_card_is_found_from_current_pixels(self):
        selected=cv2.copyMakeBorder(self.cell,5,5,5,5,cv2.BORDER_CONSTANT,value=(255,255,255))
        self.assertEqual(castle_card_quantity(selected),1)
        for scale in (.65,.8,1.,1.3):
            with self.subTest(scale=scale):
                moved = self.frame.copy()
                moved[860:1030,428:558] = 0
                moved[860:1030,1250:1380] = self.cell
                moved = cv2.resize(moved,None,fx=scale,fy=scale)
                card = resolve_live_card(moved,self.catalog,CLAN_CASTLE)
                self.assertEqual(card.quantity,1)
                self.assertLess(abs(card.box[0]-1250*scale),8)

    def test_emblem_is_not_the_identity_and_blank_cyan_card_is_rejected(self):
        from coc_bot.attack.reinforcements import badge_reference
        _,mask = badge_reference()
        changed = self.cell.copy()
        # The reference was cropped at (452,899) in the source frame.
        badge = changed[39:118,24:104]
        badge[mask==0] = (20,180,30)
        self.assertEqual(castle_card_quantity(changed),1)
        self.assertIsNone(castle_card_quantity(np.full_like(self.cell,(210,180,30))))

    def test_simulated_depletion_is_zero_and_occlusion_never_means_available(self):
        depleted = darkened(self.cell)
        self.assertEqual(castle_card_quantity(depleted),0)
        covered = self.cell.copy();covered[30:120] = 0
        self.assertIsNone(castle_card_quantity(covered))
        self.assertIsNone(castle_card_quantity(np.zeros_like(self.cell)))
        frame = self.frame.copy();frame[860:1030,428:558] = depleted
        self.assertEqual(resolve_live_card(frame,self.catalog,CLAN_CASTLE).quantity,0)
        self.assertEqual(resolve_just_depleted(frame,self.catalog,castle()).quantity,0)
        with self.assertRaises(ValueError):resolve_just_depleted(self.frame,self.catalog,castle())

    def test_other_army_cards_and_ambiguous_castles_never_authorize_deployment(self):
        for name in ('siege-bar','starter-bar'):
            frame = battle(name)
            for x,y,w,h in card_boxes(frame,'battle'):
                with self.subTest(name=name,box=(x,y,w,h)):
                    self.assertIsNone(castle_card_quantity(frame[y:y+h,x:x+w]))
            with self.assertRaises(ValueError):resolve_live_card(frame,self.catalog,CLAN_CASTLE)
        duplicate = self.frame.copy();duplicate[860:1030,1250:1380] = self.cell
        with self.assertRaises(ValueError):resolve_live_card(duplicate,self.catalog,CLAN_CASTLE)

    def test_old_artwork_reference_cannot_grant_availability(self):
        catalog = Mock()
        catalog.identify.return_value = (CLAN_CASTLE,'siege',1.,1.)
        with patch('coc_bot.attack.army.visible_card_boxes',return_value=[castle().box]), \
                patch('coc_bot.attack.army.read_badge',return_value=1):
            cards = read_army(np.zeros_like(self.frame),'battle',catalog)
        self.assertIsNone(cards[0].quantity)

    def test_native_siege_selector_castle_reaches_the_farming_plan(self):
        frame = battle('clan-castle-toggle-bar')
        observed = agree_cards(read_army(frame,'battle',self.catalog),
                               read_army(frame,'battle',self.catalog))
        castles = [c for c in observed if c.unit_id == CLAN_CASTLE]
        self.assertEqual(len(castles),1)
        self.assertEqual((castles[0].quantity,castles[0].stable),(1,True))
        for progression in (False,True):
            plan = automatic_plan([troop(),*castles],progression=progression)
            drops = [s for s in plan.steps if s.unit_id == CLAN_CASTLE]
            self.assertEqual([(s.action,s.quantity) for s in drops],[('deploy_point',1)])
        for x,y,w,h in card_boxes(frame,'battle'):
            if x == castles[0].box[0]:continue
            self.assertIsNone(castle_card_quantity(frame[y:y+h,x:x+w]))
        for scale in (.65,.8,1.,1.3):
            with self.subTest(scale=scale):
                live = resolve_live_card(cv2.resize(frame,None,fx=scale,fy=scale),
                                         self.catalog,CLAN_CASTLE)
                self.assertEqual(live.quantity,1)

    def test_siege_selector_does_not_prove_availability_or_clan_identity(self):
        cell = battle('clan-castle-toggle-bar')[860:1030,287:418].copy()
        from coc_bot.attack.reinforcements import badge_reference
        _,mask = badge_reference('image_toggle')
        changed = cell.copy()
        changed[39:118,24:104][mask==0] = (30,180,20)
        self.assertEqual(castle_card_quantity(changed),1)
        depleted = darkened(cell)
        # The selector can stay colored after the shield itself is unavailable.
        depleted[116:,51:] = cell[116:,51:]
        self.assertEqual(castle_card_quantity(depleted),0)
        for box in ((39,118,24,104),(20,37,20,111),(131,150,20,39)):
            top,bottom,left,right=box
            covered=cell.copy();covered[top:bottom,left:right]=0
            self.assertIsNone(castle_card_quantity(covered))


class CastlePlanTests(TestCase):
    def test_all_farming_families_deploy_once_before_heroes(self):
        for name,progression in (('electro_dragon',False),('dragon',True),('barbarian',True)):
            with self.subTest(name=name):
                hero = ArmyCard('h',(600,860,130,170),'king','hero',1,stable=True)
                plan = automatic_plan([troop(name),hero,castle()],progression=progression)
                drops = [s for s in plan.steps if s.unit_id==CLAN_CASTLE]
                self.assertEqual(len(drops),1)
                self.assertEqual((drops[0].action,drops[0].quantity),('deploy_point',1))
                self.assertLess(plan.steps.index(drops[0]),next(i for i,s in enumerate(plan.steps) if s.unit_id=='king'))

    def test_empty_uncertain_and_absent_castles_do_not_block_attacks(self):
        for progression in (False,True):
            for card in (castle(0),castle(None),castle(1,False),castle(2),castle(True)):
                with self.subTest(progression=progression,card=card):
                    plan = automatic_plan([troop(),card],progression=progression)
                    self.assertFalse(any(s.unit_id==CLAN_CASTLE for s in plan.steps))
            self.assertEqual(len(automatic_plan([troop()],progression=progression).steps),1)

    def test_castle_cannot_be_double_deployed_alongside_a_siege(self):
        siege = replace(castle(),unit_id='flame_flinger')
        for progression in (False,True):
            with self.assertRaises(ValueError):
                automatic_plan([troop(),castle(),siege],progression=progression)
        plan = automatic_plan([troop(),castle()])
        with self.assertRaises(ValueError):
            replace(plan,army=plan.army+(ArmyEntry('flame_flinger','siege',1,True),)).validate()

    def test_scan_omits_unavailable_castle_without_selecting_any_card(self):
        for quantity in (0,None,1):
            session=Mock();session.config=SimpleNamespace(progression_enabled=False)
            session.client.stop_check=lambda:False
            session.capture.screenshot.return_value=battle()
            with patch('coc_bot.attack.automatic.BattleFrameGate'), \
                    patch('coc_bot.attack.automatic.read_army',return_value=[troop(),castle(quantity)]):
                cards=scan_army(session,Mock())
            self.assertEqual(CLAN_CASTLE in {c.unit_id for c in cards},quantity==1)
            session.input.tap.assert_not_called()


class CastleExecutorTests(TestCase):
    def executor(self, root, name='clan-castle-bar'):
        session=Mock();session.config=SimpleNamespace(data_dir=Path(root),adb_device='test')
        session.client.stop_check=lambda:False
        frame=battle(name)
        plan=automatic_plan([troop(quantity=1),castle()])
        # Map onto a safe visible portion of a synthetic measured battlefield.
        projection=Projection(((900,50),(1500,400),(900,750),(300,400)))
        exe=VerifiedExecutor(session,plan,projection,frame,UnitCatalog(Path(root)/'icons'))
        exe.frame=Mock(return_value=frame)
        exe.position=Mock(return_value=(frame,(400,400)))
        exe.target=Mock(return_value=(400,400))
        return exe,session,frame

    def test_selector_variant_requires_native_depletion_after_one_map_tap(self):
        for consumed in (False,True):
            with self.subTest(consumed=consumed),TemporaryDirectory() as root:
                exe,session,frame=self.executor(root,'clan-castle-toggle-bar')
                exe.plan=AttackPlan((ArmyEntry(CLAN_CASTLE,'siege',1,True),),
                    (PlanStep('deploy_point',CLAN_CASTLE,1,(MapPoint(.055,.5),)),))
                after=frame.copy()
                if consumed:
                    cell=frame[860:1030,287:418]
                    depleted=darkened(cell)
                    depleted[116:,51:]=cell[116:,51:]
                    after[860:1030,287:418]=depleted
                exe.frame=Mock(side_effect=[frame,after,after])
                with patch('coc_bot.attack.executor.selected_card',return_value=True):
                    result=exe.run()
                session.input.tap.assert_called_once_with(400,400,jitter=0)
                self.assertEqual(result.success,consumed)
                self.assertEqual(result.verified_taps,int(consumed))
                self.assertEqual(result.uncertain_tap,not consumed)

    def test_available_castle_is_tapped_once_and_requires_depletion(self):
        for after in (0,1):
            with self.subTest(after=after),TemporaryDirectory() as root:
                exe,session,frame=self.executor(root)
                exe.plan=AttackPlan((ArmyEntry(CLAN_CASTLE,'siege',1,True),),
                    (PlanStep('deploy_point',CLAN_CASTLE,1,(MapPoint(.055,.5),)),))
                deployed=frame.copy()
                if after==0:deployed[860:1030,428:558]=darkened(deployed[860:1030,428:558])
                # Preflight/selection use native live recognition. Only game I/O
                # and the selection outline are simulated, not the recognizer.
                exe.frame=Mock(side_effect=[frame,deployed,deployed])
                with patch('coc_bot.attack.executor.selected_card',return_value=True):
                    result=exe.run()
                session.input.tap.assert_called_once_with(400,400,jitter=0)
                self.assertEqual(result.success,after==0)
                self.assertEqual(result.verified_taps,1 if after==0 else 0)
                self.assertEqual(result.uncertain_tap,after!=0)

    def test_missing_or_empty_castle_is_optional_at_preflight(self):
        for missing in (True,False):
            with self.subTest(missing=missing),TemporaryDirectory() as root:
                exe,session,frame=self.executor(root)
                def resolve(image, unit):
                    if unit!=CLAN_CASTLE:return troop(quantity=1)
                    if missing:raise ValueError('Unit is hidden or ambiguous: clan_castle')
                    return castle(0)
                exe.resolve=Mock(side_effect=resolve)
                exe.deploy=Mock(side_effect=lambda *args:setattr(exe.result,'verified_taps',1))
                result=exe.run()
                self.assertTrue(result.success)
                self.assertEqual([c.args[0] for c in exe.deploy.call_args_list],['electro_dragon'])
                self.assertIn(CLAN_CASTLE,exe.skipped_units)
                session.input.tap.assert_not_called()

    def test_castle_disappearing_before_its_turn_does_not_block_remaining_steps(self):
        with TemporaryDirectory() as root:
            exe,session,frame=self.executor(root)
            exe.plan=replace(exe.plan,steps=tuple(reversed(exe.plan.steps)))
            reads=iter([castle(),castle(0)])
            exe.resolve=Mock(side_effect=lambda image,unit:next(reads) if unit==CLAN_CASTLE else troop(quantity=1))
            actual=exe.deploy
            exe.deploy=Mock(side_effect=lambda unit,point:actual(unit,point) if unit==CLAN_CASTLE else
                            setattr(exe.result,'verified_taps',1))
            result=exe.run()
            self.assertTrue(result.success)
            self.assertEqual([c.args[0] for c in exe.deploy.call_args_list],[CLAN_CASTLE,'electro_dragon'])
            session.input.tap.assert_not_called()

    def test_selection_failure_skips_castle_and_cannot_claim_a_completed_attack(self):
        for vanished in (False,True):
            with self.subTest(vanished=vanished),TemporaryDirectory() as root:
                exe,session,frame=self.executor(root)
                exe.plan=AttackPlan((ArmyEntry(CLAN_CASTLE,'siege',1,True),),
                    (PlanStep('deploy_point',CLAN_CASTLE,1,(MapPoint(.055,.5),)),))
                if vanished:
                    exe.resolve=Mock(side_effect=[castle(),castle(),ValueError('hidden'),ValueError('hidden')])
                with patch('coc_bot.attack.executor.selected_card',return_value=False):
                    result=exe.run()
                self.assertFalse(result.success)
                self.assertFalse(result.uncertain_tap)
                self.assertEqual(result.verified_taps,0)
                self.assertEqual(exe.skipped_units,{CLAN_CASTLE})
                self.assertEqual(session.input.tap.call_count,1 if vanished else 2)
                self.assertTrue(all(c.args!=(400,400) for c in session.input.tap.call_args_list))

    def test_camera_failure_and_stop_are_never_treated_as_optional(self):
        for error in (ValueError('Battle zoom changed'),AdbStopped('Stopped')):
            with self.subTest(error=error),TemporaryDirectory() as root:
                exe,session,frame=self.executor(root)
                exe.resolve=Mock(side_effect=lambda image,unit:troop(quantity=1) if unit!=CLAN_CASTLE else
                                 (_ for _ in ()).throw(ValueError('Unit is hidden or ambiguous')))
                exe.frame=Mock(side_effect=[frame,error])
                if isinstance(error,AdbStopped):
                    with self.assertRaises(AdbStopped):exe.run()
                else:self.assertFalse(exe.run().success)
                session.input.tap.assert_not_called()
                self.assertFalse(exe.skipped_units)

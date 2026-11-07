import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

import cv2
import numpy as np

from coc_bot.accounts.store import AccountStore, write
from coc_bot.attack.army import ArmyCard, agree_cards, read_army, resolve_live_card
from coc_bot.attack.automatic import automatic_plan
from coc_bot.attack.hero_library import profile_data_roots, standard_portraits
from coc_bot.control.attack_planner import learned_catalog


def frame(name):
    result=np.zeros((1048,1853,3),np.uint8)
    result[850:]=cv2.imread(str(Path(__file__).parent/'fixtures/attack'/(name+'.png')))
    return result


class SharedHeroLibraryTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=AccountStore(temp.name)
        accounts=[dict(id=c*32,tag='#PYLQG'+str(i+2),original=i==0,roles=['farming'])
                  for i,c in enumerate('abcde')]
        # Valid player-tag alphabet only.
        for account,tag in zip(accounts,('#PYLQG2','#PYLQG8','#PYLQG9','#PYLQGC','#PYLQGR')):
            account['tag']=tag
        write(self.store.path,dict(version=1,active=accounts[0]['id'],pending=None,accounts=accounts))
        self.roots=[self.store.profile(a)/'data' for a in accounts]

    def catalog(self,index=0,**kwargs):
        return learned_catalog(SimpleNamespace(data_dir=self.roots[index],adb_device='new-device'),
                               use_saved_routine=False,**kwargs)

    def save(self,root,name,image,kind='hero'):
        target=root/'attack-planner/units';target.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(target/(name+'.png')),image)
        write(target/(name+'.json'),dict(unit_id=name,kind=kind,device='old-device'))

    def test_five_accounts_get_standard_heroes_without_local_references(self):
        image=frame('clan-castle-toggle-bar')
        expected={'barbarian_king','minion_prince','grand_warden','royal_champion'}
        for index in range(5):
            with self.subTest(account=index):
                catalog=self.catalog(index)
                cards=agree_cards(read_army(image,'battle',catalog),read_army(image,'battle',catalog))
                heroes=[c for c in cards if c.kind=='hero']
                self.assertEqual({c.unit_id for c in heroes},expected)
                self.assertTrue(all(c.stable and c.quantity==1 for c in heroes))
                troop=ArmyCard('troop',(125,857,140,183),'electro_dragon','troop',10,stable=True)
                castle=next(c for c in cards if c.unit_id=='clan_castle')
                plan=automatic_plan([troop,castle,*heroes],progression=True)
                self.assertEqual(sum(s.action=='ability' for s in plan.steps),4)
                self.assertEqual(sum(s.action=='deploy_point' for s in plan.steps),5)

    def test_reviewed_skin_is_shared_without_levels_devices_or_backup_copies(self):
        image=np.random.default_rng(121).integers(0,255,(180,130,3),dtype=np.uint8)
        self.save(self.roots[2],'reviewed_skin',image)
        self.save(self.roots[0]/'account_backups/old','wrong_name',image)
        self.save(self.roots[0]/('accounts/profiles/'+'f'*32+'/data'),'orphan',image)
        for i,root in enumerate(self.roots):
            self.assertEqual(set(profile_data_roots(root)),set(r.resolve() for r in self.roots))
            self.assertEqual(self.catalog(i).identify_reference(image)[0],'reviewed_skin')
        troop=np.random.default_rng(122).integers(0,255,(180,130,3),dtype=np.uint8)
        self.save(self.roots[2],'private_troop',troop,'troop')
        self.assertIsNone(self.catalog(0).identify_reference(troop))

    def test_standard_alias_does_not_make_automatic_identity_ambiguous(self):
        king=dict(standard_portraits())['barbarian_king']
        self.save(self.roots[1],'hero_1',king)
        self.assertEqual(self.catalog(4).identify_reference(king)[0],'barbarian_king')
        self.assertEqual(self.catalog(4,unit_ids={'hero_1'}).identify_reference(king)[0],'hero_1')

    def test_level_and_pet_badges_do_not_establish_portrait_identity(self):
        catalog=self.catalog()
        image=frame('clan-castle-bar')  # Older level 16/16/14 native portraits.
        heroes=[c for c in read_army(image,'battle',catalog) if c.kind=='hero']
        self.assertEqual({c.unit_id for c in heroes},{'barbarian_king','minion_prince','grand_warden'})
        for card in heroes:
            x,y,w,h=card.box;changed=image.copy()
            changed[y+round(h*.80):y+h,x:x+w]=(80,80,80)
            changed[y:y+round(h*.34),x:x+round(w*.40)]=(80,80,80)
            self.assertEqual(resolve_live_card(changed,catalog,card.unit_id).quantity,1)
        for name,portrait in standard_portraits():
            unrelated=portrait.copy();h,w=unrelated.shape[:2]
            unrelated[:round(h*.80)]=(50,50,50)
            self.assertIsNone(catalog.identify_reference(unrelated,kind='hero'))

    def test_shared_portrait_does_not_make_grey_heroes_available(self):
        catalog=self.catalog();image=frame('siege-bar')
        cards=agree_cards(read_army(image,'battle',catalog),read_army(image,'battle',catalog))
        heroes=[c for c in cards if c.kind=='hero' and c.unit_id]
        self.assertEqual({c.unit_id:c.quantity for c in heroes},
                         {'barbarian_king':0,'archer_queen':0,'grand_warden':1})
        for name in ('barbarian_king','archer_queen'):
            self.assertEqual(resolve_live_card(image,catalog,name).quantity,0)
        troop=ArmyCard('t',(125,857,140,183),'electro_dragon','troop',10,stable=True)
        for progression in (False,True):
            plan=automatic_plan([troop,*heroes],progression=progression)
            self.assertEqual({a.unit_id for a in plan.army if a.kind=='hero'},{'grand_warden'})

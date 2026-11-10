"""One bounded Builder Base visit under the bot's existing device lease.

The journal is written before leaving Home Village. Interrupted visits recover
without redeploying troops or repeating spending and never enter home recovery.
"""
import json
import time
import uuid

import cv2
import numpy as np
from loguru import logger

from coc_bot.adb.client import AdbStopped
from coc_bot.adb.multitouch import Multitouch
from coc_bot.attack.camera import compare_camera
from coc_bot.attack.mapping import boundary_mask
from coc_bot.stop import interrupted_sleep
from coc_bot.runtime.battle_history import tracked_battle,note_battle,note_deployment
from coc_bot.upgrades.runner import write_json
from coc_bot.accounts.store import read
from coc_bot.builder_base.frames import BuilderFrameCapture
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.builder_base.upgrades import BuilderUpgradeRunner


def state_path(config):
    return config.data_dir/'builder_base/visit.json'


def state(config):
    path = state_path(config)
    if not path.exists():
        return {}
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result, dict):
            raise ValueError('Expected an object')
        return result
    except (OSError, ValueError) as exc:
        raise RuntimeError('Builder Base journal is unreadable; review it before restarting') from exc


def pending(config):
    from coc_bot.builder_base.verification import deferred
    return bool(state(config).get('phase') or
                read(config.data_dir/'builder_base/upgrades.json',{}).get('pending') and not deferred(config))


def deployment_points(frame):
    """Prefer clear terrain observed just outside the visible Builder boundary.

    These are bounded placement attempts, not a claim of legal-zone detection.
    A card's deployed state must change before moving on. No pan coordinates
    are reused across stages, and no tap is allowed outside the battlefield.
    """
    h, w = frame.shape[:2]
    points = []
    # The shared mask deliberately hides the fixed left HUD and so removes
    # this Builder arena's visible left perimeter. Rebuild the same strict red
    # color test locally, only in its observed lower-left diagonal corridor.
    hsv = cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    b,g,r = cv2.split(frame.astype(np.float32))
    red = (((hsv[:,:,0] <= 18) | (hsv[:,:,0] >= 174))
           & (hsv[:,:,1] >= 110) & (hsv[:,:,2] >= 65) & (hsv[:,:,2] <= 230)
           & (r > g*1.7) & (r > b*1.7))
    visible = np.zeros((h,w),np.uint8)
    visible[round(h*.18):round(h*.66),:round(w*.32)] = 255
    mask = cv2.bitwise_and(red.astype(np.uint8)*255,visible)
    lines = cv2.HoughLinesP(mask,1,np.pi/360,threshold=max(20,round(w*.013)),
                            minLineLength=round(w*.12),maxLineGap=round(w*.012))
    candidates = []
    if lines is not None:
        support_mask = cv2.dilate(mask,np.ones((3,3),np.uint8))
        for x1,y1,x2,y2 in lines.reshape(-1,4):
            if x2 < x1:
                x1,x2,y1,y2 = x2,x1,y2,y1
            dx,dy = float(x2-x1),float(y2-y1)
            length = float(np.hypot(dx,dy))
            # Require a long, supported, descending perimeter from near the
            # left viewport edge. Interior walls and red scenery do not qualify.
            if (length < w*.12 or dx <= 0 or not .55 < -dy/dx < .95
                    or x1 > w*.08 or y1 < h*.38 or y1 > h*.64
                    or x2 < w*.14 or x2 > w*.34 or y2 < h*.16 or y2 > h*.42):
                continue
            n = max(2,round(length))
            xs = np.rint(np.linspace(x1,x2,n)).astype(int)
            ys = np.rint(np.linspace(y1,y2,n)).astype(int)
            support = float((support_mask[ys,xs] > 0).mean())
            if support >= .55:
                candidates.append((length,np.array([x1,y1],float),np.array([dx,dy],float)))
    if candidates:
        length,start,delta = max(candidates,key=lambda item:item[0])
        direction = delta/length
        # For this left edge, the outside normal points up and left. Sample
        # only along the measured segment, with small offsets into clear turf.
        outward = np.array([direction[1],-direction[0]])
        for fraction in (.28,.42,.56,.70):
            for offset in (.018,.038):
                location = start + delta*fraction + outward*w*offset
                points.append(tuple(np.rint(location).astype(int)))
    observed_points = set(points)
    legacy_points = set()
    # Keep the original strict visible-edge path for other inspected Builder
    # layouts (including winter and centered arenas). It is a fallback when
    # the specific measured left perimeter above is absent.
    if not candidates:
        legacy_mask = boundary_mask(frame)
        legacy_lines = cv2.HoughLinesP(legacy_mask,1,np.pi/360,threshold=35,
                                       minLineLength=round(w*.045),maxLineGap=4)
        if legacy_lines is not None:
            for x1,y1,x2,y2 in sorted(legacy_lines.reshape(-1,4),
                                      key=lambda v:-np.hypot(v[2]-v[0],v[3]-v[1])):
                dx,dy = float(x2-x1),float(y2-y1)
                x = (x1+x2)/2
                if not dx or not .4 < abs(dy/dx) < 1.05 or not w*.25 < x < w*.48:
                    continue
                normal = np.array([-dy,dx])/np.hypot(dx,dy)
                if normal[0] > 0:
                    normal = -normal
                for fraction in (.5,.25,.75):
                    for offset in (.025,.04):
                        location=np.array([x1+dx*fraction,y1+dy*fraction])+normal*w*offset
                        point=tuple(np.rint(location).astype(int))
                        points.append(point)
                        legacy_points.add(point)
    # A line midpoint can land on a rock/building. Count accepted terrain,
    # rather than raw Hough candidates, before excluding bounded fallbacks.
    points += [(round(w*x), round(h*y)) for x,y in ((.32,.46),(.33,.51),(.35,.56))]
    # Reject forests/water/HUD and busy artwork in the candidate patch. This
    # deliberately supports the observed default Builder Base arenas only.
    accepted = []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for x,y in points:
        x_min = w*.20 if (x,y) in legacy_points else w*.015
        if not x_min < x < w*.60 or not h*.25 < y < h*.64:
            continue
        patch = hsv[y-8:y+9,x-8:x+9]
        # Inspected default and winter Builder tile palettes. This is only a
        # bounded placement attempt; the army count receipt proves acceptance.
        normal_tiles=cv2.inRange(patch,(65,20,35),(120,170,180))
        winter_tiles=cv2.inRange(patch,(108,25,80),(140,150,225))
        tiles = cv2.bitwise_or(normal_tiles,winter_tiles).mean()/255
        if tiles > .75 and gray[y-8:y+9,x-8:x+9].std() < 22 and (x,y) not in accepted:
            accepted.append((x,y))
    return accepted[:18]


class BuilderBaseRunner:
    def __init__(self, config, capture, input_ctrl, navigator, client, stop=None):
        self.config, self.capture, self.input = config, BuilderFrameCapture(capture,navigator), input_ctrl
        self.nav, self.client, self.stop = navigator, client, stop
        self.reader = BuilderReader(stop)
        self.record = state(config)
        self.folder = config.data_dir/'debug/builder-base'/uuid.uuid4().hex
        self.sequence = 0

    def check(self):
        if self.stop and self.stop():
            raise AdbStopped('Builder Base stopped')

    def wait(self, seconds=.6):
        if interrupted_sleep(seconds, self.stop):
            self.check()

    def phase(self, phase):
        self.record['phase'] = phase
        self.record['updated_at'] = time.time()
        write_json(state_path(self.config), self.record)
        logger.info('Activity: Builder Base — {}', phase.replace('_',' '))

    def frame(self):
        self.check()
        frame = self.capture.screenshot()
        self.check()
        return frame

    def evidence(self, frame, name):
        if self.sequence >= 32:
            return
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.sequence += 1
            cv2.imwrite(str(self.folder/f'{self.sequence:03}-{name}.png'), frame)
            raw = self.capture.raw_for(frame)
            if raw is not None and self.capture.was_normalized(frame):
                cv2.imwrite(str(self.folder/f'{self.sequence:03}-{name}-raw.png'), raw)
        except OSError as exc:
            logger.warning('Builder Base evidence could not be saved: {}', exc)

    def tap(self, point):
        self.check()
        if self.config.dry_run:
            raise ValueError('Builder Base actions are disabled in practice mode')
        self.input.tap(*point, jitter=0)

    def zoom(self, frame):
        self.check()
        if self.client.wm_size() != (frame.shape[1], frame.shape[0]):
            raise ValueError('Builder Base input dimensions differ from screenshot')
        with Multitouch(self.client, (frame.shape[1], frame.shape[0])) as touch:
            touch.pinch()
        self.wait()
        return self.frame()

    def home_village(self, frame):
        from coc_bot.vision.battle_menu import home_build_control_visible
        return (not self.reader.home(frame) and not self.reader.battle(frame)
                and not self.reader.result_button(frame)
                and home_build_control_visible(frame)
                and self.nav.classifier._open_chat_icon_visible(frame))

    def boat(self, *, returning, allow_setup=True):
        frame = self.frame()
        verify = self.reader.home if returning else self.home_village
        if not verify(frame):
            frame = self.settle_village(verify)
        for attempt in range(6):
            if not verify(frame):
                frame = self.settle_village(verify)
            if not returning and allow_setup:
                from coc_bot.builder_base.onboarding import BuilderOnboarding
                flow=BuilderOnboarding(self)
                if flow.select_setup_boat(frame):
                    flow.drive()
                    return self.frame()
            point = self.reader.boat_target(frame, returning=returning, box=(.14,.12,.90,.80), threshold=.86)
            if point:
                second = self.frame()
                again = self.reader.boat_target(second, returning=returning, box=(.14,.12,.90,.80), threshold=.86)
                # The boat's bubble bobs by several pixels while the camera is
                # stationary. Reacquire its center; tolerate only movement well
                # inside that verified bubble, never a reused map coordinate.
                if not verify(second) or again is None or np.linalg.norm(np.array(point)-again)>max(5,second.shape[1]*.008):
                    raise ValueError('Boat moved; navigation stopped')
                self.tap(again)
                for _ in range(10):
                    self.wait(1)
                    frame = self.frame()
                    from coc_bot.builder_base.onboarding import BuilderOnboarding
                    flow=BuilderOnboarding(self)
                    if allow_setup and flow.dialog(frame) and flow.advance_dialog():continue
                    if (self.home_village(frame) if returning else self.reader.home(frame)):
                        return frame
                raise ValueError('Boat tap did not confirm the destination village')
            if attempt == 5:
                break
            if attempt == 0:
                frame = self.zoom(frame)
                continue
            h,w = frame.shape[:2]
            gesture = (.62,.36,.40,.66) if returning else (.40,.62,.62,.38)
            if attempt % 2 == 0:
                gesture = (.65,.62,.38,.62) if returning else (.38,.45,.65,.45)
            self.check()
            self.input.swipe(round(w*gesture[0]),round(h*gesture[1]),round(w*gesture[2]),round(h*gesture[3]),duration_ms=300)
            self.wait()
            frame = self.frame()
        self.evidence(frame,'boat-not-found')
        raise ValueError('Boat not found after bounded camera search')

    def acknowledge_bonus(self, frame):
        from coc_bot.progression.home import acknowledge_star_bonus
        return acknowledge_star_bonus(self.nav,frame,self.capture,self.input,
                                      lambda:bool(self.stop and self.stop()))

    def recover_overlay(self, frame):
        from coc_bot.progression.home import recover_known_overlay
        return recover_known_overlay(self.nav,frame)

    def settle_village(self, verify):
        from coc_bot.progression.home import recover_home_overlay
        from coc_bot.builder_base.onboarding import BuilderOnboarding
        for _ in range(8):
            frame = self.frame()
            from coc_bot.builder_base.tutorials import recover
            if recover(self,frame):continue
            if self.reader.reward_button(frame):
                if not self.acknowledge_bonus(frame):
                    raise ValueError('Star Bonus acknowledgement could not be verified or retry limit reached')
            elif BuilderOnboarding(self).dialog(frame) and BuilderOnboarding(self).advance_dialog():
                pass
            elif recover_home_overlay(self.nav,frame):
                pass
            elif verify(frame):
                return frame
            self.wait(1)
        raise ValueError('Village controls not verified after waiting for transitions/rewards')

    def enter(self):
        from coc_bot.builder_base.onboarding import BuilderOnboarding
        flow=BuilderOnboarding(self)
        frame = self.frame()
        if self.reader.home(frame):
            if flow.state().get('phase') not in (None,'complete'):flow.drive()
            self.phase('builder_home')
            return
        setup=flow.state()
        if (setup.get('account')==self.config.account_tag
            and setup.get('phase') in ('selecting_boat','first_sail_requested')
            and self.home_village(frame)):
            # Account verification can deselect the boat. Reacquire that owned
            # navigation target instead of assuming its action tiles stayed open.
            self.phase('travelling_to_builder_base')
            if self.reader.selected_boat_rebuild(frame) or flow.dialog(frame) or flow.prepare():flow.drive()
            else:self.boat(returning=False)
            self.phase('builder_home')
            return
        if not self.nav.ensure_clan_chat():
            raise ValueError('Cannot establish Home Village before Builder Base visit')
        frame = self.frame()
        if getattr(self.config,'donation_enabled',True):
            if not self.nav.classifier._clan_chat_anchor_visible(frame):
                raise ValueError('Clan chat was not verified')
            self.nav.close_clan_chat(frame)
        elif not self.home_village(frame):
            raise ValueError('Home Village was not verified')
        self.wait()
        self.phase('travelling_to_builder_base')
        if flow.prepare():flow.drive()
        else:self.boat(returning=False)
        self.phase('builder_home')

    def finish(self):
        frame = self.frame()
        if self.reader.daily_reward_close(frame):
            from coc_bot.builder_base.tutorials import recover
            if recover(self,frame):frame=self.frame()
        if self.reader.reward_button(frame):
            frame = self.settle_village(lambda f:self.reader.home(f) or self.home_village(f))
        if self.reader.home(frame):
            self.phase('returning_to_home_village')
            self.boat(returning=True)
        frame = self.frame()
        if not (self.home_village(frame) or self.nav.classifier._clan_chat_anchor_visible(frame)):
            raise ValueError('Home Village not verified; donation recovery blocked')
        if not self.nav.ensure_clan_chat():
            raise ValueError('Could not confirm clan chat after Builder Base visit')
        self.record.pop('phase', None)
        self.record['last_finished_at'] = time.time()
        self.record['next_visit_at'] = time.time()+self.config.builder_base_interval_seconds
        write_json(state_path(self.config), self.record)
        from coc_bot.runtime.screenshot_retention import prune_attack_diagnostics
        prune_attack_diagnostics(self.config.data_dir)

    def attack(self):
        frame = self.frame()
        if not self.reader.home(frame):
            raise ValueError('Builder Base home is required to start an attack')
        self.phase('opening_attack')
        self.tap((round(frame.shape[1]*.065),round(frame.shape[0]*.89)))
        self.wait()
        frame = self.frame()
        if not self.reader.attack_menu(frame):
            raise ValueError('Builder Base Start Attack dialog not verified')
        from coc_bot.builder_base.starter import army as starter_army
        starter=starter_army(self.reader,frame)
        army_kind=self.reader.supported_army_kind(frame)
        supported=army_kind is not None
        if not supported and starter is None:
            from coc_bot.builder_base.army import empty_attack,repair
            if empty_attack(self.reader,frame) and repair(self):
                frame=self.frame();starter=starter_army(self.reader,frame)
                if self.reader.home(frame) and self.reader.home(self.frame()):
                    # Choose Army replaces the preflight modal and closes to
                    # the village. Reopen it before interpreting any army card.
                    self.tap((round(frame.shape[1]*.065),round(frame.shape[0]*.89)))
                    self.wait();frame=self.frame();starter=starter_army(self.reader,frame)
                army_kind=self.reader.supported_army_kind(frame)
                supported=army_kind is not None
        second=self.frame()
        if (not supported and starter is None or not self.reader.attack_menu(second)
            or supported and self.reader.supported_army_kind(second)!=army_kind
            or supported and not self.reader.battle_army_ready(army_kind)
            or starter is not None and starter_army(self.reader,second)!=starter):
            self.evidence(frame, 'unsupported-army')
            closing=self.frame()
            if self.reader.attack_menu(closing) and self.reader.attack_menu(self.frame()):
                self.tap((round(closing.shape[1]*.853),round(closing.shape[0]*.182)))
                self.wait()
            elif not (self.reader.home(closing) and self.reader.home(self.frame())):
                raise ValueError('Unsupported Builder army left an unknown menu; no close tap sent')
            self.phase('builder_home')
            logger.warning('Builder Base attack skipped: army is not a verified supported composition')
            return {'status':'unsupported_army'}
        for key in ('starter_army','starter_sent','starter_confirmed','army_kind'):self.record.pop(key,None)
        if starter is not None:self.record['starter_army']=starter
        if supported:self.record['army_kind']=army_kind
        self.phase('matchmaking')
        self.tap(self.reader.find(second,'find_now',(.65,.60,.84,.72)))
        for _ in range(30):
            self.wait(1)
            frame = self.frame()
            if self.reader.battle(frame):
                self.phase('battle')
                return self.watch_battle(deploy=True,army=army_kind or 'night_witch')
        raise ValueError('Builder Base matchmaking timed out; checkpoint retained')

    @tracked_battle('builder')
    def watch_battle(self, *, deploy=False, army=None):
        if self.record.get('starter_army'):
            from coc_bot.builder_base.starter import watch
            return watch(self,deploy=deploy)
        army=army or self.record.get('army_kind') or 'night_witch'
        deadline = time.monotonic()+480
        attempts = {}; abilities = {}; zoomed = False
        fighting = False
        stage = 1
        count = 0
        placement_frame = None
        placement_targets = []
        air_positions = {}
        spread_targets = []
        spacing_notice = False
        while time.monotonic() < deadline:
            frame = self.frame()
            from coc_bot.builder_base.tutorials import recover
            if recover(self,frame):continue
            if self.reader.reward_button(frame):
                if not self.acknowledge_bonus(frame):
                    raise ValueError('Star Bonus acknowledgement could not be verified or retry limit reached')
                self.wait(.4)
                continue
            if self.recover_overlay(frame):
                self.wait(.4)
                continue
            point = self.reader.result_button(frame)
            if point:
                self.evidence(frame,'battle-results')
                second = self.frame()
                point = self.reader.result_button(second)
                if point:
                    note_battle(entered_battle=True,result_confirmed=True)
                    from coc_bot.runtime.battle_history import record_results
                    record_results(frame,second,'builder',self.stop)
                    self.phase('leaving_results')
                    self.tap(point)
                    self.wait(2)
                continue
            if self.reader.home(frame):
                self.phase('builder_home')
                return {'status':'returned' if count or not deploy else 'no_verified_deployment',
                        'verified_deployments':count}
            if not self.reader.battle(frame):
                self.wait(1)
                continue
            note_battle(entered_battle=True)
            if not deploy:
                self.wait(3)
                continue
            scouting = bool(self.reader.find(frame, 'battle_starts', (.43,.012,.57,.055)))
            if scouting and fighting:
                stage += 1
                if stage > 2:
                    raise ValueError('Unexpected additional Builder Base stage')
                logger.info('Builder Base: second stage — rebuilding deployment targets')
                zoomed = False
                placement_frame = None
                placement_targets = []
                spread_targets = []
                air_positions.clear()
                spacing_notice = False
                attempts.clear()
                abilities.clear()
                fighting = False
            elif not scouting:
                fighting = True
            cards = self.reader.cards(frame,army=army)
            note_battle(army=[{'unit':card['unit'],'count':1} for card in cards])
            ready = sorted([c for c in cards if not c['deployed'] and attempts.get((c['slot'],c['unit']),0)<6],
                           key=lambda c: (c['slot']==0, c['slot']))
            if ready and army=='baby_dragon' and spread_targets and air_positions:
                from coc_bot.builder_base.deployment import separated_air_target
                feasible=[];held=False
                for candidate in ready:
                    if candidate['unit'] in ('baby_dragon','battle_copter'):
                        occupied=[p for slot,positions in air_positions.items() if slot!=candidate['slot'] for p in positions]
                        if separated_air_target(spread_targets,occupied,frame.shape[1]) is None:
                            held=True
                            continue
                    feasible.append(candidate)
                if held and not spacing_notice:
                    logger.warning('Дракончики ожидают: на видимой границе нет достаточно удалённой точки высадки')
                    spacing_notice=True
                # Held air camps must not starve ground heroes or abilities.
                ready=feasible
            if ready:
                if not zoomed:
                    frame = self.zoom(frame)
                    if not self.reader.battle(frame):
                        continue
                    zoomed = True
                    placement_frame = None
                    placement_targets = []
                    self.evidence(frame, 'stage-view')
                card = ready[0]
                second = self.frame()
                same = next((c for c in self.reader.cards(second,army=army) if c['slot']==card['slot']
                             and c['unit']==card['unit'] and not c['deployed']),None)
                if same:
                    self.tap(same['point'])
                    self.wait(.15)
                    before = self.frame()
                    after = self.frame()
                    motion = compare_camera(before, after)
                    if not self.reader.battle(after) or not motion['verified'] or abs(motion['scale']-1)>.003:
                        self.wait(1)
                        continue
                    transform = np.array(motion['transform'])
                    if max(abs(transform[0,2]),abs(transform[1,2]))>3:
                        continue
                    # The red boundary disappears after the first unit lands.
                    # Retain its targets only while artwork verifies the same
                    # camera and map; discard them on every stage transition.
                    if placement_frame is None:
                        placement_targets = deployment_points(after)
                        if army=='baby_dragon':
                            from coc_bot.builder_base.deployment import air_deployment_points
                            spread_targets=air_deployment_points(after,placement_targets)
                        placement_frame = after.copy() if placement_targets or spread_targets else None
                    points = placement_targets
                    if placement_frame is not None:
                        alignment = compare_camera(placement_frame, after)
                        if (not alignment['verified'] or abs(alignment['scale']-1)>.003
                            or max(abs(np.array(alignment['transform'])[:2,2]))>3):
                            self.wait(.3)
                            continue
                    key = (card['slot'],card['unit'])
                    attempt = attempts.get(key,0)
                    air_spread=army=='baby_dragon' and card['unit'] in ('baby_dragon','battle_copter')
                    if air_spread:
                        from coc_bot.builder_base.deployment import separated_air_target
                        occupied=[p for slot,positions in air_positions.items() if slot!=card['slot'] for p in positions]
                        target=separated_air_target(spread_targets,occupied,after.shape[1],attempt)
                        if target is None:
                            if not spacing_notice:
                                logger.warning('Дракончики ожидают: на видимой границе нет достаточно удалённой точки высадки')
                                spacing_notice=True
                            self.wait(1)
                            continue
                    else:
                        target=points[attempt % len(points)] if points else None
                    if target is None:
                        self.wait(1)
                        continue
                    if air_spread:
                        # Reserve even an uncertain tap: a missed receipt must
                        # never send another air camp into the same area.
                        air_positions.setdefault(card['slot'],[]).append(target)
                        logger.info('Раздельная высадка воздушного отряда: ячейка {}, точка {}',card['slot']+1,target)
                    self.tap(target)
                    attempts[key] = attempt+1
                    self.wait(.4)
                    check = self.frame()
                    if attempt < 2:
                        self.evidence(check, f'slot-{card["slot"]}-attempt-{attempt}')
                    updated = next((c for c in self.reader.cards(check,army=army) if c['slot']==card['slot']
                                        and c['unit']==card['unit']),None)
                    if updated and updated['deployed']:
                        count += 1
                        note_deployment(card['unit'],points=[target],frame=check)
                        logger.info('Builder Base: deployment confirmed for {} slot {}',card['unit'],card['slot'])
                        self.evidence(check,'deployment-confirmed')
                        abilities.pop(key,None)
                    else:
                        logger.warning('Builder Base: no clear deployment confirmation; waiting for a supported view')
            else:
                for card in cards:
                    key = (card['slot'],card['unit'])
                    cooldown = 15 if card['unit'] != 'night_witch' else 480
                    one_time = card['unit'] in ('night_witch','baby_dragon')
                    if one_time and key in abilities:
                        continue
                    if card['unit']=='baby_dragon' and not card.get('ability_ready'):
                        continue
                    if not card['deployed'] or time.monotonic()-abilities.get(key,-1000)<cooldown:
                        continue
                    fresh = self.frame()
                    valid = next((c for c in self.reader.cards(fresh,army=army) if c['slot']==card['slot']
                                  and c['unit']==card['unit'] and c['deployed']
                                  and (c['unit']!='baby_dragon' or c.get('ability_ready'))),None)
                    if valid:
                        self.tap(valid['point'])
                        abilities[key] = time.monotonic()
                self.wait(2)
        raise ValueError('Builder Base battle did not reach verified results/home within eight minutes')

    def pause_upgrades(self, result):
        """Retain the receipt; release only after an independently verified Home return.

        An unknown screen, held placement, battle or stopped operation still owns
        recovery. No exception is converted into permission to spend again.
        """
        from coc_bot.runtime.verification import record_failure, fingerprint
        from coc_bot.builder_base.progression import BuilderProgressionRunner
        from coc_bot.builder_base.verification import paused_result
        path=self.config.data_dir/'builder_base/upgrades.json'
        if self.record.get('phase') in ('battle','matchmaking','leaving_results','collection_needs_review'):
            raise ValueError('Builder recovery checkpoint cannot be deferred as an upgrade failure')
        journal=read(path,{})
        payment=journal.get('pending')
        if not isinstance(payment,dict) or payment.get('kind') not in ('construction','wall','buildings','research'):
            raise ValueError('Unknown Builder receipt cannot be deferred safely')
        message=result.get('message') or 'Builder upgrade outcome could not be verified'
        failure=record_failure(self.config,'builder_base.upgrades',message,pending=payment,evidence=self.folder)
        self.evidence(self.frame(),'verification-failed')
        receipt=BuilderProgressionRunner(self.config,self.capture,self.input,self.nav,self.stop)
        receipt.close()
        for _ in range(2):
            frame=self.frame()
            if (not self.reader.home(frame) or receipt.construction_controls(frame) is not None
                or self.reader.battle(frame) or self.reader.result_button(frame)):
                raise ValueError('Builder verification failed on an unsettled screen; safe return is not verified')
        self.finish()
        for _ in range(2):
            frame=self.frame()
            if not (self.home_village(frame) or self.nav.classifier._clan_chat_anchor_visible(frame)):
                raise ValueError('Home Village not independently verified; Builder receipt remains blocking')
        # Re-read before writing so a changed transaction cannot inherit this
        # receipt's Home proof. Interrupted navigation never writes this marker.
        journal=read(path,{})
        if journal.get('pending')!=payment:
            raise ValueError('Builder receipt changed while returning Home')
        journal['deferred_receipt']={'account':getattr(self.config,'account_tag',None),
            'fingerprint':fingerprint(payment),'failure_id':failure,'home_verified_at':time.time()}
        write_json(path,journal)
        logger.warning('Builder upgrades paused [{}]; Home Village verified, continuing safe account work',failure)
        return paused_result(self.config)

    def recover(self):
        from coc_bot.builder_base.verification import deferred
        if not self.record.get('phase') and deferred(self.config):return
        payment=read(self.config.data_dir/'builder_base/upgrades.json',{}).get('pending')
        if not self.record.get('phase') and not payment:
            return
        if self.record.get('phase') == 'collection_needs_review':
            raise ValueError('Builder Base gem balance changed during collection; review the saved evidence and visit journal before resuming')
        logger.info('Recovering interrupted Builder Base visit without new deployments')
        if payment:
            if self.record.get('phase') in ('battle','matchmaking','leaving_results'):
                raise ValueError('Builder payment and battle checkpoints disagree; no recovery input sent')
            if not self.record.get('phase'):self.phase('checking_upgrades')
            frame=self.frame()
            if not self.reader.home(frame):
                if not (self.home_village(frame) or self.nav.classifier._clan_chat_anchor_visible(frame)):
                    raise ValueError('Builder payment recovery needs a verified village before travel')
                from types import SimpleNamespace
                from coc_bot.accounts.navigation import verify_session
                verify_session(SimpleNamespace(config=self.config,capture=self.capture,input=self.input,
                               nav_input=self.input,navigator=self.nav),self.stop or (lambda:False))
                if not self.nav.ensure_clan_chat():raise ValueError('Home village did not verify before receipt recovery')
                if getattr(self.config,'donation_enabled',True):self.nav.close_clan_chat(self.frame())
                self.wait();self.phase('travelling_to_builder_base')
                self.boat(returning=False,allow_setup=False)
                self.phase('checking_upgrades')
            from coc_bot.builder_base.progression import BuilderProgressionRunner
            receipt=BuilderProgressionRunner(self.config,self.capture,self.input,self.nav,self.stop)
            kind=payment.get('kind')
            if kind not in ('construction','wall','buildings','research'):
                raise ValueError('Unknown Builder payment category; no recovery input sent')
            try:
                result=receipt.run('research' if kind=='research' else 'buildings',execute=False)
            except ValueError as exc:
                result={'status':'needs_review','message':str(exc)}
            if receipt.state().get('pending'):
                return self.pause_upgrades(result)
        from coc_bot.builder_base.onboarding import BuilderOnboarding
        flow=BuilderOnboarding(self)
        if flow.state().get('phase') not in (None,'complete'):
            flow.drive()
            self.finish()
            return
        frame = self.frame()
        # A delivered bonus may survive a failed post-battle collection.
        for _ in range(3):
            if not self.reader.reward_button(frame):break
            if not self.acknowledge_bonus(frame):
                raise ValueError('Star Bonus acknowledgement could not be verified or retry limit reached')
            self.wait(.4);frame=self.frame()
        # A reconnect can leave the free welcome notice over either village.
        # Dismiss only known non-purchase overlays before inspecting recovery.
        from coc_bot.progression.home import recover_home_overlay
        for _ in range(4):
            if not recover_home_overlay(self.nav,frame):break
            if self.wait(.5):return
            frame=self.frame()
        if self.record.get('phase')=='editing_army':
            from coc_bot.builder_base.army import close as close_army,editor_close
            if editor_close(self.reader,frame) is not None:
                if not close_army(self):raise ValueError('Builder army editor could not be recovered')
                frame=self.frame()
        if (self.record['phase']=='checking_upgrades' and
            getattr(self.config,'builder_base_progression_enabled',False)):
            from coc_bot.builder_base.progression import BuilderProgressionRunner
            BuilderProgressionRunner(self.config,self.capture,self.input,self.nav,self.stop).close()
            frame=self.frame()
        if self.reader.research_sorting(frame) is True:
            BuilderUpgradeRunner(self.config,self.capture,self.input,self.nav,self.stop).close()
            frame=self.frame()
            if self.reader.research_sorting(frame) is True:
                raise ValueError('Builder research sorting did not close during recovery')
        from coc_bot.builder_base.resources import ResourceCollector
        from coc_bot.builder_base.tutorials import recover as recover_tutorial
        for _ in range(16):
            if not recover_tutorial(self,frame):break
            frame=self.frame()
        collector = ResourceCollector(self)
        if collector.reader.cart(frame):
            # Recovery closes the cart without claiming/spending anything.
            collector.close_cart()
            frame = self.frame()
        if self.reader.battle(frame) or self.reader.result_button(frame) or self.record['phase']=='matchmaking':
            self.watch_battle(deploy=False)
        else:
            close = self.reader.detail_close(frame)
            if close:
                self.tap(close); self.wait(); frame = self.frame()
            if self.reader.menu_kind(frame):
                self.tap((round(frame.shape[1]*.984),round(frame.shape[0]*.032)))
                self.wait()
            elif self.reader.attack_menu(frame):
                self.tap((round(frame.shape[1]*.853),round(frame.shape[0]*.182)))
                self.wait()
        self.finish()

    def run(self, *, refill=False):
        if self.config.dry_run:
            return {'status':'practice_skipped'}
        from coc_bot.builder_base.verification import deferred,paused_result
        if not self.record.get('phase') and deferred(self.config):return paused_result(self.config)
        if self.record.get('phase') or pending(self.config):
            return self.recover() or {'status':'recovered'}
        self.enter()
        report = {}
        if getattr(self.config, 'builder_base_collect_resources', False):
            from coc_bot.builder_base.resources import ResourceCollector
            report['collection'] = ResourceCollector(self).run()
        if refill and self.config.builder_base_attacks_enabled:
            report=self.refill_resources(report)
            if report.get('visit_repeat'):
                self.finish()
                return report
        def upgrade():
            self.phase('checking_upgrades')
            progression=getattr(self.config,'builder_base_progression_enabled',False)
            if progression:
                from coc_bot.builder_base.progression import BuilderProgressionRunner
                runner=BuilderProgressionRunner(self.config,self.capture,self.input,self.nav,self.stop)
            else:runner = BuilderUpgradeRunner(self.config,self.capture,self.input,self.nav,self.stop)
            choices=[]
            if progression and self.config.builder_base_upgrades_enabled:choices.append('buildings')
            if getattr(self.config,'builder_base_research_enabled',False): choices.append('research')
            if self.config.builder_base_upgrades_enabled: choices.extend(['buildings']*(2 if progression else 3))
            result={'status':'disabled'}
            completed=[]
            paused=[]
            for kind in choices:
                result=runner.run(kind,execute=True)
                from coc_bot.runtime.verification import log_result
                log_result(self.config,'builder_base.'+kind,result,pending=runner.state().get('pending'))
                logger.info('Builder Base {} upgrade: {} — {}',kind,result.get('status'),
                            result.get('message') or 'No additional details')
                if kind=='research' and result.get('status')=='nothing_eligible':
                    for item in result.get('recommendations',[]):
                        logger.info('Builder research candidate {}: {}',item.get('name'),
                                    item.get('skip') or 'eligible')
                if result.get('status') in ('started','built','recovered'):
                    completed.append(result)
                    continue  # The previous transaction is already confirmed.
                if (result.get('status') in ('blocked','changed')
                    and not runner.state().get('pending')):
                    paused.append(result)
                    continue  # An unrecognized pre-payment dialog owns no funds.
                # A busy lab does not prevent using a free builder. Each later
                # purchase obtains fresh slot, balance and confirmation reads.
                if result.get('status') in ('nothing_eligible','skipped','busy','waiting'):
                    if kind=='buildings' and not progression:break
                    continue
                return result|{'completed_operations':completed,'paused_operations':paused}
            report=(completed[-1]|{'completed_operations':completed}) if completed else result
            return report|{'paused_operations':paused} if paused else report
        upgrades=(self.config.builder_base_upgrades_enabled or
                  getattr(self.config,'builder_base_research_enabled',False))
        if upgrades:
            report['upgrade']=upgrade()
            if read(self.config.data_dir/'builder_base/upgrades.json',{}).get('pending'):
                return report|self.pause_upgrades(report['upgrade'])
            if refill and report['upgrade'].get('paused_operations'):
                report.update(retry_at=time.time()+900,message='Some Builder upgrade checks need another observation')
        if self.config.builder_base_attacks_enabled and not refill:
            if upgrades and report['upgrade'].get('status') in ('needs_review','changed','blocked','stopped'):
                report['attack']={'status':'blocked','message':'Upgrade outcome must be resolved before farming'}
                self.finish()
                return report
            from coc_bot.builder_base.demand import farming_demand
            observation = self.resource_demand()
            demand = farming_demand(observation,
                buildings=self.config.builder_base_upgrades_enabled,
                research=getattr(self.config,'builder_base_research_enabled',False),
                reserved=self.config.builder_base_builders_reserved,
                reserves={'gold':self.config.builder_base_gold_reserve,
                          'elixir':self.config.builder_base_elixir_reserve})
            self.record['resource_demand']=observation|{'attack':demand.attack,'reason':demand.reason}
            self.phase('builder_home')
            logger.info('Builder Base farming: {}',demand.reason)
            report['attack'] = self.attack() if demand.attack else {'status':'not_needed','message':demand.reason}
            if demand.attack and report['attack'].get('status')!='unsupported_army' and getattr(self.config, 'builder_base_collect_resources', False):
                report['collection_after_attack'] = ResourceCollector(self).run()
            if demand.attack and upgrades and report['upgrade'].get('status')=='nothing_eligible':
                report['upgrade']=upgrade()
        self.finish()
        if refill and not report.get('retry_at') and report.get('upgrade',{}).get('completed_operations'):
            # Return Home between bounded upgrade batches so the coordinator
            # can check chat. The next pass rescans every slot/payment afresh.
            report['visit_repeat']=True
        return report

    def refill_resources(self, report):
        from coc_bot.accounts.store import write
        from coc_bot.runtime.resource_farming import decide,record_outcome
        from coc_bot.builder_base.resources import ResourceReader
        path=self.config.data_dir/'resources/builder.json'
        saved=read(path,{})
        account=getattr(self.config,'account_tag',None)
        if saved.get('account',account)!=account:raise ValueError('Builder resource observations belong to another account')
        if time.time()<saved.get('retry_at',0):
            return report|{'retry_at':saved['retry_at'],'message':saved.get('message','Builder farming paused')}
        saved.pop('retry_at',None)
        reader=ResourceReader(self.reader)
        capacities=self.reader.storage_capacities(self)
        first_frame,second_frame=self.frame(),self.frame()
        clean=not any(self.reader.storage_tooltip_visible(f,r) for f in (first_frame,second_frame) for r in ('gold','elixir'))
        first,second=(reader.balances(first_frame),reader.balances(second_frame)) if clean else ({},{})
        observation={'resources':['gold','elixir'],
                     'balances':{r:second[r] for r in ('gold','elixir') if type(second.get(r)) is int and first.get(r)==second[r]},
                     'capacities':capacities}
        decision=decide(observation,saved,start=self.config.farm_resource_start_percent,
                        stop=self.config.farm_resource_target_percent)
        saved.update(observation=observation,observed_at=time.time(),message=decision.message,status=decision.status,account=account)
        if decision.status=='unverified' or decision.attack and saved.get('no_progress',0)>=3:
            saved.update(retry_at=time.time()+(60 if decision.status=='unverified' else 900),no_progress=0,
                         message=('Builder resources unreadable: '+decision.message if decision.status=='unverified'
                                  else 'Builder attacks produced no verified resource gain'))
            write(path,saved)
            return report|{'retry_at':saved['retry_at'],'message':saved['message']}
        write(path,saved)
        if decision.attack:
            report['attack']=self.attack()
            if report['attack'].get('status')=='unsupported_army':
                saved.update(retry_at=time.time()+900,message='Builder army is unsupported')
            else:
                if getattr(self.config,'builder_base_collect_resources',False):
                    from coc_bot.builder_base.resources import ResourceCollector
                    report['collection_after_attack']=ResourceCollector(self).run()
                after=reader.balances(self.frame())
                if any(type(after.get(r)) is not int for r in decision.resources):
                    saved.update(retry_at=time.time()+300,message='Post-battle Builder resources are unreadable')
                else:
                    record_outcome(saved,observation['balances'],after,decision.resources)
                    if all(type(after.get(r)) is int for r in ('gold','elixir')):
                        saved.update(observation=observation|{'balances':{r:after[r] for r in ('gold','elixir')}},observed_at=time.time())
            write(path,saved)
            return report|{'visit_repeat':not saved.get('retry_at'),
                           'retry_at':saved.get('retry_at'),'message':saved.get('message')}
        return report

    def resource_demand(self):
        """Two fresh upgrade-menu observations before any new attack."""
        from coc_bot.builder_base.upgrades import supported_building
        from coc_bot.upgrades.vision import Candidate
        from coc_bot.upgrades.vision import compact
        progression=getattr(self.config,'builder_base_progression_enabled',False)
        if progression:
            from coc_bot.builder_base.progression import BuilderProgressionRunner
            runner=BuilderProgressionRunner(self.config,self.capture,self.input,self.nav,self.stop)
        else:runner=BuilderUpgradeRunner(self.config,self.capture,self.input,self.nav,self.stop)
        report={'builders':None,'lab':None,'balances':{},'capacities':{},'targets':[]}
        try:
            for kind in ('buildings','research'):
                enabled=(self.config.builder_base_upgrades_enabled if kind=='buildings' else
                         getattr(self.config,'builder_base_research_enabled',False))
                if not enabled:continue
                first=runner.open_menu(kind)
                if first is None:break
                a=runner.inspect(kind,first)
                b=runner.inspect(kind,self.frame())
                if a['availability']!=b['availability'] or a['balances']!=b['balances']:continue
                report['builders' if kind=='buildings' else 'lab']=b['availability']
                report['balances']=b['balances']
                if progression:
                    from coc_bot.builder_base.progression import CONSTRUCTIBLE,hall_blockers
                    from coc_bot.builder_base.research import supports_progression_research
                    if b['availability'] is None or not b['availability'][0]:continue
                    inventory=runner.scan(self.frame(),kind)
                    if not inventory['complete']:continue
                    if kind=='buildings' and inventory.get('hall_verified') is True:
                        report.update(hall=inventory['hall'],hall_verified=True,
                                      inventory_at=time.time(),account=self.config.account_tag)
                    rows=[v for v in inventory['rows'] if type(v.get('cost')) is int and v['cost']>0
                          and v.get('currency') in ('gold','elixir') and v.get('state') not in ('maxed','future_locked')]
                    order={'starlaboratory':0,'armycamp':1,'goldstorage':2,'elixirstorage':2}
                    rows.sort(key=lambda v:order.get(compact(v['name']),3))
                    currencies=set()
                    for row in rows:
                        name=compact(row['name'])
                        resource=row['currency']
                        floor=getattr(self.config,'builder_base_'+resource+'_reserve')
                        balance=b['balances'].get(resource)
                        if resource in currencies or type(balance) is not int or balance>=row['cost']+floor:continue
                        supported=(name in CONSTRUCTIBLE or name=='builderhall' and not hall_blockers(inventory)) if kind=='buildings' else supports_progression_research(row)
                        if not supported:continue
                        located=runner.find_row(row,kind)
                        if located is None:continue
                        # The complete inventory nominates a target; a fresh
                        # identical row must still exist before it can justify farming.
                        from coc_bot.progression.reader import row_key
                        fresh=runner.reader.rows(self.frame())
                        if not any(row_key(v)==row_key(row) and
                                   (kind!='research' or v.get('target_level')==row.get('target_level'))
                                   for v in fresh):continue
                        excluded=name in {compact(n) for n in self.config.upgrade_excluded_names.split(',')}
                        target_fields=('name','currency','cost','target_level') if kind=='research' else ('name','currency','cost')
                        report['targets'].append({k:row.get(k) for k in target_fields}|
                                                 {'kind':kind,'supported':not excluded})
                        currencies.add(resource)
                    continue
                previous={(compact(c['name']),c['currency'],c['cost']) for c in a['recommendations']}
                for c in b['recommendations']:
                    if (compact(c['name']),c['currency'],c['cost']) not in previous:continue
                    supported=(supported_building(Candidate(c['name'],c['cost'],c['currency'],(0,0))) if kind=='buildings'
                               else compact(c['name'])=='nightwitch' and c['currency']=='elixir')
                    excluded=compact(c['name']) in {compact(n) for n in self.config.upgrade_excluded_names.split(',')}
                    report['targets'].append({k:c[k] for k in ('name','currency','cost')}|
                                             {'kind':kind,'supported':supported and not excluded})
        finally:
            if not self.stop or not self.stop():runner.close()
        # Capacity is read from the game's resource details, never inferred from
        # a remembered hall level or a full-looking colored resource bar.
        report['capacities']=self.reader.storage_capacities(self)
        return report

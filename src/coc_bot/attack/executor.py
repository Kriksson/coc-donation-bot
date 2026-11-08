"""Verified deployments, including bounded spam bursts. Never replay uncertain taps."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
import uuid

import cv2
import numpy as np
from loguru import logger

from coc_bot.attack.army import check_stop, resolve_live_card, resolve_just_depleted
from coc_bot.attack.camera import compare_camera, CameraFeatures
from coc_bot.attack.projection import input_area, step_points, validate_geometry
from coc_bot.attack.survey import affine
from coc_bot.attack.battle_gate import BattleFrameGate
from coc_bot.adb.client import AdbStopped
from coc_bot.vision.battle_menu import active_battle_ready
from coc_bot.attack.reinforcements import CLAN_CASTLE
from coc_bot.attack.edge_fallback import SOURCE as LOCAL_EDGE


class ReinforcementsUnavailable(ValueError):
    """Optional Castle is unavailable before a map tap, never after one."""


class HeroUnavailable(ValueError):
    """Automatic hero identity, availability or selection could not be verified."""


@dataclass
class ExecutionResult:
    success: bool
    reason: str
    verified_taps: int = 0
    first_deploy_at: float | None = None
    uncertain_tap: bool = False
    first_attempt_at: float | None = None


def selected_card(frame, card):
    """Selection is a bright, low-saturation outline on all four card edges."""
    x,y,w,h=card.box
    crop=frame[y:y+h,x:x+w]
    if not crop.size: return False
    white=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,0,195),(180,65,255))>0
    pad=max(3,round(w*.06))
    return (white[pad:-pad,:pad].any(axis=1).mean()>.75 and
            white[pad:-pad,-pad:].any(axis=1).mean()>.75 and
            # Equipment chips can join the card contour above its top edge.
            # Require a continuous horizontal border within that header band,
            # plus both long side borders and the bottom (never portrait alone).
            white[:max(pad,round(h*.25)),pad:-pad].mean(axis=1).max()>.75 and
            # The dark contour can include the card's lower drop shadow.
            white[-max(pad,round(h*.12)):,pad:-pad].any(axis=0).mean()>.75)


def hero_health_visible(frame, card, *, allow_low=False):
    x,y,w,h=card.box
    # A newly deployed card can rise a few pixels above its portrait contour.
    # Include that small header margin, but require the bar's dark enclosure.
    crop=frame[max(0,y-round(h*.04)):y+round(h*.30),x:x+w]
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(35,90,90),(75,255,255))
    if allow_low:
        # A verified deployed hero can be wounded by the time its ability runs.
        # Red/yellow health still counts, but only inside the narrow header
        # widget, with the same dark enclosure as a full green health bar.
        mask |= cv2.inRange(hsv,(0,100,100),(35,255,255))
        mask |= cv2.inRange(hsv,(170,100,100),(180,255,255))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    # A cyan selection-edge highlight is not a health bar. Require a filled
    # green strip with meaningful height, not a one-pixel antialiasing line.
    for contour in contours:
        bx,by,bw,bh=cv2.boundingRect(contour)
        width_ok=(bw>w*.50 and bw/bh>=5) or (allow_low and
                  bw>w*.12 and bw/bh>=1.5 and bx<w*.20 and by<h*.12)
        if (width_ok and h*.025<=bh<h*.15 and
                bx>=w*.03 and bx+bw<=w*.97 and by>=max(2,h*.01) and
                cv2.contourArea(contour)/(bw*bh)>.70):
            rim=max(2,round(h*.02))
            dark=hsv[:,:,2]<110
            above=dark[max(0,by-rim):by,bx:bx+bw]
            below=dark[by+bh:by+bh+rim,bx:bx+bw]
            if above.size and below.size and above.mean()>.35 and below.mean()>.35:
                return True
    return False


class VerifiedExecutor:
    def __init__(self, session, plan, projection, reference, catalog, *, journal_dir=None, spam=False):
        validate_geometry(plan,projection)
        self.session,self.plan,self.projection=session,plan,projection
        self.reference,self.catalog=reference,catalog
        self.stop=session.client.stop_check
        self.matrix=np.eye(3)
        self._camera_features=CameraFeatures()
        self.last_frame=None
        self.battle_gate=BattleFrameGate(session.attack_nav.battlefield_ready,
            lambda frame, **evidence: active_battle_ready(frame,stop_check=self.stop,**evidence))
        self.result=ExecutionResult(False,'not started')
        self.deployed_heroes=set();self.abilities=set();self.skipped_abilities=set()
        self.skipped_units=set()
        self._deployment_observation=None
        self.spam=spam
        self.optional_heroes = {entry.unit_id for entry in plan.army if spam and entry.kind == 'hero'}
        self.touch=None
        self._outer_probe_pending=projection.source in ('registered_default_outer_ring', LOCAL_EDGE)
        self.path=Path(journal_dir or session.config.data_dir/'debug'/'attack-executions')/(uuid.uuid4().hex+'.jsonl')
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def send_taps(self, targets, *, batch=False):
        if self.touch is None:
            if len(targets)==1 and not batch:self.session.input.tap(*targets[0],jitter=0)
            else:self.session.input.tap_many(targets,settle_ms=0)
            return
        from coc_bot.vision import recorder
        recorder.note_action('tap_batch',points=targets,dry_run=False)
        try:self.touch.taps(targets)
        except OSError as exc:
            # A disconnect can happen after any down/up packet. Never switch
            # transports or repeat a group whose delivery is uncertain.
            raise ValueError('Rapid touch connection lost; no taps replayed') from exc

    def note(self, event, **fields):
        # Write intent before sending input. Interrupted runs cannot be resumed.
        with self.path.open('a',encoding='utf-8') as handle:
            handle.write(json.dumps({'at':time.time(),'event':event,**fields})+'\n')
            handle.flush()
            if event in ('map_tap_intent','map_batch_intent','ability_intent','finished'):
                os.fsync(handle.fileno())
        if event=='step':
            logger.info('Attack step {}/{}: {} {}',fields['number']+1,len(self.plan.steps),
                        fields['action'].replace('_',' '),fields.get('unit_id','').replace('_',' '))
        elif event=='deployment_verified':
            logger.info('Deployment confirmed: {} ×{} (remaining {})',fields['unit_id'],fields.get('batch_size',1),fields['quantity_after'])
        elif event=='map_batch_intent':
            logger.info('Deploying {} ×{} as a rapid group',fields['unit_id'],len(fields['targets']))
        elif event=='waiting_for_battle_controls':
            logger.info('Attack paused — waiting for clear battle controls')
        elif event=='battle_controls_restored':
            logger.info('Battle controls restored — checking camera before continuing')
        elif event=='finished':
            logger.info('Attack executor: {} ({} verified deployments)',fields['reason'],fields['verified_taps'])
        elif event=='ability_skipped':
            logger.info('Hero ability skipped: {} — no usable health bar; continuing remaining steps',fields['unit_id'])
        elif event=='reinforcements_skipped':
            logger.info('Clan Castle skipped — {}; continuing the attack',fields['reason'])
        elif event=='hero_skipped':
            logger.info('Hero {} skipped — {}; continuing the attack',fields['unit_id'],fields['reason'])

    def frame(self):
        self._deployment_observation=None
        check_stop(self.stop)
        frame=self.session.capture.screenshot()
        self.last_frame=frame
        ready=frame.shape==self.reference.shape and self.battle_gate.accept(frame)
        if not ready:
            # Timed event rewards can cover a still-running battle. Never tap
            # through them. Resume only after fresh battle controls reappear.
            self.note('waiting_for_battle_controls')
            deadline=time.monotonic()+20
            for _ in range(10):
                check_stop(self.stop)
                if time.monotonic()>=deadline: break
                self.session._sleep(min(1.,deadline-time.monotonic()))
                check_stop(self.stop)
                frame=self.session.capture.screenshot()
                self.last_frame=frame
                ready=frame.shape==self.reference.shape and self.battle_gate.accept(frame)
                if ready:
                    self.note('battle_controls_restored')
                    break
        if not ready:
            cv2.imwrite(str(self.path.with_suffix('.blocked.png')),frame)
            raise ValueError('Battle controls changed; deployment paused')
        self.matrix=affine(compare_camera(self.reference,frame,cache=self._camera_features))
        scale=np.hypot(self.matrix[0,0],self.matrix[1,0])
        if abs(scale-1)>.01: raise ValueError('Battle zoom changed; map must be rebuilt')
        return frame

    def resolve(self, frame, unit_id):
        return resolve_live_card(frame,self.catalog,unit_id,stop_check=self.stop)

    def unavailable(self, unit_id, reason):
        if unit_id == CLAN_CASTLE:
            return ReinforcementsUnavailable(reason)
        if unit_id in self.optional_heroes:
            return HeroUnavailable(reason)
        return ValueError(reason)

    def skip_optional_unit(self, unit_id, exc):
        self.skipped_units.add(unit_id)
        event = 'hero_skipped' if isinstance(exc, HeroUnavailable) else 'reinforcements_skipped'
        self.note(event, unit_id=unit_id, reason=str(exc))

    def find(self, frame, unit_id):
        """Search only inside the army bar, with bounded overlap and fresh slots."""
        for direction in (0,-1,-1,1,1,1,1):
            check_stop(self.stop)
            if direction:
                h,w=frame.shape[:2]
                a,b=(.75,.30) if direction<0 else (.30,.75)
                self.session.input.swipe(round(w*a),round(h*.91),round(w*b),round(h*.91),350)
                self.session._sleep(.15);frame=self.frame()
            try:return frame,self.resolve(frame,unit_id)
            except ValueError as exc:
                if 'hidden or ambiguous' not in str(exc): raise
        raise self.unavailable(unit_id, 'Unit not found after a bounded army-bar search: '+unit_id)

    def target(self, point):
        x,y=self.projection.pixel(point)
        p=self.matrix@np.array([x,y,1.])
        return p[:2]/p[2]

    def position(self, point):
        """Re-measure every pan; there are no remembered swipe counts."""
        observed=self._deployment_observation if self.spam else None
        self._deployment_observation=None
        for attempt in range(5):
            # Reuse the just-verified deployment frame for the next selection.
            # select() still captures/validates the new selection before any
            # map tap, and a pan always requires a newly measured frame.
            check_stop(self.stop)
            frame=(observed[1] if attempt==0 and observed and time.monotonic()-observed[3]<=1.
                   else self.frame());h,w=frame.shape[:2]
            x,y=self.target(point)
            if input_area(x,y,w,h): return frame,(round(x),round(y))
            dx=float(np.clip(w*.48-x,-w*.22,w*.22))
            dy=float(np.clip(h*.46-y,-h*.20,h*.20))
            self.note('pan',dx=dx,dy=dy)
            self.session.input.swipe(round(w*.48),round(h*.46),round(w*.48+dx),round(h*.46+dy),350)
            self.session._sleep(.2)
        raise ValueError('Deployment point could not be brought clear of the controls')

    def select(self, frame, unit_id):
        self._deployment_observation=None
        frame,card=self.find(frame,unit_id)
        # Cards rise/reflow after selection and deployment. Observe twice before
        # deciding the click missed, then permit one fresh, identified CARD tap.
        # Map taps and already-deployed hero abilities must never be retried here.
        for attempt in range(2):
            check_stop(self.stop)
            if unit_id in self.optional_heroes and (card.kind != 'hero' or card.quantity != 1
                                                    or hero_health_visible(frame, card)):
                raise HeroUnavailable('Hero is not ready to deploy: '+unit_id)
            if card.quantity is None or card.quantity<=0:
                raise self.unavailable(unit_id, 'Unit count or availability is unverified: '+unit_id)
            if selected_card(frame,card):return frame,card
            if card.kind in ('hero','siege') and hero_health_visible(frame,card):
                raise ValueError('Unit is already deployed: '+unit_id)
            x,y,w,h=card.box
            self.note('selection_intent',unit_id=unit_id,attempt=attempt+1,box=list(card.box))
            self.send_taps([(x+w//2,y+h//2)])
            for observation in range(2):
                self.session._sleep(.2)
                frame=self.frame()
                try:card=self.resolve(frame,unit_id)
                except ValueError as exc:
                    if observation==0:continue
                    if unit_id == CLAN_CASTLE or unit_id in self.optional_heroes:
                        raise self.unavailable(unit_id, str(exc)) from exc
                    raise
                confirmed=bool(selected_card(frame,card))
                self.note('selection_observation',unit_id=unit_id,confirmed=confirmed,box=list(card.box))
                if unit_id in self.optional_heroes and (card.kind != 'hero' or card.quantity != 1
                                                        or hero_health_visible(frame, card)):
                    raise HeroUnavailable('Hero is not ready to deploy: '+unit_id)
                if card.quantity is None or card.quantity<=0:
                    raise self.unavailable(unit_id, 'Unit count or availability is unverified: '+unit_id)
                if confirmed:return frame,card
        cv2.imwrite(str(self.path.with_suffix('.selection.png')),frame)
        raise self.unavailable(unit_id, 'Unit selection was not confirmed: '+unit_id)

    def deploy(self, unit_id, point):
        frame,target=self.position(point)
        frame,card=self.select(frame,unit_id)
        # Selection cannot grant permission to use stale coordinates.
        h,w=frame.shape[:2];target=tuple(round(n) for n in self.target(point))
        if not input_area(*target,w,h): raise ValueError('Target moved under game controls')
        before=card.quantity
        if self._outer_probe_pending and card.kind!='troop':
            raise ValueError('Outer ring needs a verified troop deployment before support')
        if card.kind in ('hero','siege') and hero_health_visible(frame,card):
            raise ValueError('Unit is already deployed: '+unit_id)
        self.note('map_tap_intent',unit_id=unit_id,quantity_before=before,target=target)
        check_stop(self.stop)
        sent_at=time.time()
        from coc_bot.attack.recovery import AttackCheckpoint
        checkpoint=AttackCheckpoint(self.session.config)
        if checkpoint.load() is None:
            checkpoint.begin('deploying')
        checkpoint.update('deploying',deployment_possible=True,first_attempt_at=
                          checkpoint.load().get('first_attempt_at',sent_at),journal=self.path.name)
        self.result.first_attempt_at=self.result.first_attempt_at or sent_at
        self.result.uncertain_tap=True
        cv2.imwrite(str(self.path.with_suffix('.before.png')),frame)
        self.send_taps([target])
        # No retry of a map tap, including when capture/OCR fails after it.
        for attempt in range(2):
            # The rapid connection omits InputController's random settle.
            # Let single-use cards finish rising before reading their health
            # bars; otherwise a premature screenshot costs a whole extra
            # recognition cycle. This waits, never resends the deployment.
            self.session._sleep(.45 if attempt==0 and self.touch is not None
                                and card.kind in ('hero','siege') else .2)
            after_frame=self.frame()
            cv2.imwrite(str(self.path.with_suffix('.after.png')),after_frame)
            try:
                after=self.resolve(after_frame,unit_id)
            except ValueError:
                try:
                    after=resolve_just_depleted(after_frame,self.catalog,card,stop_check=self.stop)
                except ValueError:
                    # A rising card can be between layouts during deployment.
                    # Retry observation only; never send another map tap.
                    if attempt==0: continue
                    raise
            self.note('deployment_observation',unit_id=unit_id,quantity=after.quantity)
            good=(after.quantity==before-1 if card.kind not in ('hero','siege') or unit_id == CLAN_CASTLE else
                  hero_health_visible(after_frame,after) or card.kind=='siege' and after.quantity==0)
            if good:
                self.result.uncertain_tap=False
                self.result.verified_taps+=1
                if card.kind=='troop':self._outer_probe_pending=False
                self.result.first_deploy_at=self.result.first_deploy_at or sent_at
                if card.kind=='hero':
                    self.deployed_heroes.add(unit_id)
                self._deployment_observation=(unit_id,after_frame,after,time.monotonic())
                self.note('deployment_verified',unit_id=unit_id,quantity_after=after.quantity)
                return
        raise ValueError('No verified deployment change for '+unit_id+'; remaining taps stopped')

    def ability(self, unit_id):
        check_stop(self.stop)
        if unit_id not in self.deployed_heroes or unit_id in self.abilities or unit_id in self.skipped_abilities:
            raise ValueError('Hero ability has no verified deployment')
        observed=self._deployment_observation
        if self.spam and observed and observed[0]==unit_id and time.monotonic()-observed[3]<=1.:
            # The immediately preceding deployment already proved this card's
            # health bar in a current battle frame. No intervening input.
            _,frame,card,_=observed
        else:
            frame,card=self.find(self.frame(),unit_id)
        if unit_id in self.optional_heroes and card.kind != 'hero':
            raise HeroUnavailable('Hero ability identity is unverified: '+unit_id)
        if not hero_health_visible(frame,card,allow_low=True):
            # Already deployed and freshly identified, but dead/auto-triggered
            # or too uncertain to tap. Other heroes can still have abilities.
            self.skipped_abilities.add(unit_id)
            self.note('ability_skipped',unit_id=unit_id)
            return
        x,y,w,h=card.box
        self.note('ability_intent',unit_id=unit_id)
        self.send_taps([(x+w//2,y+h//2)])
        self.abilities.add(unit_id)
        self.note('ability_sent',unit_id=unit_id)

    def deploy_batch(self, unit_id, points, *, spam=False):
        """One selected card, clear targets, and one exact count delta.

        Spam air/Rage groups can contain <=20 taps, sent in interruptible chunks
        of at most five. A partial/uncertain burst is never retried.
        """
        supported=('electro_dragon','dragon','balloon','barbarian','archer','rage','rage_spell') if spam else (
            'barbarian','archer','giant','wall_breaker','wizard')
        if unit_id not in supported:
            raise ValueError('Only supported ground troops can use deployment batches')
        if not 1<=len(points)<=(20 if spam else 5):raise ValueError('Invalid deployment batch')
        if self._outer_probe_pending:
            self.note('outer_ring_probe',unit_id=unit_id)
            self.deploy(unit_id,points[0])
            if len(points)>1:self.deploy_batch(unit_id,points[1:],spam=spam)
            return
        if len(points)==1:return self.deploy(unit_id,points[0])
        check_stop(self.stop)
        frame,_=self.position(points[0]);frame,card=self.select(frame,unit_id)
        expected_kind='spell' if spam and unit_id in ('rage','rage_spell') else 'troop'
        if card.kind!=expected_kind or card.quantity is None or card.quantity<len(points):
            raise ValueError('Batch unit availability is unverified')
        h,w=frame.shape[:2]
        targets=[tuple(round(v) for v in self.target(point)) for point in points]
        remainder=[]
        if spam:
            # Keep the visible prefix fast; remeasure the camera before any
            # remaining offscreen target. Never tap through army/HUD controls.
            count=next((i for i,target in enumerate(targets) if not input_area(*target,w,h)),len(targets))
            if not count:raise ValueError('Spam target moved under game controls')
            remainder=points[count:];points=points[:count];targets=targets[:count]
        elif not all(input_area(*target,w,h) for target in targets):
            # Nothing has been sent. Reposition and verify individual targets
            # when this camera cannot safely show a whole batch.
            for point in points:self.deploy(unit_id,point)
            return
        self.note('map_batch_intent',unit_id=unit_id,quantity_before=card.quantity,targets=targets)
        check_stop(self.stop);sent_at=time.time()
        from coc_bot.attack.recovery import AttackCheckpoint
        checkpoint=AttackCheckpoint(self.session.config)
        if checkpoint.load() is None:checkpoint.begin('deploying')
        checkpoint.update('deploying',deployment_possible=True,first_attempt_at=
                          checkpoint.load().get('first_attempt_at',sent_at),journal=self.path.name)
        self.result.first_attempt_at=self.result.first_attempt_at or sent_at
        self.result.uncertain_tap=True
        cv2.imwrite(str(self.path.with_suffix('.before.png')),frame)
        if spam:
            for start in range(0,len(targets),5):
                check_stop(self.stop)
                self.send_taps(targets[start:start+5],batch=True)
        else:self.session.input.tap_many(targets)
        self.note('map_batch_sent',unit_id=unit_id,count=len(targets),spam=spam)
        for attempt in range(2):
            self.session._sleep(.2);after_frame=self.frame()
            cv2.imwrite(str(self.path.with_suffix('.after.png')),after_frame)
            try:
                after=self.resolve(after_frame,unit_id)
            except ValueError:
                try:after=resolve_just_depleted(after_frame,self.catalog,card,stop_check=self.stop,spent=len(points))
                except ValueError:
                    if attempt==0:continue
                    raise
            self.note('deployment_batch_observation',unit_id=unit_id,quantity=after.quantity)
            if after.quantity==card.quantity-len(points):
                self.result.uncertain_tap=False;self.result.verified_taps+=len(points)
                self.result.first_deploy_at=self.result.first_deploy_at or sent_at
                self.note('deployment_verified',unit_id=unit_id,quantity_after=after.quantity,batch_size=len(points))
                self._deployment_observation=(unit_id,after_frame,after,time.monotonic())
                if remainder:self.deploy_batch(unit_id,remainder,spam=True)
                return
        raise ValueError('Batch count change was not confirmed; no taps will be replayed')

    def run(self):
        self.note('started',plan=self.plan.to_dict())
        try:
            frame=self.frame()
            # Re-read every used unit before the first map tap.
            for entry in self.plan.army:
                if any(step.unit_id==entry.unit_id for step in self.plan.steps):
                    try:
                        frame,card=self.find(frame,entry.unit_id)
                        if entry.unit_id == CLAN_CASTLE and card.quantity != 1:
                            raise ReinforcementsUnavailable('No available Clan Castle troops')
                        if entry.unit_id in self.optional_heroes and (
                            card.kind != 'hero' or card.quantity != 1 or hero_health_visible(frame, card)
                        ):
                            raise HeroUnavailable('Hero is not ready to deploy')
                    except (ReinforcementsUnavailable, HeroUnavailable) as exc:
                        self.skip_optional_unit(entry.unit_id, exc)
                        # find() may have scrolled the army bar; never reuse
                        # the earlier frame for the next preflight unit.
                        frame=self.frame()
                        continue
                    if card.kind!=entry.kind or card.quantity is None or card.quantity<entry.quantity:
                        raise ValueError('Live army differs from the reviewed plan: '+entry.unit_id)
                    if card.kind in ('hero','siege') and hero_health_visible(frame,card):
                        raise ValueError('Unit is already deployed: '+entry.unit_id)
            if self.spam and getattr(self.session.input,'dry_run',True) is False:
                from coc_bot.adb.multitouch import Multitouch
                touch=Multitouch(self.session.client,(frame.shape[1],frame.shape[0]))
                try:self.touch=touch.__enter__()
                except AdbStopped:raise
                except (ValueError, OSError, RuntimeError):
                    # Startup has sent no touches. The existing transport is
                    # still safe here; no fallback is allowed after a send.
                    touch.close()
                    self.note('rapid_touch_unavailable')
                else:self.note('rapid_touch_ready')
            for number,step in enumerate(self.plan.steps):
                check_stop(self.stop);self.note('step',number=number,action=step.action,unit_id=step.unit_id)
                if step.unit_id in self.skipped_units:
                    continue
                if step.action=='wait':
                    self._deployment_observation=None;self.session._sleep(step.seconds)
                elif step.action=='ability':
                    try:
                        self.ability(step.unit_id)
                    except HeroUnavailable as exc:
                        self.skip_optional_unit(step.unit_id, exc)
                else:
                    points=step_points(step)
                    if (self.spam and self.plan.strategy in ('mass_electro_dragons','mass_dragons') and
                            step.unit_id in ('electro_dragon','dragon','balloon','barbarian','archer','rage','rage_spell')):
                        for start in range(0,len(points),20):self.deploy_batch(step.unit_id,points[start:start+20],spam=True)
                    elif (getattr(self.session.config,'progression_enabled',False) is True and
                            self.plan.strategy=='farming_ground' and step.action=='deploy_line'):
                        for start in range(0,len(points),5):self.deploy_batch(step.unit_id,points[start:start+5])
                    else:
                        for point in points:
                            try:
                                self.deploy(step.unit_id,point)
                            except (ReinforcementsUnavailable, HeroUnavailable) as exc:
                                self.skip_optional_unit(step.unit_id, exc)
                                break
            self.result.success,self.result.reason=True,'All planned deployments verified'
            if self.skipped_units:
                self.result.reason='Available planned deployments verified; skipped: '+', '.join(sorted(self.skipped_units))
                if not self.result.verified_taps:
                    self.result.success=False
                    self.result.reason='No available units were deployed'
            if self.skipped_abilities:
                self.result.reason+='; unavailable abilities skipped: '+', '.join(sorted(self.skipped_abilities))
        except ValueError as exc:
            self.result.reason=str(exc)
            if self.last_frame is not None:
                cv2.imwrite(str(self.path.with_suffix('.failed.png')),self.last_frame)
        except AdbStopped:
            self.result.reason='Stopped'
            raise
        except Exception as exc:
            self.result.reason=f'{type(exc).__name__}: {exc}'
            raise
        finally:
            if self.touch is not None:
                self.touch.close();self.touch=None
            self.note('finished',**vars(self.result))
        return self.result

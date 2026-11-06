"""Account-local Home wall evidence. The upgrade journal alone controls spending."""
from contextlib import closing, contextmanager
import json
import sqlite3
import time
import uuid

import cv2
from loguru import logger

# Fixed per-profile limits. A full store of unresolved intents blocks new spending.
MAX_INTENTS = 4
MAX_OBSERVATIONS = 10
MAX_PNG_BYTES = 4 * 1024 * 1024


class EvidenceError(Exception):
    pass


def account(runner):
    tag = runner.config.account_tag
    return tag or 'profile:' + str(runner.path.parent.resolve())


@contextmanager
def transaction(runner):
    path = runner.path.with_name('wall-evidence.sqlite3')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA foreign_keys = ON')
            db.execute('BEGIN IMMEDIATE')
            db.execute("""CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, account TEXT NOT NULL, receipt TEXT NOT NULL, confirmed_at REAL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS observations (
                intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
                recorded_at REAL NOT NULL, stage TEXT NOT NULL, readings TEXT NOT NULL, png BLOB NOT NULL)""")
            yield db
    except (OSError, sqlite3.Error, cv2.error, ValueError, TypeError) as exc:
        raise EvidenceError(str(exc)) from exc


def insert_observation(db, intent_id, stage, frame, readings):
    ok, png = cv2.imencode('.png', frame)
    if not ok or png.nbytes > MAX_PNG_BYTES:
        raise EvidenceError('Wall screenshot could not be stored within the evidence limit')
    db.execute('INSERT INTO observations VALUES (?, ?, ?, ?, ?)',
               (intent_id, time.time(), stage, json.dumps(readings), png.tobytes()))


def begin(runner, state, receipt, queue_frames, selection_frame=None):
    """Commit all before evidence before publishing a recoverable payment intent."""
    from coc_bot.upgrades.runner import write_json
    if state.get('pending'):
        return {'status': 'needs_review', 'message': 'Existing payment requires review'}
    if getattr(runner, 'inventory_directory', None) != 'builder_base':
        if len(queue_frames) != 2:
            return {'status': 'blocked', 'message': 'Two before queue frames are required'}
        intent_id = uuid.uuid4().hex
        receipt = receipt | {'intent_id': intent_id, 'account': account(runner)}
        try:
            with transaction(runner) as db:
                if db.execute('SELECT count(*) FROM intents').fetchone()[0] >= MAX_INTENTS:
                    removed = db.execute("""DELETE FROM intents WHERE id = (
                        SELECT id FROM intents WHERE confirmed_at IS NOT NULL ORDER BY confirmed_at LIMIT 1)""")
                    if not removed.rowcount:
                        raise EvidenceError('All wall evidence slots require review')
                db.execute('INSERT INTO intents VALUES (?, ?, ?, NULL)',
                           (intent_id, receipt['account'], json.dumps(receipt)))
                for frame in queue_frames:
                    insert_observation(db, intent_id, 'before_queue', frame, {
                        'remaining': receipt['remaining_before'], 'target_level': receipt['target_level']})
                if selection_frame is not None:
                    insert_observation(db, intent_id, 'before_selection', selection_frame, {
                        'count': receipt['count'], 'cost': receipt['cost'], 'balance': receipt['balance_before']})
        except EvidenceError as exc:
            return {'status': 'blocked', 'message': f'Wall before evidence unavailable: {exc}'}
    updated = state | {'pending': receipt}
    try:
        write_json(runner.path, updated)
    except OSError as exc:
        return {'status': 'needs_review', 'message': f'Wall intent journal could not be saved: {exc}'}
    state.update(updated)


def observe(runner, receipt, stage, frame, **readings):
    if 'intent_id' not in receipt:
        return  # Legacy or Builder Base receipt.
    with transaction(runner) as db:
        ident = receipt['intent_id']
        stored = db.execute('SELECT account FROM intents WHERE id = ? AND confirmed_at IS NULL', (ident,)).fetchone()
        if stored != (account(runner),) or stored != (receipt.get('account'),):
            raise EvidenceError('Wall evidence account or intent could not be verified')
        count = db.execute('SELECT count(*) FROM observations WHERE intent_id = ?', (ident,)).fetchone()[0]
        if count >= MAX_OBSERVATIONS:
            raise EvidenceError('Wall observation limit reached; existing evidence retained')
        insert_observation(db, ident, stage, frame, readings)


def mark_confirmed(runner, receipt):
    # Only a durably completed journal can make an evidence slot recyclable.
    if 'intent_id' in receipt:
        try:
            with transaction(runner) as db:
                db.execute('UPDATE intents SET confirmed_at = ? WHERE id = ? AND account = ?',
                           (time.time(), receipt['intent_id'], receipt['account']))
        except EvidenceError as exc:
            logger.warning('Confirmed wall evidence remains reserved: {}', exc)

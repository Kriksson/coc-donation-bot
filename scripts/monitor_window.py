"""Summarize one CasaOS monitor window from its recorded samples (no device access)."""
import argparse
import json
from datetime import datetime
from pathlib import Path


def epoch(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return value if type(value) in (float, int) else None


def summarize(meta, rows, donor):
    start, end = meta['started_at'], meta['ends_at']
    cadence = meta['interval_seconds']
    # Include a boundary probe only as the right endpoint of the preceding interval.
    rows = sorted((r for r in rows if r['at'] >= start), key=lambda r: r['at'])
    samples = [r for r in rows if r['at'] <= end]
    stop = min(end, rows[-1]['at']) if rows else start
    seconds = dict(observed=0.0, active=0.0, stopped=0.0, manual=0.0, donor_chat=0.0)
    largest = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = min(stop, right['at']) - left['at']
        if dt <= 0:
            break
        interval = right['at'] - left['at']
        largest = max(largest, interval)
        status = left.get('status') or {}
        if 'probe_error' in left or type(status.get('active')) is not bool or interval > 1.5 * cadence:
            continue
        seconds['observed'] += dt
        seconds['active' if status['active'] else 'stopped'] += dt
        if status.get('manual_control'):
            seconds['manual'] += dt
        elif (status['active'] and (left.get('account') or {}).get('nickname') == donor
              and status.get('activity') in ('Watching clan chat', 'Checking requests')):
            seconds['donor_chat'] += dt

    attacks, upgrades, incidents = set(), set(), {}
    for sample in samples:
        for profile in sample.get('profiles', []):
            account = profile['id']
            files = profile['files']
            attack = files.get('attack-planner/last-attack.json') or {}
            execution = profile.get('execution') or {}
            at = epoch(attack.get('completed_at'))
            if (at is not None and start <= at <= end and attack.get('phase') == 'completed'
                    and attack.get('id') and attack.get('journal') and attack['journal'] == execution.get('journal')
                    and execution.get('success') is True and execution.get('verified_taps', 0) > 0):
                attacks.add((account, attack['id']))
            for file in ('upgrades/state.json', 'builder_base/upgrades.json'):
                state = files.get(file) or {}
                if state.get('unreadable'):
                    continue
                receipt = state.get('last_completed') or {}
                at = epoch(receipt.get('confirmed_at') or receipt.get('at'))
                if at is not None and start <= at <= end and receipt.get('phase') == 'confirmed':
                    upgrades.add((account, file, at, receipt.get('name'), receipt.get('cost')))
                pending = state.get('pending')
                if isinstance(pending, dict) and pending:
                    key = (account, file, pending.get('at'), pending.get('kind'))
                    incident = incidents.setdefault(key, dict(account=profile['nickname'], kind=pending.get('kind'),
                        intent_at=pending.get('at'), first_observed=sample['at'], observations=0))
                    incident.update(last_observed=sample['at'], observations=incident['observations']+1)
    return dict(status=meta['status'], elapsed_seconds=round(stop-start,2), samples=len(samples),
                probe_errors=sum('probe_error' in r for r in samples), largest_interval_seconds=round(largest,2),
                unknown_seconds=round(max(0,stop-start-seconds['observed']),2),
                sampled_seconds={k:round(v,2) for k,v in seconds.items()},
                donor_chat_percent_of_elapsed=round(100*seconds['donor_chat']/(stop-start),1) if stop>start else None,
                observed_completed_attacks=len(attacks), observed_confirmed_upgrades=len(upgrades),
                observed_pending_intents=list(incidents.values()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--donor', default='King War')
    args = parser.parse_args()
    meta = json.loads((args.folder/'meta.json').read_text())
    with (args.folder/'samples.jsonl').open() as stream:
        print(json.dumps(summarize(meta, (json.loads(line) for line in stream if line.endswith('\n')), args.donor), indent=2))

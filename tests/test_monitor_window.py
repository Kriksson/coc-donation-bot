import unittest
from scripts.monitor_window import summarize


class MonitorWindowTests(unittest.TestCase):
    def test_gaps_errors_and_boundary_do_not_inflate_chat_or_receipts(self):
        meta = dict(started_at=100, ends_at=150, interval_seconds=10, status='completed')
        sample = dict(account={'nickname':'King War'}, status={'active':True,'activity':'Watching clan chat'})
        state = {'pending':{'kind':'wall','at':50}}
        profile = dict(id='a',nickname='King War',files={'upgrades/state.json':state})
        rows = [dict(sample,at=101,profiles=[profile]),dict(sample,at=111,profiles=[profile]),
                {'at':135,'probe_error':'timeout'},dict(sample,at=145),dict(sample,at=151)]
        report = summarize(meta,rows,'King War')
        self.assertEqual(report['samples'],4)
        self.assertEqual(report['sampled_seconds']['donor_chat'],15)
        self.assertEqual(report['unknown_seconds'],35)
        self.assertEqual(report['observed_confirmed_upgrades'],0)
        self.assertEqual(report['observed_pending_intents'][0]['observations'],2)
        rows[-1]['at'] = 300  # A much later probe cannot establish endpoint coverage.
        self.assertEqual(summarize(meta,rows,'King War')['unknown_seconds'],40)

    def test_home_and_matching_successful_execution_are_both_required(self):
        meta = dict(started_at=100, ends_at=140, interval_seconds=10, status='completed')
        receipt = dict(id='battle',phase='completed',journal='battle.jsonl',completed_at=120)
        profile = dict(id='a',nickname='Main',files={'attack-planner/last-attack.json':receipt},
                       execution={'journal':'other.jsonl','verified_taps':4,'success':True})
        row = {'at':130,'profiles':[profile]}
        self.assertEqual(summarize(meta,[row],'Main')['observed_completed_attacks'],0)
        profile['execution'].update(journal='battle.jsonl',success=False)
        self.assertEqual(summarize(meta,[row],'Main')['observed_completed_attacks'],0)
        profile['execution']['success']=True
        self.assertEqual(summarize(meta,[row,row],'Main')['observed_completed_attacks'],1)

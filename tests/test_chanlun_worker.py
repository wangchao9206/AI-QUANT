"""Real-engine prefix parity and audit semantics, without orders or PnL."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from chanlun_worker.adapters import ADAPTERS
from chanlun_worker.analysis import analyze, canonical
from chanlun_worker.data import load_dataset


class ChanWorkerTests(unittest.TestCase):
    def test_prefix_matches_direct_rebuild_for_each_available_engine(self):
        for name in ('native', 'chanpy', 'czsc', 'baseline'):
            with self.subTest(engine=name):
                observed = analyze(name, 501)
                adapter = ADAPTERS[name]()
                for bar in load_dataset()[:501]:
                    adapter.push(bar)
                self.assertEqual(sorted(canonical(s['raw']) for s in observed['structures']),
                                 sorted(canonical(s) for s in adapter.structures()))
                self.assertEqual(len(observed['bars']), 501)
                self.assertTrue(all(e['endIndex'] < 501 for e in observed['events']))
                self.assertTrue(all(e['observedDate'] <= observed['observedAsOfDate'] for e in observed['events']))
                self.assertTrue(all(s['eligibleAt'] is None for s in observed['structures']))

    def test_future_price_changes_do_not_change_past_structures_or_events(self):
        altered = copy.deepcopy(load_dataset())
        for bar in altered[501:]:
            for key in ('open','high','low','close'):
                bar[key] *= 3
        for engine in ('native','chanpy'):
            original = analyze(engine, 501)
            with patch('chanlun_worker.analysis.load_dataset', return_value=altered):
                replay = analyze(engine, 501)
            self.assertEqual(original['structures'], replay['structures'])
            self.assertEqual([{k:v for k,v in e.items() if k!='recordedAt'} for e in original['events']],
                             [{k:v for k,v in e.items() if k!='recordedAt'} for e in replay['events']])

    def test_revision_and_retraction_keep_original_observation_and_identity(self):
        class RevisingAdapter:
            version='test';parameters={};layers=['BI']
            def push(self,bar): self.index=bar['index']
            def structures(self):
                if self.index in (2,4) or self.index>4:return []
                return [{'type':'BI','startIndex':0,'endIndex':self.index,'direction':'UP',
                         'startPrice':1.,'endPrice':float(self.index+2),'engineConfirmed':self.index==1}]
        with patch.dict(ADAPTERS,{'fixture':RevisingAdapter}):
            result=analyze('fixture',50)
        events=result['events']
        self.assertEqual([e['eventType'] for e in events],['OBSERVED','REVISED','RETRACTED','OBSERVED','RETRACTED'])
        self.assertEqual([e['revision'] for e in events],[1,2,3,4,5])
        self.assertEqual(len({e['id'] for e in events}),1)
        self.assertEqual(len({e['firstObservedDate'] for e in events}),1)
        self.assertGreater(events[1]['engineConfirmedDate'],events[1]['firstObservedDate'])
        self.assertEqual(events[3]['priorRevision'],3)

    def test_reproduces_reviewed_full_history_counts(self):
        self.assertEqual(analyze('chanpy',1894)['counts'],{'BI':103,'SEGMENT':17,'ZONE':13})
        self.assertEqual(analyze('czsc',1894)['counts'],{'BI':153,'ZONE':20})

    def test_bounds_and_license_cannot_be_bypassed(self):
        for count in (0,49,1895,5001):
            with self.assertRaises(ValueError):analyze('chanpy',count)
        with self.assertRaises(ValueError):analyze('pro',501)


if __name__=='__main__': unittest.main()

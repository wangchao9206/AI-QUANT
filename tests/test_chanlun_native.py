"""Independent geometry, chronology and signal counterexamples for our kernel."""
import copy
import math
import unittest

from chanlun_worker.data import load_dataset
from chanlun_worker.native import NativeEngine, SegmentModel, Stroke, ZoneSignalModel


def strokes(points):
    return [Stroke(i,i+1,a,b,i+2) for i,(a,b) in enumerate(zip(points,points[1:]))]


def candles(count=30):
    return [{'index':i,'open':115.,'high':116.,'low':114.,'close':115.} for i in range(count)]


class NativeGeometryTests(unittest.TestCase):
    def test_flat_and_included_candles_do_not_invent_fractals(self):
        engine=NativeEngine()
        for i in range(50):engine.push({'index':i,'open':100.,'high':102.,'low':98.,'close':100.})
        self.assertEqual(engine.structures(),[])
        self.assertEqual(len(engine.pending.indices),50)

    def test_sealed_structures_are_prefix_stable_and_rebuilds_match(self):
        bars=load_dataset()[:501]
        engine=NativeEngine()
        prefixes={}
        for bar in bars:
            engine.push(bar)
            if bar['index'] in (99,249,500):prefixes[bar['index']]=copy.deepcopy(engine.structures())
        final=engine.structures()
        for end,observed in prefixes.items():
            rebuilt=NativeEngine()
            for bar in bars[:end+1]:rebuilt.push(bar)
            self.assertEqual(observed,rebuilt.structures())
            frozen=[s for s in observed if s['type'] in ('FRACTAL','BI','SEGMENT') and s['engineConfirmed']]
            self.assertTrue(frozen)
            for item in frozen:self.assertIn(item,final)
            self.assertTrue(all(s['endIndex']<=end for s in observed))
        self.assertTrue(any(s['type']=='BI' and not s['engineConfirmed'] for s in final))

    def test_segment_without_gap_and_with_gap_are_direction_symmetric(self):
        for sign in (1,-1):
            simple=SegmentModel()
            for pen in strokes([sign*p for p in [0,5,2,8,3,7,1]]):simple.push(pen)
            self.assertEqual(simple.segments[0].b,sign*8)
            self.assertFalse(simple.evidence[0]['hasFeatureGap'])
            model=SegmentModel()
            full=strokes([sign*p for p in [0,5,2,10,7,9,6,8,4,7,5,8]])
            for pen in full[:8]:model.push(pen)
            self.assertEqual(model.segments,[])
            for pen in full[8:]:model.push(pen)
            self.assertEqual(model.segments[0].b,sign*10)
            self.assertTrue(model.evidence[0]['hasFeatureGap'])

    def test_invalid_and_non_contiguous_input_is_rejected(self):
        engine=NativeEngine()
        with self.assertRaises(ValueError):engine.push({'index':1,'open':1,'high':2,'low':0,'close':1})
        with self.assertRaises(ValueError):engine.push({'index':0,'open':1,'high':0,'low':2,'close':1})

    def test_later_bars_do_not_mutate_already_returned_evidence(self):
        bars=load_dataset()[:501]
        engine=NativeEngine()
        for bar in bars[:250]:engine.push(bar)
        observed=engine.structures()
        frozen=copy.deepcopy(observed)
        for bar in bars[250:]:engine.push(bar)
        self.assertEqual(observed,frozen)


class NativeSignalTests(unittest.TestCase):
    def third_point(self,last=112,cross=False,sign=1):
        bars=candles()
        if cross:bars[12]['low']=105
        if sign<0:
            for b in bars:b.update(open=300-b['open'],close=300-b['close'],high=300-b['low'],low=300-b['high'])
        model=ZoneSignalModel(bars,[0.]*len(bars))
        points=[100,110,102,108,104,120,last]
        if sign<0:points=[300-p for p in points]
        for i,pen in enumerate(strokes(points)):
            model.push(Stroke(pen.start,pen.end,pen.a,pen.b,[3,5,7,9,11,15][i]))
        return model

    def test_third_point_requires_strict_retest_and_observation_time(self):
        for sign,kind in ((1,'B3'),(-1,'S3')):
            model=self.third_point(sign=sign)
            points=[s for s in model.signals if s['signalType']==kind]
            self.assertEqual(len(points),1)
            self.assertEqual(points[0]['candidateObservedIndex'],15)
            self.assertEqual(points[0]['endIndex'],6)
            self.assertIn('zoneHigh',points[0]['evidence'])
        self.assertFalse(self.third_point(last=108).signals)
        self.assertFalse(self.third_point(cross=True).signals)

    def test_divergence_needs_trend_context_and_second_point_never_breaks_first(self):
        bars=[{'index':i,'open':93.,'high':94.,'low':92.,'close':93.} for i in range(30)]
        histogram=[0.]*30
        histogram[6:9]=[-10.]*3;histogram[10:13]=[-1.]*3
        model=ZoneSignalModel(bars,histogram)
        model.zones=[{'startIndex':0,'endIndex':2,'low':130.,'high':140.},
                     {'startIndex':3,'endIndex':5,'low':110.,'high':120.}]
        for pen in [Stroke(6,8,100,90,9),Stroke(8,10,90,98,11),Stroke(10,12,98,85,13),
                    Stroke(12,14,85,97,15),Stroke(14,16,97,90,17)]:model.push(pen)
        first=next(s for s in model.signals if s['signalType']=='B1')
        second=next(s for s in model.signals if s['signalType']=='B2')
        self.assertGreater(second['startPrice'],first['startPrice'])
        self.assertLess(first['evidence']['currentArea'],first['evidence']['previousArea'])
        model.invalidate({'index':18,'low':84.,'high':95.})
        self.assertEqual(first['signalState'],'INVALIDATED')
        self.assertEqual(second['signalState'],'INVALIDATED')
        self.assertFalse(first['engineConfirmed'])


if __name__=='__main__':unittest.main()

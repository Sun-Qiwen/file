from pathlib import Path
import sys,unittest,math
from types import SimpleNamespace as NS
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'board/runtime/application'))
from board_pipeline import Pipeline

class RawHeadsModel:
    def __init__(self,model,score):self.cnn=model=='cnn';self.score=score
    def get_inputs(self):return [NS(shape=[1,1,96,96] if self.cnn else [1,3,480,640],name='image')]
    def get_outputs(self):return [NS(shape=[1,2,48,48]),NS(shape=[1,1])] if self.cnn else [NS(shape=[1,6,60,80]),NS(shape=[1,6,30,40]),NS(shape=[1,6,15,20])]
    def run(self,names,feed):
        if self.cnn:raise AssertionError('This test exercises the real detector decode path only')
        heads=[np.zeros((1,6,h,w),np.float32) for h,w in ((60,80),(30,40),(15,20))]
        heads[0][0,2:4,30,30]=math.log(8.)
        heads[0][0,4,30,30]=self.score;heads[0][0,5,30,30]=1.
        return heads

class DetectorThresholdTests(unittest.TestCase):
    def detect(self,score):
        p=Pipeline(ROOT/'board/runtime/application',session_factory=lambda model:RawHeadsModel(model,score))
        return p.detect(np.full((480,640,3),128,np.uint8))
    def test_score_between_point15_and_point30_is_now_a_hand(self):
        rows=self.detect(.2);self.assertEqual(len(rows),1)
        self.assertAlmostEqual(rows[0].confidence,.2,places=6)
    def test_score_below_point15_is_still_rejected(self):
        self.assertEqual(len(self.detect(.149)),0)
    def test_point15_boundary_is_strictly_greater(self):
        self.assertEqual(len(self.detect(.15)),0)
        self.assertEqual(len(self.detect(.1501)),1)

if __name__=='__main__':unittest.main()

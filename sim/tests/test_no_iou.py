from pathlib import Path
import sys,unittest
from types import SimpleNamespace as NS
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'board/runtime/application'))
from board_pipeline import Pipeline
from geometry import HandDetection,TargetSelector

class NoIouModels:
    def __init__(self,model):self.cnn=model=='cnn'
    def get_inputs(self):return [NS(shape=[1,1,96,96] if self.cnn else [1,3,480,640])]
    def get_outputs(self):return [NS(shape=[1,2,48,48]),NS(shape=[1,1])] if self.cnn else [NS(shape=[1,6,60,80]),NS(shape=[1,6,30,40]),NS(shape=[1,6,15,20])]
    def run(self,names,feed):
        if not self.cnn:raise AssertionError('Only neural model inference is substituted')
        heat=np.full((1,2,48,48),-5.,np.float32);heat[0,0,24,12]=10.;heat[0,1,24,30]=10.
        return [heat,np.array([[5.]],np.float32)]

def no_iou_pipeline():return Pipeline(ROOT/'board/runtime/application',session_factory=NoIouModels)
def one(box):return [HandDetection(box,.9)]
A=(50,100,150,200);B=(250,100,350,200);C=(450,100,550,200);D=(50,300,150,400)

class NoIouPolicyTests(unittest.TestCase):
    def run_boxes(self,boxes):
        p=no_iou_pipeline();iterator=iter(boxes);p.detect=lambda frame:next(iterator)
        frame=np.full((480,640,3),128,np.uint8)
        return p,lambda t:p.run_frame(frame,timestamp=float(t))
    def test_nonoverlapping_single_hand_updates_without_losing_target(self):
        p,run=self.run_boxes([one(A),one(C),one(B),one(D)])
        for t in range(4):self.assertEqual(run(t)['status'],'ok')
        self.assertEqual(p.selector.previous.xyxy,D)
    def test_lost_target_recovery_counts_unique_frames_without_overlap(self):
        p,run=self.run_boxes([one(A),[],one(B),one(C),one(D)])
        self.assertEqual([run(t)['status'] for t in range(5)],['ok','target_temporarily_lost','confirming_target','confirming_target','ok'])
    def test_blocked_target_reacquires_three_nonoverlapping_boxes(self):
        p,run=self.run_boxes([one(A)]+[[]]*13+[one(B),one(C),one(D)])
        run(0)
        for t in range(1,14):run(t)
        self.assertEqual([run(t)['status'] for t in range(14,17)],['searching_target','searching_target','ok'])
    def test_missing_frame_still_breaks_blocked_reacquire_streak(self):
        p,run=self.run_boxes([one(A)]+[[]]*13+[one(B),[],one(C),one(D),one(A)])
        for t in range(14):run(t)
        run(14);self.assertEqual(p.reacquire_streak,1)
        run(15);self.assertEqual(p.reacquire_streak,0)
        self.assertEqual([run(t)['status'] for t in range(16,19)],['searching_target','searching_target','ok'])
    def test_multiple_hands_remain_ambiguous_then_unique_frames_recover(self):
        p,run=self.run_boxes([one(A),one(A)+one(C),one(B),one(C),one(D)])
        self.assertEqual([run(t)['status'] for t in range(5)],['ok','ambiguous_target','confirming_target','confirming_target','ok'])
    def test_legacy_selector_still_requires_overlap_by_default(self):
        selector=TargetSelector(lost_grace_frames=12)
        selector.select(one(A),(480,640))
        result=selector.select(one(C),(480,640))
        self.assertIsNone(result.detection);self.assertEqual(result.status,'target_temporarily_lost')

if __name__=='__main__':unittest.main()

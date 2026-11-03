from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'board/runtime/application'),str(ROOT/'board/runtime/application')]
import coin_game

class NoTimeoutTests(unittest.TestCase):
    def make(self):
        now=[100.];sink=coin_game.DirectionState()
        c=coin_game.create_direction_controller(sink,stable_frames=3,clock=lambda:now[0])
        self.addCleanup(c.close)
        return now,sink,c
    def valid(self,stamp=100.,angle=90.,probability=.99):
        return dict(status='ok',valid_probability=probability,angle_degrees=angle,frame_timestamp=stamp)
    def tracking(self,c):
        for _ in range(3):c.update(self.valid())
    def test_last_direction_survives_long_gap_without_results(self):
        now,sink,c=self.make();self.tracking(c);self.assertEqual(sink.read(),3)
        now[0]=130.;c.check_timeout();self.assertEqual(sink.read(),3)
        self.assertEqual(c.update(self.valid(130.)).reason,'tracking')
    def test_older_valid_result_is_not_rejected_by_two_second_age(self):
        now,sink,c=self.make();now[0]=110.
        for stamp in (100.,101.,102.):c.update(self.valid(stamp))
        self.assertEqual(sink.read(),3)
    def test_no_hand_still_stops_and_resets_three_result_confirmation(self):
        now,sink,c=self.make();self.tracking(c);now[0]=130.
        self.assertEqual(c.update(dict(status='no_hand')).direction,12)
        self.assertEqual(c.update(self.valid(130.)).direction,12)
        self.assertEqual(c.update(self.valid(130.)).direction,12)
        self.assertEqual(c.update(self.valid(130.)).direction,3)
    def test_invalid_pose_and_invalid_timestamp_still_stop(self):
        now,sink,c=self.make();self.tracking(c)
        self.assertEqual(c.update(self.valid(probability=.4)).direction,12)
        self.tracking(c)
        self.assertEqual(c.update(self.valid(stamp=101.)).direction,12)
    def test_finish_restart_and_previous_round_frame_gate_still_work(self):
        now,sink,c=self.make();gate=coin_game.RoundControl(c,100.)
        for _ in range(3):gate.update(self.valid())
        self.assertEqual(sink.read(),3);gate.finish();self.assertEqual(sink.read(),12)
        now[0]=130.;gate.restart(130.)
        for _ in range(3):gate.update(self.valid(129.))
        self.assertEqual(sink.read(),12)
        for _ in range(3):gate.update(self.valid(130.))
        self.assertEqual(sink.read(),3)

if __name__=='__main__':unittest.main()

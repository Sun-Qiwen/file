from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'board/runtime/application'),str(ROOT/'board/runtime/application')]
import coin_game,game_state

class SingleFrameTests(unittest.TestCase):
    def make(self):
        now=[100.];sink=coin_game.DirectionState()
        c=coin_game.create_direction_controller(sink,clock=lambda:now[0])
        self.addCleanup(c.close)
        return now,sink,c
    def valid(self,stamp=100.,angle=90.):
        return dict(status='ok',valid_probability=.99,angle_degrees=angle,frame_timestamp=stamp)
    def test_first_valid_direction_moves_car_without_waiting(self):
        now,sink,c=self.make();game=game_state.CoinGame();game.start(100.)
        c.update(self.valid());game.advance(101.,sink.read())
        self.assertEqual((game.x,game.y),(467.,240.))
    def test_new_direction_applies_on_its_first_valid_result(self):
        now,sink,c=self.make()
        c.update(self.valid(angle=0.));self.assertEqual(sink.read(),0)
        c.update(self.valid(angle=90.));self.assertEqual(sink.read(),3)
    def test_no_hand_stops_then_first_valid_result_resumes(self):
        now,sink,c=self.make();c.update(self.valid())
        self.assertEqual(c.update(dict(status='no_hand')).direction,12)
        self.assertEqual(c.update(self.valid()).direction,3)
    def test_previous_round_frame_rejected_then_one_new_frame_starts(self):
        now,sink,c=self.make();gate=coin_game.RoundControl(c,100.)
        c.update(self.valid());now[0]=130.;gate.restart(130.)
        gate.update(self.valid(129.));self.assertEqual(sink.read(),12)
        gate.update(self.valid(130.));self.assertEqual(sink.read(),3)
    def test_normal_command_line_uses_single_frame_default(self):
        class Parsed(Exception):pass
        seen=[];original=coin_game.argparse.ArgumentParser.parse_args
        def capture(parser,*args,**kwargs):
            seen.append(original(parser,[]));raise Parsed()
        with patch.object(coin_game.argparse.ArgumentParser,'parse_args',capture):
            with self.assertRaises(Parsed):coin_game.main()
        self.assertEqual(seen[0].stable_frames,1)

if __name__=='__main__':unittest.main()

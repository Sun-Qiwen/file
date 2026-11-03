import sys,unittest
from pathlib import Path
ROOT=Path(__file__).parents[2]
sys.path[:0]=[str(ROOT/'src/ps/game'),str(ROOT/'src/ps/hdmi/legacy')]
from coin_game import DirectionState
from control import DirectionController
class DirectionTests(unittest.TestCase):
 def test_stale_or_lost_gesture_stops_game_direction(self):
  now=[100.];sink=DirectionState();controller=DirectionController(sink,stable_frames=3,clock=lambda:now[0])
  result=dict(status='ok',valid_probability=.99,angle_degrees=90,frame_timestamp=100.)
  controller.update(result);controller.update(result);self.assertEqual(sink.read(),12)
  controller.update(result);self.assertEqual(sink.read(),3)
  now[0]=102.1;controller.check_timeout();self.assertEqual(sink.read(),12)
  controller.update(dict(status='no_hand'));self.assertEqual(sink.read(),12)
  controller.close()
if __name__=='__main__':unittest.main()

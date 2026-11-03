import sys,unittest,random
from pathlib import Path
import numpy as np
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'board/runtime/application'))
from game_state import CoinGame
from game_renderer import GameRenderer
class RendererTests(unittest.TestCase):
 def test_original_background_and_coin_alpha(self):
  renderer=GameRenderer(ROOT/'data/game/images.npz')
  game=CoinGame(rng=random.Random(9));game.start(0);game.coin=(20,20)
  frame=np.zeros((720,1280),np.uint16)
  renderer.draw(frame,game,0)
  with np.load(ROOT/'data/game/images.npz') as assets:
   self.assertEqual(int(frame[10,10]),int(assets['background'][2,2]))
   region=frame[20:100,20:100];mask=assets['coin_alpha']
   np.testing.assert_array_equal(region[mask],assets['coin'][mask])
   bg=np.repeat(np.repeat(assets['background'],5,axis=0),5,axis=1)
   np.testing.assert_array_equal(region[~mask],bg[20:100,20:100][~mask])
 def test_dirty_car_does_not_leave_trails(self):
  renderer=GameRenderer(ROOT/'data/game/images.npz')
  game=CoinGame(rng=random.Random(9));game.start(0);game.coin=(20,20)
  frame=np.zeros((720,1280),np.uint16);renderer.draw(frame,game,0)
  game.advance(4,3);bands=renderer.draw(frame,game,4)
  np.testing.assert_array_equal(frame[240:480,392:600],renderer.background[240:480,392:600])
  self.assertTrue(bands)
if __name__=='__main__':unittest.main()

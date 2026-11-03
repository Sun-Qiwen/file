import sys, unittest, random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[2]/'board/runtime/application'))
from game_state import CoinGame

class GameStateTests(unittest.TestCase):
    def game(self):
        g=CoinGame(rng=random.Random(7)); g.start(100.0); return g
    def test_60_seconds_is_real_time_and_freezes(self):
        g=self.game(); g.advance(110.0,12)
        self.assertEqual(g.remaining(110.0),50)
        g.advance(160.0,3); before=(g.x,g.y,g.score,g.coin)
        self.assertEqual(g.phase,'finished')
        g.advance(180.0,9)
        self.assertEqual((g.x,g.y,g.score,g.coin),before)
    def test_quarter_speed_and_stop(self):
        g=self.game(); x,y=g.x,g.y
        g.advance(101.0,3); self.assertAlmostEqual(g.x,x+75)
        self.assertEqual(g.y,y)
        g.advance(103.0,12); self.assertAlmostEqual(g.x,x+75)
    def test_pickup_scores_once_and_respawns_outside_body(self):
        g=self.game(); g.coin=(g.x+80,g.y+80)
        old=g.coin; g.advance(100.1,12)
        self.assertEqual(g.score,1); self.assertNotEqual(g.coin,old)
        g.advance(100.2,12); self.assertEqual(g.score,1)
    def test_deadline_wins_over_pickup(self):
        g=self.game(); g.coin=(g.x+80,g.y+80)
        g.advance(160.0,12); self.assertEqual(g.score,0)
    def test_boundary_and_spawn_are_reachable(self):
        g=self.game(); g.advance(120.0,3); self.assertEqual(g.x,784)
        g.advance(140.0,6); self.assertEqual(g.y,480)
        for _ in range(200):
            g.spawn_coin(); x,y=g.coin
            self.assertGreaterEqual(x,0); self.assertLessEqual(x+80,1024)
            self.assertGreaterEqual(y,0); self.assertLessEqual(y+80,720)
            self.assertFalse(g.coin_overlaps_car())
    def test_swept_pickup_on_delayed_render(self):
        g=self.game(); g.coin=(700,320)
        g.advance(104.0,3); self.assertEqual(g.score,1)
    def test_backwards_clock_rejected(self):
        g=self.game()
        with self.assertRaises(ValueError): g.advance(99.0,3)

if __name__=='__main__': unittest.main()

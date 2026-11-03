import sys,unittest,random
from pathlib import Path
ROOT=Path(__file__).parents[2]
sys.path[:0]=[str(ROOT/'board/runtime/application'),str(ROOT/'board/runtime/application')]
import game_state,coin_game
from control import DirectionController,MemorySink

class RestartTests(unittest.TestCase):
    def test_restart_clears_position_score_and_deadline(self):
        rounds=game_state.GameRounds(100.,rng=random.Random(7))
        self.assertEqual(rounds.tick(103.,12),'start')
        rounds.game.coin=(rounds.game.x+80,rounds.game.y+80)
        rounds.tick(103.1,12);rounds.tick(105.,3)
        self.assertEqual(rounds.game.score,1)
        self.assertTrue(rounds.observe_button(1,110.))
        self.assertEqual((rounds.game.phase,rounds.game.score,rounds.game.x,rounds.game.y),('ready',0,392.,240.))
        self.assertIsNone(rounds.game.started)
        self.assertIsNone(rounds.tick(112.99,3))
        self.assertEqual(rounds.tick(113.,12),'start')
        self.assertEqual(rounds.game.deadline,173.)
    def test_result_is_once_and_can_restart(self):
        rounds=game_state.GameRounds(100.)
        rounds.tick(103.,12)
        self.assertEqual(rounds.tick(163.,12),'result')
        self.assertIsNone(rounds.tick(164.,12))
        self.assertTrue(rounds.observe_button(1,165.))
        self.assertEqual(rounds.tick(168.,12),'start')
        self.assertEqual(rounds.tick(228.,12),'result')
        self.assertEqual(rounds.round_id,2)
    def test_startup_baseline_hold_and_wrap(self):
        rounds=game_state.GameRounds(100.,button_count=65535)
        self.assertFalse(rounds.observe_button(65535,101.))
        self.assertTrue(rounds.observe_button(0,102.))
        self.assertFalse(rounds.observe_button(0,103.))
        self.assertEqual(rounds.ready_until,105.)
        self.assertTrue(rounds.observe_button(1,104.))
        self.assertEqual(rounds.round_id,3)
    def test_old_inflight_result_cannot_resume_after_restart(self):
        now=[100.]
        sink=MemorySink();controller=DirectionController(sink,clock=lambda:now[0])
        gate=coin_game.RoundControl(controller,100.)
        def result(stamp):return dict(status='ok',valid_probability=.9,angle_degrees=90.,frame_timestamp=stamp)
        for _ in range(3):gate.update(result(100.))
        self.assertEqual(sink.commands[-1],3)
        now[0]=101.;gate.restart(101.)
        gate.update(result(100.9))
        self.assertEqual(sink.commands[-1],12)
        gate.update(result(101.));gate.update(result(101.))
        self.assertEqual(sink.commands[-1],12)
        gate.update(result(101.))
        self.assertEqual(sink.commands[-1],3)
    def test_finish_freezes_control_until_restart(self):
        sink=MemorySink();controller=DirectionController(sink,clock=lambda:100.)
        gate=coin_game.RoundControl(controller,100.)
        result=dict(status='ok',valid_probability=.9,angle_degrees=90.,frame_timestamp=100.)
        gate.finish()
        for _ in range(4):gate.update(result)
        self.assertFalse(gate.is_active());self.assertEqual(sink.commands[-1],12)
        gate.restart(100.)
        for _ in range(3):gate.update(result)
        self.assertTrue(gate.is_active());self.assertEqual(sink.commands[-1],3)

class FinishedFailureTests(unittest.TestCase):
    def test_finished_worker_error_exits_and_cleans_without_button(self):
        import tempfile,threading,os
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        now=[100.];state=dict(finished=False,display_closed=False,engine_closed=False,capture_closed=False,ticks=0)
        class QuitEvent:
            def is_set(self):
                state['ticks']+=1
                if state['ticks']>100:raise AssertionError('finished branch ignored worker failure')
                return False
            def wait(self,delay):now[0]+=.1;return False
            def set(self):pass
        class Display:
            def __init__(self,*args):self.front=None;self.buffers=[object(),object()]
            def restart_count(self):return 0
            def present(self,index,**kwargs):self.front=index
            def stats(self):return dict(underflow_lines=0,read_errors=0,video_frames=1,presented_frames=1)
            def close(self,**kwargs):state['display_closed']=True
        class Renderer:
            def __init__(self,*args):pass
            def draw(self,frame,game,*args,**kwargs):
                if game.phase=='finished':state['finished']=True
                return []
        class Capture:
            def __init__(self,*args):pass
            def close(self,**kwargs):state['capture_closed']=True
        class Worker:
            def __init__(self,engine,pipeline,capture,controller,*args):
                self.control=coin_game.RoundControl(controller,now[0]);self.stop=threading.Event()
                self.thread=NS(start=lambda:None,ident=None)
            def snapshot(self):
                return None,'stopped',('camera failure after result' if state['finished'] else None),0
        camera=NS(isOpened=lambda:True,set=lambda *args:True)
        engine=NS(overlay=NS(ip_dict={name:dict(phys_addr=address) for name,address in
                  [('engine',0x43c00000),('perf',0x43c10000),('ddr_hdmi_0',0x40020000)]}),
                  factory=None,close=lambda:state.update(engine_closed=True))
        modules={'board_pipeline':NS(Pipeline=lambda *args,**kwargs:object()),'capture':NS(LatestFrames=Capture),
                 'game_renderer':NS(GameRenderer=Renderer),'ddr_display':NS(DDRDisplay=Display),
                 'cv2':NS(VideoCapture=lambda *args:camera,CAP_V4L2=0,CAP_PROP_FOURCC=1,CAP_PROP_FRAME_WIDTH=2,
                          CAP_PROP_FRAME_HEIGHT=3,CAP_PROP_FPS=4,CAP_PROP_BUFFERSIZE=5,VideoWriter_fourcc=lambda *args:0)}
        with tempfile.TemporaryDirectory(dir=os.environ.get('COIN_TEST_TEMP')) as temporary:
            argv=['coin_game.py','--duration','.1','--log-dir',str(Path(temporary)/'logs')]
            with patch.dict(sys.modules,modules),patch.object(sys,'argv',argv),patch.object(coin_game,'verify_package',lambda root:None), \
                 patch.object(coin_game,'create_engine',lambda root:engine),patch.object(coin_game,'InferenceWorker',Worker), \
                 patch.object(coin_game,'time',NS(monotonic=lambda:now[0])),patch.object(coin_game.signal,'signal',lambda *args:None), \
                 patch.object(coin_game,'threading',NS(Event=QuitEvent,Lock=threading.Lock,Thread=threading.Thread)):
                with self.assertRaisesRegex(RuntimeError,'camera failure after result'):coin_game.main()
        self.assertTrue(state['display_closed']);self.assertTrue(state['engine_closed']);self.assertTrue(state['capture_closed'])

if __name__=='__main__':unittest.main()

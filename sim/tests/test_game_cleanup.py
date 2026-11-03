import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[2]/'board/runtime/application'))
from coin_game import shutdown_resources
class Resource:
 def __init__(self,failures=0):self.failures=failures;self.closed=False;self.stopped=False
 def close(self,**kwargs):
  if self.failures:self.failures-=1;raise OSError('injected close failure')
  self.closed=True
 def stop(self,*args,**kwargs):self.stopped=True
class CleanupTests(unittest.TestCase):
 def run_case(self,which):
  capture,controller,display,engine=[Resource() for _ in range(4)]
  resources=dict(capture=capture,controller=controller,display=display,engine=engine)
  resources[which].failures=1
  errors=shutdown_resources(worker=None,camera=None,**resources,pause=lambda _:None,report=lambda _:None)
  self.assertTrue(display.closed,'display must drain despite an independent close error')
  self.assertTrue(engine.closed,'engine must drain despite an independent close error')
  self.assertTrue(controller.stopped)
  self.assertTrue(errors)
 def test_capture_error_does_not_skip_dma_cleanup(self):self.run_case('capture')
 def test_controller_error_does_not_skip_dma_cleanup(self):self.run_case('controller')
 def test_display_error_does_not_skip_engine_cleanup(self):self.run_case('display')
 def test_engine_error_is_retried_without_freeing_early(self):self.run_case('engine')
if __name__=='__main__':unittest.main()

"""One camera owner, one replaceable frame slot, bounded consumer waits."""
from dataclasses import dataclass
from threading import Condition,Event,Thread,current_thread
from time import monotonic
import math
import numpy as np

@dataclass(frozen=True)
class FrameSample:
    frame:np.ndarray
    timestamp:float
    sequence:int
    dropped:int
    read_ms:float
    def __iter__(self):return iter((self.frame,self.timestamp))

class LatestFrames:
    """The worker owns release(); close never releases during a blocking read."""
    def __init__(self,camera,*,clock=monotonic,wait_s=5.,autostart=True):
        if not math.isfinite(wait_s) or wait_s<=0:raise ValueError('Invalid capture timeout')
        self.camera=camera;self.clock=clock;self.wait_s=wait_s
        self._condition=Condition();self._stop=Event();self._slot=None
        self._sequence=0;self._consumed=0;self._error=None;self._finished=False
        self._start_requested=False;self._released=False
        self._thread=Thread(target=self._read,name='latest-camera',daemon=True)
        if autostart:self.start()
    def start(self):
        if self._stop.is_set():raise RuntimeError('Capture already closed')
        if self._start_requested:raise RuntimeError('Capture already started')
        self._start_requested=True;self._thread.start()
    def _release_once(self):
        with self._condition:
            if self._released:return
            self._released=True
        self.camera.release()
    def _read(self):
        try:
            while not self._stop.is_set():
                started=self.clock();ok,frame=self.camera.read();stamp=self.clock()
                if self._stop.is_set():break
                if not ok or frame is None:raise RuntimeError('Camera read failed')
                if frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:raise ValueError('Camera did not return BGR uint8')
                if not math.isfinite(stamp) or stamp<started:raise ValueError('Invalid capture clock')
                with self._condition:
                    if self._slot is not None and stamp<self._slot[1]:raise ValueError('Capture clock moved backward')
                    self._sequence+=1
                    self._slot=(frame,stamp,self._sequence,(stamp-started)*1000)
                    self._condition.notify_all()
        except Exception as error:
            with self._condition:self._error=error;self._condition.notify_all()
        finally:
            try:self._release_once()
            except Exception as error:
                with self._condition:self._error=error
            with self._condition:self._finished=True;self._condition.notify_all()
    def take(self):
        deadline=monotonic()+self.wait_s
        with self._condition:
            while True:
                if self._error:raise RuntimeError('Capture worker failed') from self._error
                if self._stop.is_set() or self._finished:raise RuntimeError('Capture worker closed')
                if self._slot is not None and self._slot[2]>self._consumed:
                    frame,stamp,sequence,read_ms=self._slot
                    dropped=sequence-self._consumed-1;self._consumed=sequence
                    return FrameSample(frame,stamp,sequence,dropped,read_ms)
                remaining=deadline-monotonic()
                if remaining<=0:raise TimeoutError('No new camera frame within capture timeout')
                self._condition.wait(remaining)
    def frames(self,count=0):
        index=0
        while count==0 or index<count:
            yield self.take();index+=1
    def close(self,timeout=1.):
        self._stop.set()
        with self._condition:self._condition.notify_all()
        if current_thread() is not self._thread and self._thread.is_alive():self._thread.join(timeout)
        if self._thread.is_alive():raise TimeoutError('Camera worker is blocked; device release is not confirmed')
        self._release_once()

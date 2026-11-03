"""Continuous pointing -> stable 12-way commands, explicit stop and optional time bounds."""
from dataclasses import dataclass,asdict
from collections import deque
from threading import Event,RLock,Thread,current_thread
from time import monotonic
import math

STOP=12

def angle_to_direction(angle):
    angle=float(angle)
    if not math.isfinite(angle):raise ValueError('Non-finite pointing angle')
    return int(((angle%360)+15)//30)%12

@dataclass(frozen=True)
class Decision:
    direction:int
    reason:str
    angle:float|None=None
    probability:float|None=None
    def as_dict(self):return asdict(self)

class DirectionController:
    def __init__(self,sink,*,stable_frames=3,hysteresis_degrees=3.,timeout_s=2.,max_age_s=2.,clock=monotonic,watchdog=False,evidence_window_s=None,detector_max_age_s=None):
        if type(stable_frames)is not int or stable_frames<1:raise ValueError('stable_frames must be positive')
        if not math.isfinite(hysteresis_degrees):raise ValueError('Non-finite control settings')
        if not 0<=hysteresis_degrees<15:raise ValueError('Invalid control settings')
        for value in (timeout_s,max_age_s,evidence_window_s,detector_max_age_s):
            if value is not None and (not math.isfinite(value) or value<=0):raise ValueError('Invalid evidence lifetime')
        self.evidence_window=evidence_window_s;self.detector_max_age=detector_max_age_s
        self._evidence=deque(maxlen=stable_frames);self._last_observed=None
        self.sink=sink;self.stable_frames=stable_frames;self.hysteresis=hysteresis_degrees
        self.timeout=timeout_s;self.max_age=max_age_s;self.clock=clock
        self._lock=RLock();self._event=Event();self._thread=None;self._closed=False;self._error=None
        self._sent=None;self._candidate=None;self._count=0;self._deadline=None
        self.last_decision=Decision(STOP,'startup')
        self.stop('startup',force=True)
        if watchdog and (self.timeout is not None or self.max_age is not None):
            self._thread=Thread(target=self._watch,name='pointing-watchdog',daemon=True);self._thread.start()
    def _send(self,direction,force=False):
        if force or direction!=self._sent:self.sink.write(direction);self._sent=direction
    def stop(self,reason='stopped',force=False):
        with self._lock:
            self._candidate=None;self._count=0;self._deadline=None
            self._evidence.clear()
            self._send(STOP,force)
            self.last_decision=Decision(STOP,reason);return self.last_decision
    def update(self,result):
        with self._lock:
            if self._closed:raise RuntimeError('Controller closed')
            if self._error:raise RuntimeError('Control watchdog failed') from self._error
            if self.evidence_window is not None:
                try:
                    observed=float(result['frame_timestamp'])
                    if not math.isfinite(observed):return self.stop('non_finite_result')
                    if observed>self.clock()+.01:return self.stop('invalid_frame_timestamp')
                    if self._last_observed is not None and observed<=self._last_observed:return self.stop('non_increasing_timestamp')
                    self._last_observed=observed
                except (KeyError,TypeError,ValueError):return self.stop('invalid_result')
            if result.get('status')!='ok':return self.stop(str(result.get('status','invalid')))
            try:
                probability=float(result['valid_probability']);angle=float(result['angle_degrees']);timestamp=float(result['frame_timestamp'])
                now=self.clock()
                if not all(math.isfinite(v) for v in (probability,angle,timestamp,now)):return self.stop('non_finite_result')
                if not .5<=probability<=1:return self.stop('invalid_pose')
                if timestamp>now+.01 or (self.max_age is not None and now-timestamp>self.max_age):return self.stop('stale_frame')
                if self.detector_max_age is not None:
                    detected=float(result['detector_timestamp'])
                    if not math.isfinite(detected) or detected>timestamp+.01 or now-detected>self.detector_max_age:return self.stop('stale_detector')
                direction=angle_to_direction(angle)
            except (KeyError,ValueError,TypeError):return self.stop('invalid_result')
            if self._sent is not None and self._sent<12:
                delta=abs((angle-self._sent*30+180)%360-180)
                if delta<=15+self.hysteresis:direction=self._sent
            if self.evidence_window is None:
                if direction==self._candidate:self._count+=1
                else:self._candidate=direction;self._count=1
            else:
                if now-timestamp>self.evidence_window:return self.stop('stale_evidence')
                if direction!=self._candidate:self._evidence.clear();self._candidate=direction
                while self._evidence and now-self._evidence[0]>self.evidence_window:self._evidence.popleft()
                self._evidence.append(timestamp);self._count=len(self._evidence)
            if self._count<self.stable_frames:
                self.check_timeout()
                self.last_decision=Decision(self._sent,'stabilizing',angle,probability);return self.last_decision
            self._send(direction)
            deadlines=[]
            if self.timeout is not None:deadlines.append(now+self.timeout)
            if self.max_age is not None:deadlines.append(timestamp+self.max_age)
            self._deadline=min(deadlines) if deadlines else None
            self.last_decision=Decision(direction,'tracking',angle,probability);return self.last_decision
    def check_timeout(self):
        with self._lock:
            if self._deadline is not None and self.clock()>=self._deadline:
                if self.evidence_window is None:return self.stop('timeout')
                # Output expiry stops motion. Only a new, distinct, fresh frame can resume it.
                self._send(STOP);self._deadline=None;self.last_decision=Decision(STOP,'timeout')
                return self.last_decision
            return self.last_decision
    def _watch(self):
        limits=[v for v in (self.timeout,self.max_age) if v is not None]
        interval=min(.05,min(limits)/4) if limits else .05
        while not self._event.wait(interval):
            try:self.check_timeout()
            except Exception as error:
                with self._lock:self._error=error
                self._event.set()
    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True;self._event.set()
        if self._thread and self._thread is not current_thread():self._thread.join(.5)
        self.stop('closed',force=True)

class MemorySink:
    def __init__(self):self.commands=[]
    def write(self,direction):
        if type(direction)is not int or not 0<=direction<=12:raise ValueError('Invalid direction code')
        self.commands.append(direction)

class GpioSink:
    def __init__(self,gpio):
        self.gpio=gpio;self._lock=RLock()
        with self._lock:self.gpio.write(4,0);self.gpio.write(0,STOP)
    def write(self,direction):
        if type(direction)is not int or not 0<=direction<=12:raise ValueError('Invalid direction code')
        with self._lock:self.gpio.write(0,direction)

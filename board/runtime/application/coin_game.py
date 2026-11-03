"""Camera-controlled 60-second coin game; all pictures and frames live in DDR."""
from pathlib import Path
import argparse,hashlib,json,math,signal,threading,time
import numpy as np

def create_direction_controller(sink,*,stable_frames=1,clock=None):
    """Apply one valid result immediately; retain it until an explicit stop or new decision."""
    from control import DirectionController
    return DirectionController(sink,stable_frames=stable_frames,timeout_s=None,max_age_s=None,
                               clock=time.monotonic if clock is None else clock,watchdog=False)

class DirectionState:
    def __init__(self):
        self._lock=threading.Lock();self._direction=12
    def write(self,direction):
        if type(direction) is not int or not 0<=direction<=12:raise ValueError('invalid direction')
        with self._lock:self._direction=direction
    def read(self):
        with self._lock:return self._direction

class RoundControl:
    """Serialize a round boundary with publication of in-flight inference results."""
    def __init__(self,controller,now):
        self.controller=controller;self.lock=threading.Lock();self.restart(now)
    def restart(self,now):
        now=float(now)
        if not math.isfinite(now):raise ValueError('non-finite round clock')
        with self.lock:
            self.after=now;self.active=True
            self.controller.stop('round_ready',force=True)
    def finish(self):
        with self.lock:
            self.active=False;self.controller.stop('time_up',force=True)
    def is_active(self):
        with self.lock:return self.active
    def update(self,result):
        with self.lock:
            if not self.active:return self.controller.last_decision
            try:old=float(result['frame_timestamp'])<self.after
            except (KeyError,TypeError,ValueError):return self.controller.stop('invalid_result')
            if old:return self.controller.last_decision
            return self.controller.update(result)

class InferenceWorker:
    def __init__(self,engine,pipeline,capture,controller,rotate,log_dir):
        self.engine=engine;self.pipeline=pipeline;self.capture=capture;self.controller=controller
        self.control=RoundControl(controller,time.monotonic())
        self.rotate=rotate;self.log_dir=log_dir;self.stop=threading.Event();self.lock=threading.Lock()
        self.preview=None;self.reason='starting';self.error=None;self.rows=0
        self.thread=threading.Thread(target=self.run,name='gesture-inference',daemon=False)
    def snapshot(self):
        with self.lock:return self.preview,self.reason,self.error,self.rows
    def run(self):
        import cv2
        try:
            with (self.log_dir/'inference.jsonl').open('w') as log:
                for sample in self.capture.frames():
                    if self.stop.is_set():break
                    if not self.control.is_active():
                        self.stop.wait(.05);continue
                    if sample.frame.shape!=(480,640,3):raise ValueError('camera must supply 640x480 BGR')
                    frame=cv2.rotate(sample.frame,cv2.ROTATE_180) if self.rotate else sample.frame
                    begin=time.monotonic()
                    result=self.pipeline.run_frame(frame,timestamp=sample.timestamp)
                    if self.stop.is_set():break
                    control=dict(result)
                    if control['angle_degrees'] is not None:control['angle_degrees']=(-control['angle_degrees'])%360
                    decision=self.control.update(control)
                    tensor=np.asarray(self.engine.last_input['cnn'])
                    if tensor.shape!=(9216,) or not np.isfinite(tensor).all() or tensor.min()<0 or tensor.max()>1:
                        raise ValueError('invalid actual CNN input')
                    preview=np.rint(tensor.reshape(96,96)*255).astype(np.uint8)
                    end=time.monotonic()
                    row=dict(frame=sample.sequence,dropped=sample.dropped,pipeline_ms=(end-begin)*1000,
                             capture_age_ms=(end-sample.timestamp)*1000,direction=decision.direction,
                             reason=decision.reason,status=result['status'])
                    log.write(json.dumps(row)+'\n');log.flush()
                    with self.lock:self.preview=preview;self.reason=decision.reason;self.rows+=1
                    del self.engine.history[:-8];del self.engine.session_history[:-8]
        except BaseException as error:
            if not self.stop.is_set():
                with self.lock:self.error=repr(error)
        finally:self.controller.stop('inference_stopped',force=True)

def verify_package(root):
    manifest=json.loads((root/'runtime_manifest.json').read_text())
    if manifest.get('hardware_revision')!='ddr_coin_game_btn0':raise RuntimeError('wrong game package')
    for name,expected in manifest['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('unsafe package path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('package hash mismatch: '+name)
    return manifest

def create_engine(root):
    from board_contract import configure_mac
    from engine_runtime import BoardEngine
    schedule=json.loads((root/'conv_configuration.json').read_text())['candidate']
    if (schedule['outputs'],schedule['pixels'])!=(8,8):raise ValueError('requires frozen 64-MAC schedule')
    configure_mac(8,8)
    return BoardEngine(root,'overlay')

def shutdown_resources(*,worker,controller,capture,camera,display,engine,pause=time.sleep,report=print):
    """Close independent resources even after errors; retain DMA buffers until idle."""
    errors=[]
    def attempt(name,action):
        try:action();return True
        except Exception as error:
            message=name+': '+repr(error)
            if message not in errors:
                errors.append(message);report(message)
            return False
    if worker is not None:worker.stop.set()
    if controller is not None:attempt('controller stop',lambda:controller.stop('shutdown',force=True))
    if capture is not None:attempt('camera capture',lambda:capture.close(timeout=2.))
    elif camera is not None:attempt('camera release',camera.release)
    if worker is not None and worker.thread.ident is not None:
        while worker.thread.is_alive():
            if not attempt('inference thread',lambda:worker.thread.join(.5)):pause(.5)
    if controller is not None:attempt('controller close',controller.close)
    pending=[]
    if display is not None and not attempt('DDR display',lambda:display.close(timeout=1.)):
        pending.append(('DDR display',lambda:display.close(timeout=1.)))
    if engine is not None and not attempt('inference engine',engine.close):
        pending.append(('inference engine',engine.close))
    # A failed MMIO/idle check never grants permission to free the owned buffers.
    while pending:
        pause(.5)
        pending=[(name,action) for name,action in pending if not attempt(name,action)]
    return errors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--rotate',type=int,choices=(0,180),default=180)
    parser.add_argument('--stable-frames',type=int,default=1,help='valid direction confirmations (default: 1, immediate)')
    parser.add_argument('--duration',type=float,default=60.)
    parser.add_argument('--fps',type=float,default=60.)
    parser.add_argument('--log-dir',type=Path)
    parser.add_argument('--exit-after-result',type=float,default=0.,help='0 keeps the score on screen until Ctrl+C')
    args=parser.parse_args()
    if args.stable_frames<1 or not 1<=args.fps<=60 or not math.isfinite(args.duration) or args.duration<=0 or args.exit_after_result<0:
        parser.error('invalid game timing/control options')
    root=args.root.resolve();verify_package(root)
    from board_pipeline import Pipeline
    from capture import LatestFrames
    from game_state import GameRounds
    from game_renderer import GameRenderer
    from ddr_display import DDRDisplay
    import cv2
    log_dir=args.log_dir or Path.home()/'coin_game_logs'/time.strftime('%Y%m%d_%H%M%S')
    log_dir.mkdir(parents=True,exist_ok=False)
    quit_event=threading.Event()
    def request_exit(signum,frame):quit_event.set()
    signal.signal(signal.SIGINT,request_exit);signal.signal(signal.SIGTERM,request_exit)
    engine=display=camera=capture=controller=worker=None
    summary=None
    try:
        engine=create_engine(root)
        expected={'engine':0x43c00000,'perf':0x43c10000,'ddr_hdmi_0':0x40020000}
        for name,address in expected.items():
            record=engine.overlay.ip_dict.get(name)
            if record is None or record['phys_addr']!=address:raise RuntimeError('incompatible overlay: '+name)
        engine.diagnostic_dir=log_dir
        display=DDRDisplay(engine.overlay)
        renderer=GameRenderer(root/'assets/images.npz')
        sink=DirectionState()
        controller=create_direction_controller(sink,stable_frames=args.stable_frames)
        camera=cv2.VideoCapture(args.camera,cv2.CAP_V4L2)
        if not camera.isOpened():raise RuntimeError('USB camera cannot be opened')
        camera.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        camera.set(cv2.CAP_PROP_FPS,15);camera.set(cv2.CAP_PROP_BUFFERSIZE,1)
        capture=LatestFrames(camera)
        worker=InferenceWorker(engine,Pipeline(root,session_factory=engine.factory),
                               capture,controller,args.rotate,log_dir)
        worker.thread.start()
        rounds=GameRounds(time.monotonic(),duration=args.duration,button_count=display.restart_count())
        worker.control.restart(rounds.created)
        next_tick=rounds.created;rendered=0;finished_at=None;start_stats=None
        inference_baseline=worker.snapshot()[3]
        def record(event):
            with (log_dir/'rounds.jsonl').open('a') as log:log.write(json.dumps(event)+'\n')
            print(json.dumps(event),flush=True)
        record(dict(event='ready',round=rounds.round_id,logs=str(log_dir),duration=args.duration))
        while not quit_event.is_set():
            now=time.monotonic()
            preview,reason,error,inference_frames=worker.snapshot()
            if error:raise RuntimeError('gesture worker failed: '+error)
            if rounds.observe_button(display.restart_count(),now):
                worker.control.restart(now)
                rendered=0;finished_at=None;start_stats=None;summary=None
                inference_baseline=worker.snapshot()[3];next_tick=now
                record(dict(event='restart',round=rounds.round_id,button='BTN0',duration=args.duration))
            if rounds.game.phase=='finished' and finished_at is not None:
                if args.exit_after_result and now-finished_at>=args.exit_after_result:break
                quit_event.wait(.02);continue
            controller.check_timeout()
            event=rounds.tick(now,sink.read());game=rounds.game
            if event=='start':
                start_stats=display.stats()
                record(dict(event='start',round=rounds.round_id,monotonic=now))
            elif event=='coin':
                record(dict(event='coin',round=rounds.round_id,score=game.score,x=game.coin[0],y=game.coin[1]))
            elif event=='result':worker.control.finish()
            ready=max(1,math.ceil(rounds.ready_until-now)) if game.phase=='ready' else None
            index=0 if display.front is None else 1-display.front
            bands=renderer.draw(display.buffers[index],game,now,ready=ready,preview=preview,reason=reason)
            display.present(index,bands=bands);rendered+=1
            if event=='result':
                finished_at=time.monotonic();end_stats=display.stats()
                summary=dict(event='result',round=rounds.round_id,score=game.score,game_seconds=args.duration,
                             elapsed_seconds=finished_at-game.started,rendered_frames=rendered,
                             rendering_fps=rendered/max(.001,finished_at-rounds.created),
                             inference_frames=inference_frames-inference_baseline,scanout=end_stats,
                             game_underflow_lines=end_stats['underflow_lines']-start_stats['underflow_lines'],
                             game_read_errors=end_stats['read_errors']-start_stats['read_errors'])
                text=json.dumps(summary,indent=2)+'\n'
                (log_dir/'result.json').write_text(text)
                (log_dir/('round_%03d.json'%rounds.round_id)).write_text(text)
                record(summary)
            next_tick+=1./args.fps
            delay=next_tick-time.monotonic()
            if delay>0:quit_event.wait(delay)
            else:next_tick=time.monotonic()
    finally:
        shutdown_resources(worker=worker,controller=controller,capture=capture,camera=camera,
                           display=display,engine=engine)
    return summary

if __name__=='__main__':main()

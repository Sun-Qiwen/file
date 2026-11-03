"""Model sessions, DDR buffers and execution for the integrated gesture accelerator."""
from pathlib import Path
from types import SimpleNamespace
import ctypes as C,hashlib,json,os,time
import numpy as np
from board_contract import SENTINEL,COUNTERS,counter_checks,mac_issues

def digest(array):return hashlib.sha256(np.asarray(array).tobytes()).hexdigest()

class Engine:
    def configure(self,root):
        self.root=Path(root);self.meta=json.loads((self.root/'program.json').read_text())
        self.yx=json.loads((self.root/'yolox.json').read_text());self.commands=json.loads((self.root/'commands.json').read_text())
        self.exp=json.loads((self.root/'experiment.json').read_text());self.history=[];self.session_history=[]
        self.last_input={};self.last_output={};self.active=False
    def factory(self,model):
        if model not in ('yolox','cnn'):raise ValueError('unknown hardware model: '+str(model))
        return Session(self,model)
    def validate_range(self,first,last):
        if not 0<=first<=last<=self.command_limit:raise ValueError('invalid command range')

class NativeEngine(Engine):
    def __init__(self,root,dll):
        self.configure(root);self.command_limit=214
        self.arena=np.full(self.exp['total_bytes']//8,SENTINEL,np.uint64)
        self.weights=np.fromfile(self.root/'weights.bin',np.uint64);self.params=np.fromfile(self.root/'params.bin',np.uint32)
        self.stats=np.zeros(16,np.uint32);self.phase=np.zeros(1,np.uint32);self.event=np.zeros(1,np.uint32)
        with os.add_dll_directory('D:/AMD_2025_2/2025.2/win64/tools/vcxx/libexec'):self.lib=C.CDLL(str(Path(dll).resolve()))
        self.top=self.lib.yolox_int8;self.top.argtypes=[C.c_void_p]*3+[C.c_int]*2+[C.c_void_p]*3
    def invoke(self,first,last):
        self.validate_range(first,last);self.stats[:]=0;t0=time.perf_counter_ns()
        self.top(self.arena.ctypes.data,self.weights.ctypes.data,self.params.ctypes.data,first,last,self.stats.ctypes.data,self.phase.ctypes.data,self.event.ctypes.data)
        elapsed=time.perf_counter_ns()-t0;rows=self.commands[first:last]
        assert self.stats[15]==0 and self.stats[0]==len(rows) and self.stats[1]==sum(s['kind']==0 for s in rows)
        assert self.stats[2]==sum(mac_issues(s) for s in rows)
        row=dict(first=first,last=last,board_measured=False,native_cpu_ns=elapsed,stats=self.stats.tolist())
        self.history.append(row);return row
    def close(self):pass

class BoardEngine(Engine):
    def __init__(self,root,variant):
        from pynq import Overlay,allocate,Clocks,MMIO
        self.configure(root);self.buffers=[];self.overlay=None;self.mmio=None
        self.command_limit=214;self.variant=variant
        try:
            self.overlay=Overlay(str(self.root/variant/'gesture_coin_game.bit'));Clocks.fclk0_mhz=100.
            self.clock=float(Clocks.fclk0_mhz)
            assert abs(self.clock-100.)<.01 and self.overlay.is_loaded()
            self.mmio=self.overlay.engine.mmio
            self.perf=MMIO(self.overlay.ip_dict['perf']['phys_addr'],self.overlay.ip_dict['perf']['addr_range'])
            def make(array):
                buf=allocate(shape=array.shape,dtype=array.dtype);self.buffers.append(buf);buf[:]=array;buf.flush();return buf
            self.arena=make(np.full(self.exp['total_bytes']//8,SENTINEL,np.uint64))
            self.weights=make(np.fromfile(self.root/'weights.bin',np.uint64));self.params=make(np.fromfile(self.root/'params.bin',np.uint32))
            self.stats=make(np.zeros(16,np.uint32));self.offsets=json.loads((self.root/'offsets.json').read_text());self.physical={}
            for name in ('arena','weights','params','stats'):
                address=int(getattr(self,name).physical_address);self.physical[name]=address
                self.mmio.write(self.offsets[name],address&0xffffffff);self.mmio.write(self.offsets[name]+4,address>>32)
            self.identity=dict(variant=variant,clock_mhz=self.clock,bitfile=str(self.overlay.bitfile_name),
                               bit_sha256=hashlib.sha256((self.root/variant/'gesture_coin_game.bit').read_bytes()).hexdigest(),
                               hwh_sha256=hashlib.sha256((self.root/variant/'gesture_coin_game.hwh').read_bytes()).hexdigest(),physical=self.physical,
                               boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        except BaseException:self.close();raise
    def invoke(self,first,last):
        self.validate_range(first,last);t0=time.perf_counter_ns();control=self.mmio.read(0)
        if control&1 or control&0x80 or not control&4:raise RuntimeError('engine not idle, or auto-restart enabled')
        self.stats[:]=0;self.stats.flush();self.mmio.write(self.offsets['first'],first);self.mmio.write(self.offsets['last'],last)
        assert self.mmio.read(self.offsets['first'])==first and self.mmio.read(self.offsets['last'])==last
        assert self.mmio.read(0)&2==0,'old done latch was not cleared'
        t1=time.perf_counter_ns();self.arena.flush();t2=time.perf_counter_ns()
        self.active=True;self.mmio.write(0,1);t3=time.perf_counter_ns();seen_done=False;late=False
        while True:
            control=self.mmio.read(0);seen_done|=bool(control&2)
            if seen_done and control&4 and not control&1:break
            if time.perf_counter_ns()-t2>240_000_000_000:
                if not late:self.record_hung(first,last,t2,control)
                late=True;time.sleep(.1)
        self.active=False;t4=time.perf_counter_ns();self.arena.invalidate();self.stats.invalidate();t5=time.perf_counter_ns()
        counters={name:int(self.perf.read(i*4)) for i,name in enumerate(COUNTERS)}
        checks=counter_checks(self.commands[first:last],self.stats,counters,t4-t2)
        t6=time.perf_counter_ns()
        row=dict(first=first,last=last,board_measured=True,clock_mhz=self.clock,ps_start_to_done_ns=t4-t2,
                 setup_ns=t1-t0,flush_ns=t2-t1,start_write_ns=t3-t2,poll_ns=t4-t3,invalidate_ns=t5-t4,
                 counter_read_and_check_ns=t6-t5,engine_host_ns=t6-t0,
                 hardware_ms=counters['total']/100000. if checks['cycle_counter_bounded'] else None,
                 counters=counters,stats=self.stats.tolist(),late=late,**checks)
        self.history.append(row)
        assert checks['passed'] and not late,('hardware status/counter gate',row)
        return row
    def record_hung(self,first,last,start_ns,control):
        info=dict(first=first,last=last,start_ns=start_ns,now_ns=time.perf_counter_ns(),control=control,
                  physical=self.physical,variant=self.variant,cma_retained=True,active=self.active,
                  counters={name:int(self.perf.read(i*4)) for i,name in enumerate(COUNTERS)},
                  action='Holding allocations until hardware idle; do not kill collector while DMA may be active')
        directory=Path(self.diagnostic_dir);directory.mkdir(parents=True,exist_ok=True)
        with (directory/'hung_invocation.json').open('x') as f:
            json.dump(info,f,indent=2);f.flush();os.fsync(f.fileno())
        print('HUNG_INVOCATION_CMA_RETAINED',first,last,flush=True)
    def close(self):
        # Never release a CMA allocation while the FPGA may still be using it.
        while self.active:
            control=self.mmio.read(0)
            if control&4 and not control&1:self.active=False;break
            time.sleep(.1)
        for buf in reversed(self.buffers):buf.freebuffer()
        self.buffers=[]

class Session:
    def __init__(self,engine,model):self.engine=engine;self.model=model
    @property
    def supports_quantized_input(self):return self.model=='yolox'
    def get_inputs(self):return [SimpleNamespace(name='image',shape=[1,1,96,96] if self.model=='cnn' else [1,3,480,640])]
    def get_outputs(self):
        desc=[('heatmap_logits',[1,2,48,48]),('valid_logits',[1,1])] if self.model=='cnn' else [('8',[1,6,60,80]),('16',[1,6,30,40]),('32',[1,6,15,20])]
        return [SimpleNamespace(name=n,shape=s) for n,s in desc]
    def run(self,names,feed):
        e=self.engine;x=np.asarray(next(iter(feed.values())));shape=tuple(self.get_inputs()[0].shape)
        if x.shape!=shape or x.dtype!=np.float32 or not np.isfinite(x).all():raise ValueError('invalid continuous-tone model input')
        start=time.perf_counter_ns()
        if self.model=='yolox':
            ratio=x.ravel()/np.float32(2.640000104904175/127.)
            # Signed addition followed by truncation keeps half-away rounding,
            # including float32 half neighbours, without sign/abs/floor copies.
            np.add(ratio,np.copysign(np.float32(.5),ratio),out=ratio)
            np.trunc(ratio,out=ratio)
            np.clip(ratio,-127,127,out=ratio)
            prepared=ratio.astype(np.int8)
            e.arena.view(np.int8)[:prepared.size]=prepared;first,last=0,169
        else:
            prepared=x.ravel();off=e.meta['cnn_input'];e.arena.view(np.uint8)[off:off+prepared.nbytes]=prepared.view(np.uint8);first,last=169,214
        copied=time.perf_counter_ns();e.last_input[self.model]=prepared
        e.invoke(first,last);kernel_done=time.perf_counter_ns()
        if self.model=='yolox':
            outputs=[]
            for h in e.yx['heads']:
                count=int(np.prod(h['shape']));raw=e.arena.view(np.int8)[h['offset']:h['offset']+count].reshape(h['shape'])
                outputs.append((raw.astype(np.float32)*np.asarray(h['scales'],np.float32)[:,None,None])[None])
            e.last_output[self.model]=outputs
        else:
            off=e.meta['cnn_output'];raw=e.arena.view(np.uint8)[off:off+4609*4].view(np.float32).copy()
            mapping={'heatmap_logits':raw[:4608].reshape(1,2,48,48),'valid_logits':raw[4608:].reshape(1,1)}
            outputs=[mapping[k] for k in names] if names else list(mapping.values());e.last_output[self.model]=raw
        end=time.perf_counter_ns()
        e.session_history.append(dict(model=self.model,input_sha256=None,format_and_copy_ns=copied-start,
                                      engine_call_ns=kernel_done-copied,read_and_dequant_ns=end-kernel_done,session_ns=end-start,
                                      first=first,last=last,board_measured=e.history[-1]['board_measured']))
        return outputs

    def run_quantized(self,names,feed,*,preprocess_ns=0):
        input_start=time.perf_counter_ns()
        e=self.engine;x=np.asarray(next(iter(feed.values())))
        if (self.model!='yolox' or x.shape!=(1,3,480,640) or x.dtype!=np.int8
                or not x.flags.c_contiguous or x.min()<-127
                or type(preprocess_ns) is not int or preprocess_ns<0):
            raise ValueError('invalid fused YOLOX int8 input or preprocessing duration')
        start=time.perf_counter_ns()
        # Keep a separate diagnostic input copy before writing shared DDR.
        # invoke() owns cache synchronization and waits for hardware completion.
        prepared=x.ravel().copy()
        e.arena.view(np.int8)[:prepared.size]=prepared;first,last=0,169
        copied=time.perf_counter_ns();e.last_input[self.model]=prepared
        e.invoke(first,last);kernel_done=time.perf_counter_ns()
        outputs=[]
        for h in e.yx['heads']:
            count=int(np.prod(h['shape']));raw=e.arena.view(np.int8)[h['offset']:h['offset']+count].reshape(h['shape'])
            outputs.append((raw.astype(np.float32)*np.asarray(h['scales'],np.float32)[:,None,None])[None])
        e.last_output[self.model]=outputs
        end=time.perf_counter_ns()
        e.session_history.append(dict(model=self.model,input_sha256=None,format_and_copy_ns=copied-start,
                                      engine_call_ns=kernel_done-copied,read_and_dequant_ns=end-kernel_done,session_ns=end-start,
                                      first=first,last=last,board_measured=e.history[-1]['board_measured'],
                                      input_path='int8_lut',fused_prepare_ns=preprocess_ns,
                                      quantized_validation_ns=start-input_start,
                                      input_prepare_and_copy_ns=preprocess_ns+copied-input_start))
        return outputs

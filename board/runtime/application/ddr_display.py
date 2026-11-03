"""PYNQ DDR framebuffer ownership and bounded AXI-Lite presentation."""
import time
import numpy as np

class DDRDisplay:
    def __init__(self,overlay=None,*,mmio=None,buffers=None):
        self.front=None;self.pending=None;self.closed=False;self.buffers=[]
        if mmio is None:
            from pynq import MMIO
            entry=overlay.ip_dict['ddr_hdmi_0']
            if entry['phys_addr']!=0x40020000: raise ValueError('unexpected DDR display address')
            mmio=MMIO(entry['phys_addr'],entry['addr_range'])
        self.mmio=mmio
        if mmio.read(0)!=0x44445231: raise RuntimeError('overlay lacks DDR1 scanout')
        mmio.write(0x14,2)
        self._wait_stopped(.5)
        mmio.write(0x14,4)
        owns=buffers is None
        try:
            if owns:
                from pynq import allocate
                for _ in range(2): self.buffers.append(allocate(shape=(720,1280),dtype=np.uint16,cacheable=True))
            else:self.buffers=list(buffers)
            if len(self.buffers)!=2: raise ValueError('two framebuffers required')
            ranges=[]
            for frame in self.buffers:
                address=int(frame.physical_address)
                if frame.shape!=(720,1280) or frame.dtype!=np.uint16: raise ValueError('invalid frame shape/type')
                if address<=0 or address%4096 or address+frame.nbytes>2**32:
                    raise ValueError('DDR framebuffer address must be 4096-aligned and fit 32 bits')
                ranges.append((address,address+frame.nbytes))
            if max(ranges[0][0],ranges[1][0])<min(ranges[0][1],ranges[1][1]):
                raise ValueError('framebuffers overlap')
        except BaseException:
            if owns:
                for frame in self.buffers:frame.freebuffer()
            raise

    def _wait_stopped(self,timeout):
        end=time.monotonic()+timeout
        while self.mmio.read(4)&15:
            if time.monotonic()>=end: raise TimeoutError('DDR DMA not idle; buffers remain pinned')
            time.sleep(.0005)

    def present(self,index,*,bands=None,timeout=.5):
        if self.closed: raise RuntimeError('display closed')
        if index not in (0,1) or index==self.front or self.pending is not None:
            raise ValueError('framebuffer is displayed or pending')
        frame=self.buffers[index]
        if bands is None:frame.flush()
        else:
            for top,bottom in bands:
                if not 0<=top<bottom<=720:raise ValueError('invalid dirty rows')
                frame[top:bottom].flush()
        before=self.mmio.read(0x0c)
        self.pending=index
        self.mmio.write(0x10,int(frame.physical_address))
        self.mmio.write(0x14,1)
        end=time.monotonic()+timeout
        while self.mmio.read(0x0c)==before:
            if self.mmio.read(0x20):raise RuntimeError('DDR read response error')
            if time.monotonic()>=end:raise TimeoutError('DDR vblank commit timed out; do not reuse buffer')
            time.sleep(.0005)
        self.front=index;self.pending=None

    def restart_count(self):
        return int(self.mmio.read(0x28))&65535

    def stats(self):
        return dict(underflow_lines=int(self.mmio.read(0x1c)),
                    read_errors=int(self.mmio.read(0x20)),
                    video_frames=int(self.mmio.read(0x24)),
                    presented_frames=int(self.mmio.read(0x0c)))

    def close(self,timeout=.5):
        if self.closed:return
        self.mmio.write(0x14,2)
        self._wait_stopped(timeout)
        for frame in self.buffers:frame.freebuffer()
        self.buffers=[];self.closed=True

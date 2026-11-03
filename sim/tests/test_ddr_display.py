import sys,unittest,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[2]/'board/runtime/application'))
from ddr_display import DDRDisplay

class Buffer(np.ndarray):
 def __new__(cls,address):
  obj=np.zeros((720,1280),np.uint16).view(cls);obj.physical_address=address
  obj.owner=obj;obj.freed=False;return obj
 def __array_finalize__(self,obj):
  if obj is not None:self.owner=getattr(obj,'owner',obj);self.physical_address=getattr(obj,'physical_address',0)
 def flush(self): pass
 def freebuffer(self): self.freed=True

class Hardware:
 def __init__(self):
  self.reg={0:0x44445231,4:0,12:0,24:0,28:0,32:0,36:0};self.cfg=0;self.pending=False;self.allow_present=True;self.allow_stop=True
 def read(self,addr):
  if addr==12 and self.pending and self.allow_present:
   self.reg[24]=self.cfg;self.reg[12]+=1;self.pending=False;self.reg[4]=5
  return self.reg.get(addr,0)
 def write(self,addr,value):
  if addr==16:self.cfg=value
  elif addr==20 and value==1:self.pending=True;self.reg[4]=3
  elif addr==20 and value==2:
   if self.allow_stop:self.pending=False;self.reg[4]=0
   else:self.reg[4]=8

class DisplayTests(unittest.TestCase):
 def display(self):
  hw=Hardware();buffers=[Buffer(0x1000),Buffer(0x400000)]
  return DDRDisplay(mmio=hw,buffers=buffers),hw,buffers
 def test_front_buffer_cannot_be_reused_until_flip(self):
  d,h,b=self.display();d.present(0)
  self.assertEqual(h.read(24),0x1000)
  with self.assertRaises(ValueError):d.present(0)
  d.present(1);self.assertEqual(h.read(24),0x400000)
  d.present(0);d.close();self.assertTrue(all(x.freed for x in b))
 def test_timeout_keeps_buffers_pinned_until_dma_drains(self):
  d,h,b=self.display();h.allow_present=False
  with self.assertRaises(TimeoutError):d.present(0,timeout=.002)
  h.allow_stop=False
  with self.assertRaises(TimeoutError):d.close(timeout=.002)
  self.assertFalse(any(x.freed for x in b))
  h.allow_stop=True;d.close();self.assertTrue(all(x.freed for x in b))
 def test_rejects_unaligned_or_out_of_range_addresses(self):
  for addr in (0x1001,0x100000000):
   with self.assertRaises(ValueError):DDRDisplay(mmio=Hardware(),buffers=[Buffer(addr),Buffer(0x400000)])
if __name__=='__main__':unittest.main()

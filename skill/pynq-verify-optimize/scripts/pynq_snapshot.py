"""Observe existing local PYNQ state; never load an Overlay or start DMA."""
from pathlib import Path
import argparse,hashlib,json,math,platform,sys

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def snapshot(pynq_module=None,clock_ids=(0,),boot_file='/proc/sys/kernel/random/boot_id'):
    errors=[];record=dict(schema_version=1,host=platform.node(),platform=platform.platform(),
        scope='Read-only metadata and clocks; no load/reset/frequency write/DMA, no functional or performance validation',
        overlay_pair_verified=False,dma_idle_verified=False)
    try:record['boot_id']=Path(boot_file).read_text().strip()
    except OSError as e:record['boot_id']=None;errors.append('boot: '+str(e))
    try:
        if pynq_module is None:import pynq as pynq_module
        record['pynq_version']=getattr(pynq_module,'__version__',None)
        value=pynq_module.PL.bitfile_name;record['loaded_bitfile']=str(value) if value else None
        record['artifacts']={}
        if value:
            bit=Path(value)
            for kind,path in [('bit',bit),('hwh',bit.with_suffix('.hwh'))]:
                try:record['artifacts'][kind]=dict(path=str(path),sha256=sha(path))
                except OSError as e:record['artifacts'][kind]=dict(path=str(path),sha256=None);errors.append(kind+': '+str(e))
        record['clocks_mhz']={}
        for index in clock_ids:
            name='fclk'+str(index)+'_mhz'
            try:
                value=float(getattr(pynq_module.Clocks,name))
                if not math.isfinite(value):raise ValueError('Nonfinite clock reading')
                record['clocks_mhz'][name]=value
            except Exception as e:record['clocks_mhz'][name]=None;errors.append(name+': '+str(e))
    except Exception as e:errors.append('pynq: '+str(e))
    record['errors']=errors;record['status']='partial_observation' if errors else 'snapshot_created'
    return record

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',required=True);ap.add_argument('--clock-id',type=int,action='append',choices=range(4))
    a=ap.parse_args();result=snapshot(clock_ids=tuple(a.clock_id or [0]));text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    with Path(a.out).open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    print(text,end='');return 2 if result['errors'] else 0

if __name__=='__main__':sys.exit(main())

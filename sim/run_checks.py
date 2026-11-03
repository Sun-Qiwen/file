"""Run delivered manual coin-game tests; all generated files go outside this package."""
from pathlib import Path
import argparse,os,subprocess,sys,time,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',required=True,type=Path)
 p.add_argument('--iverilog',default='iverilog')
 p.add_argument('--vvp',default='vvp')
 p.add_argument('--skip-rtl',action='store_true')
 a=p.parse_args();out=a.output.resolve()
 if out.is_relative_to(ROOT):p.error('--output must be outside the delivery directory')
 out.mkdir(parents=True,exist_ok=False);tmp=out/'tmp';tmp.mkdir()
 env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',COIN_TEST_TEMP=str(tmp),TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp))
 results=[];python_count=0
 def run(name,cmd):
  start=time.monotonic();r=subprocess.run(cmd,cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  (out/(name+'.log')).write_text(r.stdout,encoding='utf-8')
  results.append(dict(name=name,exit_code=r.returncode,seconds=time.monotonic()-start))
  if r.returncode:raise RuntimeError(name+' failed; see '+str(out/(name+'.log')))
  print(name+': PASS',flush=True);return r.stdout
 text=run('python',[sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'sim/tests'),'-v'])
 match=re.search(r'Ran (\d+) tests',text)
 if match is None:raise RuntimeError('unittest test count missing')
 python_count=int(match.group(1))
 scenarios=[('button',['-P','tb_ddr_hdmi.BUTTON_TEST=1']),('fullwidth',['-P','tb_ddr_hdmi.WIDTH=1280']),('early_last',['-P','tb_ddr_hdmi.BAD_KIND=1']),('missing_last',['-P','tb_ddr_hdmi.BAD_KIND=2']),('wrong_id',['-P','tb_ddr_hdmi.BAD_KIND=3']),('slave_error',['-P','tb_ddr_hdmi.BAD_KIND=4']),('late_last',['-P','tb_ddr_hdmi.BAD_KIND=5'])]
 if not a.skip_rtl:
  for name,args in scenarios:
   executable=out/(name+'.vvp')
   run(name+'_compile',[a.iverilog,'-g2012','-s','tb_ddr_hdmi',*args,'-o',str(executable),str(ROOT/'sim/rtl/tb_ddr_hdmi.sv'),str(ROOT/'src/rtl/ddr_hdmi.v')])
   run(name,[a.vvp,str(executable)])
 sources=[*(ROOT/'sim/tests').glob('*.py'),ROOT/'sim/rtl/tb_ddr_hdmi.sv',ROOT/'src/rtl/ddr_hdmi.v',*(ROOT/'board/runtime/application').glob('*.py')]
 receipt=dict(passed=True,python_tests=python_count,rtl_scenarios=0 if a.skip_rtl else len(scenarios),results=results,source_sha256={v.relative_to(ROOT).as_posix():hashlib.sha256(v.read_bytes()).hexdigest() for v in sources})
 (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=True,python_tests=python_count,rtl_scenarios=receipt['rtl_scenarios'],output=str(out))))
if __name__=='__main__':main()

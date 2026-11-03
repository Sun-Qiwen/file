"""Read-only, fail-closed checks for the tested 7-series Vivado report layout."""
from pathlib import Path
import argparse,hashlib,json,math,re,sys

FILES=('utilization.rpt','timing.rpt','check_timing.rpt','route_status.rpt','drc.rpt','routed.dcp')
TIMING_CHECKS={'no_clock','constant_clock','pulse_width_clock','unconstrained_internal_endpoints',
 'no_input_delay','no_output_delay','multiple_clock','generated_clocks','loops',
 'partial_input_delay','partial_output_delay','latch_loops'}
SCOPE='Saved static reports/checkpoint only; not source equivalence, receipt authenticity, functional correctness or board acceptance.'

def require(condition,message):
    if not condition:raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def row(text,label):
    matches=[]
    for line in text.splitlines():
        cells=[p.strip() for p in line.split('|')[1:-1]]
        if cells and cells[0].rstrip('*')==label:
            require(len(cells)>=5,'Unknown utilization columns: '+label)
            used=float(cells[1].replace(',',''));capacity=float(cells[4].replace(',',''))
            require(math.isfinite(used) and 0<=used<=capacity and capacity>0,'Invalid resource: '+label)
            matches.append((used,capacity))
    require(matches and len(set(matches))==1,'Missing/ambiguous resource row: '+label)
    return matches[0]

def match(pattern,text,label,flags=0):
    m=re.search(pattern,text,flags);require(m is not None,'Missing '+label);return m

def inspect(directory,expected_clocks,seal=None):
    d=Path(directory).resolve();texts={n:(d/n).read_text(encoding='utf-8',errors='strict') for n in FILES if n.endswith('.rpt')}
    u=texts['utilization.rpt'];t=texts['timing.rpt']
    part=match(r'^\|\s*Device\s*:\s*(\S+)',u,'device',re.M)[1]
    require(part.lower().startswith('xc7'),'This report parser is validated for 7-series only; adapt other architectures explicitly')
    version=match(r'Vivado\s+v\.?(\d+\.\d+)',u,'Vivado version')[1]
    require(re.search(r'^\|\s*Design State\s*:\s*Routed\s*$',u,re.M),'Utilization is not a Routed report')
    resources={};capacities={}
    for key,label in [('slice','Slice'),('lut','Slice LUTs'),('ff','Slice Registers'),('controls','Unique Control Sets'),('dsp','DSPs'),('bram36_equivalent','Block RAM Tile')]:
        # Control-set table has no physical capacity; parse its used value only.
        if key=='controls':
            resources[key]=float(match(r'^\|\s*Unique Control Sets\s*\|\s*([\d.]+)',u,'control sets',re.M)[1]);continue
        resources[key],capacities[key]=row(u,label)
    require(resources['slice']>0 and resources['slice'].is_integer(),'Invalid occupied Slice count')
    values=list(map(float,match(r'^\s*WNS\(ns\).*\n[^\n]+\n([^\n]+)',t,'timing summary',re.M)[1].split()))
    require(len(values)==12 and all(math.isfinite(v) for v in values),'Unknown/nonfinite timing summary')
    require(all(values[i]>=0 for i in (0,4,8)),'Negative setup/hold/pulse slack')
    require(all(values[i]==0 for i in (1,2,5,6,9,10)),'Timing violations or failing endpoints')
    clocks={name:float(freq) for name,wave,period,freq in re.findall(r'^(\S+)\s+(\{[^}]+\})\s+([\d.]+)\s+([\d.]+)\s*$',t,re.M)}
    require(expected_clocks and set(clocks)==set(expected_clocks),'Clock set differs from the explicit project contract')
    require(all(abs(clocks[n]-freq)<.01 for n,freq in expected_clocks.items()),'Clock frequency changed')
    checks={name:int(count) for name,count in re.findall(r'^\d+\. checking (\w+) \((\d+)\)',texts['check_timing.rpt'],re.M)}
    require(set(checks)==TIMING_CHECKS and not any(checks.values()),'Missing/unknown/nonzero check_timing category')
    route=texts['route_status.rpt']
    def netcount(label):return int(match(re.escape(label)+r'\.+\s*:\s*(\d+)',route,label)[1])
    routable=netcount('# of routable nets');fully=netcount('# of fully routed nets');errors=netcount('# of nets with routing errors')
    require(fully==routable and fully>0 and errors==0,'Incomplete or erroneous routing')
    drc=texts['drc.rpt']
    require('REPORT SUMMARY' in drc and 'Fully Routed' in drc,'Missing routed DRC summary')
    severities=re.findall(r'^\|\s*\S+\s*\|\s*(Error|Critical Warning|Warning|Advisory)\s*\|[^\n]*\|\s*(\d+)\s*\|',drc,re.M)
    require(severities,'Unknown DRC table')
    require(not any(s in ('Error','Critical Warning') and int(n)>0 for s,n in severities),'DRC error/critical warning')
    hashes={n:sha(d/n) for n in FILES};seal_matches=False
    if seal is not None:
        record=json.loads(Path(seal).read_text());outputs=record.get('output_sha256',{})
        require(record.get('exit_code')==0 and set(FILES).issubset(outputs),'Seal lacks successful execution/all required outputs')
        require(isinstance(record.get('started'),(int,float)) and isinstance(record.get('ended'),(int,float)) and record['ended']>=record['started'],'Seal lacks run timestamps')
        for name,digest in outputs.items():
            require(Path(name).name==name,'Seal path escapes run directory')
            require(sha(d/name)==digest,'Sealed output changed: '+name)
        command=record.get('command',[])
        require('-source' in command and command.index('-source')+1<len(command),'Seal lacks executed Tcl path')
        script=Path(command[command.index('-source')+1]);script=script if script.is_absolute() else Path(seal).resolve().parent/script
        require(record.get('script_sha256')==sha(script),'Executed Tcl identity changed')
        seal_matches=True
    return dict(schema_version=1,static_checks_passed=True,scope=SCOPE,directory=str(d),part=part,tool_version=version,
        resources=resources,capacities=capacities,free_slices=capacities['slice']-resources['slice'],clocks_mhz=clocks,
        timing=dict(wns_ns=values[0],whs_ns=values[4],wpws_ns=values[8]),fully_routed_nets=fully,route_errors=errors,
        check_timing=checks,files=hashes,supplied_run_seal_matches=seal_matches,
        provenance_status='supplied_run_record_consistent_not_authenticated' if seal_matches else 'report_snapshot_unbound_to_execution')

def compare(candidate,baseline):
    require(baseline.get('static_checks_passed') is True,'Baseline checks not passed')
    require(candidate['part']==baseline['part'] and candidate['capacities']==baseline['capacities'],'Different device/capacity')
    require(candidate['clocks_mhz']==baseline['clocks_mhz'],'Different clock contracts')
    require(set(FILES).issubset(baseline.get('files',{})),'Baseline lacks raw artifact identities')
    for name,digest in baseline['files'].items():
        require(Path(name).name==name,'Baseline path escapes directory')
        require(sha(Path(baseline['directory'])/name)==digest,'Baseline artifacts changed; regenerate summary in relocated directories')
    parent=baseline['resources']['slice'];require(parent>0,'Empty baseline')
    saved=parent-candidate['resources']['slice']
    return dict(saved_slices=saved,reduction_of_parent_used_percent=saved/parent*100,
        actual_reported_reduction=saved>0,both_supplied_run_seals_match=bool(candidate['supplied_run_seal_matches'] and baseline.get('supplied_run_seal_matches')),
        resource_delta={k:v-baseline['resources'][k] for k,v in candidate['resources'].items()},
        scope='Area comparison only. Check project resource limits, source/function and board evidence separately.')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory');ap.add_argument('--clock',action='append',required=True,help='Repeat NAME=MHz for every expected clock')
    ap.add_argument('--seal');ap.add_argument('--baseline');ap.add_argument('--out');a=ap.parse_args()
    try:
        expected={}
        for item in a.clock:
            name,value=item.rsplit('=',1);frequency=float(value)
            require(name and name not in expected and math.isfinite(frequency) and frequency>0,'Invalid/duplicate clock contract')
            expected[name]=frequency
        result=inspect(a.directory,expected,a.seal)
        if a.baseline:result['comparison']=compare(result,json.loads(Path(a.baseline).read_text()))
        code=0
    except (ValueError,OSError,KeyError,IndexError,TypeError) as e:
        result=dict(static_checks_passed=False,error=str(e),scope=SCOPE);code=2
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.out:
        with Path(a.out).open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    print(text,end='');return code

if __name__=='__main__':sys.exit(main())

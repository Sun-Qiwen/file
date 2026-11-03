"""Shared PC/board acceptance rules. Numeric limits match the frozen PL contract."""
import re
import numpy as np

SENTINEL=np.uint64(0xA55AA55A5AA55AA5)
COUNTERS=['total','input_load_and_unpack','compute','requant','store','mac_active',
          'axi_read_wait','axi_write_wait','axi_read_bytes','axi_read_requests',
          'axi_write_bytes','axi_write_requests','weight_load','control_other',
          'input_compute_overlap','elementwise','spatial','reserved',
          'input_quant','groupnorm','pool','upconcat','valid_head','heat_dequant']

def board_preflight_gate(state,required_bytes):
    assert not state['active_workloads'],('board workload active; do not reprogram',state['active_workloads'])
    match=re.search(r'^CmaFree:\s+(\d+)\s+kB$',state['meminfo'],re.M)
    assert match,'CmaFree unavailable'
    available=int(match[1])*1024
    assert available>=required_bytes,('insufficient free CMA',available,required_bytes)
    return dict(passed=True,cma_free_bytes=available,cma_required_bytes=required_bytes)

def output_size(s):
    if s['kind']==0:
        oh=(s['h']+2*s['pad']-s['k'])//s['stride']+1
        ow=(s['w']+2*s['pad']-s['k'])//s['stride']+1
        return s['co']*oh*ow
    if s['kind']==11:return 4
    return s['n']*(4 if s['kind']>=8 else 1)

def write_layout(commands,arena_bytes):
    """0=unchanged guard, 1=exact integer byte, 2=finite FP32 word; last writer wins."""
    layout=np.zeros(arena_bytes,np.uint8)
    for s in commands:
        off=s['out'];n=output_size(s)
        assert 0<=off<=off+n<=arena_bytes,(off,n,arena_bytes)
        if s['kind']>=8:assert off%4==0 and n%4==0
        layout[off:off+n]=2 if s['kind']>=8 else 1
    floating=layout.reshape(-1,4)==2
    assert not np.any(np.any(floating,axis=1)&~np.all(floating,axis=1)),'partial float word'
    return layout

def verify_float(actual,expected,atol=2e-5,rtol=2e-5):
    actual=np.asarray(actual);expected=np.asarray(expected)
    assert actual.shape==expected.shape
    assert np.isfinite(actual).all() and np.isfinite(expected).all(),'nonfinite float'
    delta=np.abs(actual.astype(np.float64)-expected.astype(np.float64))
    bad=delta>atol+rtol*np.abs(expected.astype(np.float64))
    assert not bad.any(),('float mismatch',int(bad.sum()),float(delta.max()))
    return float(delta.max()) if delta.size else 0.

def verify_pipeline_result(actual,expected):
    for key in ('status','hands','crop_bounds','cnn_ran'):
        assert actual[key]==expected[key],('pipeline metadata',key,actual[key],expected[key])
    points=verify_float(np.asarray(actual['points']),np.asarray(expected['points']))
    probability=verify_float(np.array([actual['valid_probability']]),np.array([expected['valid_probability']]))
    if expected['angle_degrees'] is None:assert actual['angle_degrees'] is None
    else:
        assert actual['angle_degrees'] is not None
        verify_float(np.array([actual['angle_degrees']]),np.array([expected['angle_degrees']]))
    return dict(passed=True,points_max_abs=points,probability_abs=probability)

def verify_arena(actual,before,golden,layout):
    av=np.asarray(actual).view(np.uint8).ravel();bv=np.asarray(before).view(np.uint8).ravel();gv=np.asarray(golden).view(np.uint8).ravel()
    assert av.shape==bv.shape==gv.shape==layout.shape
    guard=layout==0;integer=layout==1
    ng=int(np.count_nonzero(av[guard]!=bv[guard]));ni=int(np.count_nonzero(av[integer]!=gv[integer]))
    assert ng==0,('guard bytes changed',ng)
    assert ni==0,('integer bytes mismatched',ni)
    floating=np.all(layout.reshape(-1,4)==2,axis=1)
    error=verify_float(av.view(np.float32)[floating],gv.view(np.float32)[floating])
    return dict(passed=True,guard_mismatches=ng,integer_mismatches=ni,float_max_abs=error,
                guard_bytes=int(guard.sum()),integer_bytes=int(integer.sum()),float_words=int(floating.sum()))

MAC_OUTPUT_LANES=8
MAC_PIXELS=4

def configure_mac(outputs,pixels):
    global MAC_OUTPUT_LANES,MAC_PIXELS
    if (outputs,pixels) not in ((8,4),(8,8),(16,4)):
        raise ValueError('unsupported shared convolution schedule')
    MAC_OUTPUT_LANES=outputs;MAC_PIXELS=pixels

def mac_issues(s):
    if s['kind']!=0:return 0
    oh=(s['h']+2*s['pad']-s['k'])//s['stride']+1
    ow=(s['w']+2*s['pad']-s['k'])//s['stride']+1
    return ((s['co']+MAC_OUTPUT_LANES-1)//MAC_OUTPUT_LANES)*oh*((ow+15)//16)*s['k']**2*(1 if s['depthwise'] else s['c'])*(16//MAC_PIXELS)

def traffic_bound(s):
    """Conservative 64b HP-beat bounds from source loops, not a bandwidth estimate."""
    kind=s['kind'];n=s.get('n',0)
    if kind==0:
        ci,co,h,w,k,st,pad,dw=[s[f] for f in ('c','co','h','w','k','stride','pad','depthwise')]
        oh=(h+2*pad-k)//st+1;ow=(w+2*pad-k)//st+1;stripe=64
        # Use 16-pixel blocks for a conservative read bound on the eight-bank
        # cache, charging the maximum number of reload blocks.
        blocks=oh*((ow+15)//16);terms=k*k if dw else ci*k*k
        rd=blocks*(ci*k*((stripe*st+k+14)//8)+co*((terms+14)//8)+2*co)*8+co*oh*ow*8
        wr=co*oh*ow*8
    elif kind==7:rd=n*8;wr=n
    elif kind==8:rd=n*24+s['c']*16;wr=n*4
    elif kind==9:rd=n*32;wr=n*4
    elif kind==10:rd=s['c']*s['h']*s['w']*8+s['co']*s['h']*s['w']*16;wr=n*4
    elif kind==11:rd=96*144*8+97*8+8;wr=8
    elif kind==12:rd=n*8;wr=n*4
    else:rd=n*(max(1,s.get('k',1)**2)+3)*32;wr=n*8
    return int(rd*2+4096),int(wr*2+4096)

def counter_checks(commands,stats,counters,elapsed_ns):
    stats=np.asarray(stats);expected=sum(mac_issues(s) for s in commands)
    status=bool(stats[15]==0 and stats[0]==len(commands) and stats[1]==sum(s['kind']==0 for s in commands)
                and stats[2]==expected and counters['mac_active']==expected)
    cycles=(elapsed_ns+1_000_000)/10<2**32
    rd=sum(traffic_bound(s)[0] for s in commands)+64;wr=sum(traffic_bound(s)[1] for s in commands)+64
    traffic=rd<2**32 and wr<2**32 and counters['axi_read_bytes']<=rd and counters['axi_write_bytes']<=wr
    parts=('input_load_and_unpack','compute','requant','store','weight_load','control_other',
           'elementwise','spatial','input_quant','groupnorm','pool','upconcat','valid_head','heat_dequant')
    partition=abs(sum(counters.get(k,0) for k in parts)-counters['input_compute_overlap']-counters['total'])<=16 and counters['total']>0
    return dict(passed=bool(status and cycles and traffic and partition),status_ok=status,
                cycle_counter_bounded=bool(cycles),byte_counter_bounded=bool(traffic),stage_partition_ok=bool(partition),
                expected_mac_events=expected,read_byte_upper=rd,write_byte_upper=wr)

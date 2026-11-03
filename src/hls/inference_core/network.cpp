#include <stdint.h>
#include <limits.h>
#include "program.h"
#include "arena_io.h"
#include "conv_engine.h"
#include "focus_packed.h"
#include "cnn_ops.h"
#include "concat_identity.h"
#include "resize_packed.h"
#include "maxpool_packed.h"
#ifndef __SYNTHESIS__
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static int32_t rescale(int8_t x,uint32_t m) {
#pragma HLS INLINE
 int64_t p=(int64_t)x*m;
 int64_t q=p>=0?(p+(1LL<<29))>>30:-(((-p)+(1LL<<29))>>30);
 if(q>INT32_MAX)q=INT32_MAX;if(q<INT32_MIN)q=INT32_MIN;
 return (int32_t)q;
}
static int8_t clamp8(int64_t x) {
#pragma HLS INLINE
 return x>127?127:(x< -127?-127:(int8_t)x);
}
#include "concat_requant.h"
#include "add_packed.h"
static void elementwise(uint64_t *arena,const uint32_t *params,const Command &cmd) {
#pragma HLS INLINE off
 if(add_packed_eligible(cmd)) {
  add_packed_words(arena,cmd.a,cmd.b,cmd.out,cmd.n>>3,cmd.ma,cmd.mb);
  return;
 }
 if(concat_requant_eligible(cmd)) {
  concat_requant_words(arena,cmd.a,cmd.out,cmd.n>>3,cmd.ma);
  return;
 }
 uint32_t start=0;
 const uint64_t input_end=(uint64_t)cmd.a+cmd.n;
 const uint64_t output_end=(uint64_t)cmd.out+cmd.n;
 if(cmd.kind==3 && cmd.ma==(1u<<30) && cmd.n>=8
    && ((cmd.a|cmd.out)&7)==0
    && input_end<=0x100000000ULL && output_end<=0x100000000ULL
    && (input_end<=cmd.out || output_end<=cmd.a)) {
  concat_identity_words(arena,cmd.a,cmd.out,cmd.n>>3);
  start=cmd.n&~7u;
 }
 for(uint32_t i=start;i<cmd.n;i+=8) {
  uint64_t word=0;
  for(int lane=0;lane<8;++lane) {
#pragma HLS PIPELINE II=1
   uint32_t at=i+lane;
   if(at<cmd.n) {
    int8_t x=read_byte(arena,cmd.a,at),y;
    if(cmd.kind==2)y=clamp8((int64_t)rescale(x,cmd.ma)+rescale(read_byte(arena,cmd.b,at),cmd.mb));
    else if(cmd.kind==6)y=(int8_t)params[cmd.lut+(int)x+127];
    else y=clamp8(rescale(x,cmd.ma));
    word|=(uint64_t)(uint8_t)y<<(lane*8);
   }
  }
  int bytes=cmd.n-i<8?(int)(cmd.n-i):8;
  write_fragment(arena,cmd.out+i,word,bytes);
 }
}
static void spatial(uint64_t *arena,const Command &cmd) {
#pragma HLS INLINE off
 // Packed 2x nearest-neighbour Resize only for the two frozen ROM shapes.
 const bool resize_small=cmd.c==128 && cmd.h==15 && cmd.w==20 && cmd.n==153600;
 const bool resize_large=cmd.c==64 && cmd.h==30 && cmd.w==40 && cmd.n==307200;
 const uint64_t resize_input_end=(uint64_t)cmd.a+(resize_small?38400ULL:76800ULL);
 const uint64_t resize_output_end=(uint64_t)cmd.out+cmd.n;
 if(cmd.kind==5 && (resize_small || resize_large) && ((cmd.a|cmd.out)&7)==0
    && resize_input_end<=0x100000000ULL && resize_output_end<=0x100000000ULL
    && (resize_input_end<=cmd.out || resize_output_end<=cmd.a)) {
  resize_packed(arena,cmd.a,cmd.out,resize_small);
  return;
 }
 // Keep all unsupported shapes, partial lengths, byte alignment and aliasing
 // on the original path, including its sequential in-place behavior.
 const uint64_t focus_input_end=(uint64_t)cmd.a+921600;
 const uint64_t focus_output_end=(uint64_t)cmd.out+921600;
 if(cmd.kind==1 && cmd.c==3 && cmd.h==480 && cmd.w==640 && cmd.n==921600
    && ((cmd.a|cmd.out)&7)==0
    && focus_input_end<=0x100000000ULL && focus_output_end<=0x100000000ULL
    && (focus_input_end<=cmd.out || focus_output_end<=cmd.a)) {
  focus_packed(arena,cmd.a,cmd.out);
  return;
 }
 if(maxpool_packed_eligible(cmd)) {maxpool_packed(arena,cmd.a,cmd.out,cmd.k,cmd.pad);return;}
 // Only the measured MaxPool_131/132/133 command shapes reuse this one
 // channel buffer. Keep aliasing commands on the original sequential path.
 const bool channel_cached = cmd.kind==4 && cmd.c==128 && cmd.h==15 && cmd.w==20
   && ((cmd.k==5 && cmd.pad==2) || (cmd.k==9 && cmd.pad==4) || (cmd.k==13 && cmd.pad==6))
   && cmd.stride==0 && cmd.n==38400
   && ((uint64_t)cmd.a+cmd.n<=cmd.out || (uint64_t)cmd.out+cmd.n<=cmd.a);
 int8_t channel_cache[300];
#pragma HLS BIND_STORAGE variable=channel_cache type=ram_1p impl=bram
 uint32_t cached_channel=UINT32_MAX;
 uint32_t oh=cmd.kind==1?cmd.h/2:(cmd.kind==5?cmd.h*2:cmd.h);
 uint32_t ow=cmd.kind==1?cmd.w/2:(cmd.kind==5?cmd.w*2:cmd.w);
 for(uint32_t i=0;i<cmd.n;i+=8) {
  uint64_t word=0;
  for(int lane=0;lane<8;++lane) {
   uint32_t at=i+lane;
   if(at<cmd.n) {
    uint32_t c=at/(oh*ow),q=at%(oh*ow),y=q/ow,x=q%ow;
    if(channel_cached && c!=cached_channel) {
     // No rounding of the 300-byte channel, including half-word boundaries.
     // Preserve the original scalar DDR read helper and serial loop schedule.
     for(uint32_t j=0;j<300;++j)
      channel_cache[j]=read_byte(arena,cmd.a,c*cmd.h*cmd.w+j);
     cached_channel=c;
    }
    int value=-128;
    if(cmd.kind==1) {
     uint32_t block=c/cmd.c,ic=c%cmd.c;
     value=read_byte(arena,cmd.a,(ic*cmd.h+y*2+(block&1))*cmd.w+x*2+(block>>1));
    } else if(cmd.kind==5) value=read_byte(arena,cmd.a,(c*cmd.h+y/2)*cmd.w+x/2);
    else {
     for(uint32_t ky=0;ky<cmd.k;++ky)for(uint32_t kx=0;kx<cmd.k;++kx) {
      int iy=(int)y+(int)ky-(int)cmd.pad,ix=(int)x+(int)kx-(int)cmd.pad;
      if(iy>=0 && iy<(int)cmd.h && ix>=0 && ix<(int)cmd.w) {
       int v=channel_cached ? channel_cache[iy*cmd.w+ix]
                            : read_byte(arena,cmd.a,(c*cmd.h+iy)*cmd.w+ix);
       if(v>value)value=v;
      }
     }
    }
    word|=(uint64_t)(uint8_t)value<<(lane*8);
   }
  }
  int bytes=cmd.n-i<8?(int)(cmd.n-i):8;
  write_fragment(arena,cmd.out+i,word,bytes);
 }
}
extern "C" EXPORT void yolox_int8(uint64_t *arena,const uint64_t *weights,const uint32_t *params,
 int first,int last,uint32_t *stats,volatile uint32_t *phase,volatile uint32_t *mac_event) {
#pragma HLS INTERFACE m_axi port=arena offset=slave bundle=features depth=708872 max_read_burst_length=32 max_write_burst_length=32 num_read_outstanding=2 num_write_outstanding=1
#pragma HLS INTERFACE m_axi port=weights offset=slave bundle=weights depth=157138 max_read_burst_length=32
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=params depth=32768 max_read_burst_length=32
#pragma HLS INTERFACE m_axi port=stats offset=slave bundle=stats depth=16
#pragma HLS INTERFACE s_axilite port=arena bundle=control
#pragma HLS INTERFACE s_axilite port=weights bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=first bundle=control
#pragma HLS INTERFACE s_axilite port=last bundle=control
#pragma HLS INTERFACE s_axilite port=stats bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS INTERFACE ap_none port=phase
#pragma HLS INTERFACE ap_vld port=mac_event
#pragma HLS ALLOCATION function instances=conv_engine limit=1
 uint32_t counts[16]={0};uint32_t done=0,convs=0,issues=0;
 if(first<0 || last<first || last>COMMAND_COUNT){stats[15]=1;*phase=7;return;}
 for(int i=first;i<last;++i) {
  Command cmd=PROGRAM[i];*phase=6;
  if(cmd.kind==0) {
   conv_engine(arena,weights,params,cmd.a,cmd.out,cmd.weights,cmd.bias,cmd.mult,
    cmd.c,cmd.co,cmd.h,cmd.w,cmd.k,cmd.stride,cmd.pad,cmd.depthwise,cmd.relu,counts,phase,mac_event);
   if(counts[15]){stats[15]=counts[15];*phase=7;return;}
   ++convs;issues+=counts[2];
  } else if(cmd.kind>=7) {cnn_ops(arena,params,cmd,counts,phase);if(counts[15]){stats[15]=counts[15];*phase=7;return;}}
  else if(cmd.kind==2 || cmd.kind==3 || cmd.kind==6)elementwise(arena,params,cmd);
  else spatial(arena,cmd);
  ++done;
 }
 stats[0]=done;stats[1]=convs;stats[2]=issues;stats[15]=0;*phase=7;
}

#pragma once
#include <stdint.h>
// A command-local, per-channel separable maximum. No cross-command state.
static bool maxpool_packed_eligible(const Command &s) {
#pragma HLS INLINE
 const uint64_t ae=(uint64_t)s.a+38400,oe=(uint64_t)s.out+38400;
 return s.kind==4 && s.c==128 && s.h==15 && s.w==20 && s.n==38400 && s.stride==0
  && ((s.k==5&&s.pad==2)||(s.k==9&&s.pad==4)||(s.k==13&&s.pad==6))
  && ((s.a|s.out)&7)==0 && ae<=0x100000000ULL && oe<=0x100000000ULL
  && (ae<=s.out || oe<=s.a);
}
static void maxpool_packed(uint64_t *arena,uint32_t src,uint32_t dst,uint8_t k_arg,uint8_t pad_arg) {
#pragma HLS INLINE off
 uint64_t raw[38];
 int8_t horizontal[300];
#pragma HLS BIND_STORAGE variable=raw type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=horizontal type=ram_1p impl=bram
 uint64_t packed=0;
 uint8_t lane=0;
 uint32_t output_word=dst>>3;
 // The eligible caller permits only k=5/9/13 and pad=2/4/6.
 const uint8_t k=k_arg&15u,pad=pad_arg&7u;
 for(uint8_t ch=0;ch<128;++ch) {
  const uint8_t shift=(ch&1)*4;
  const uint32_t first=(src>>3)+(ch*300)/8;
  maxpool_load:for(uint8_t j=0;j<38;++j) {
#pragma HLS PIPELINE II=1
   raw[j]=arena[first+j];
  }
  for(uint8_t y=0;y<15;++y)for(uint8_t x=0;x<20;++x) {
   int8_t best=-128;
   maxpool_horizontal_k:for(uint8_t t=0;t<k;++t) {
#pragma HLS PIPELINE II=1
    const int8_t ix=(int8_t)x+(int8_t)t-(int8_t)pad;
    int8_t value=-128;
    if(ix>=0 && ix<20) {
     const uint16_t index=(shift+y*20+(uint8_t)ix)&511u;
     value=(int8_t)(raw[index>>3]>>((index&7)*8));
    }
    if(value>best)best=value;
   }
   horizontal[y*20+x]=best;
  }
  for(uint8_t y=0;y<15;++y)for(uint8_t x=0;x<20;++x) {
   int8_t best=-128;
   maxpool_vertical_k:for(uint8_t t=0;t<k;++t) {
#pragma HLS PIPELINE II=1
    const int8_t iy=(int8_t)y+(int8_t)t-(int8_t)pad;
    const int8_t value=iy>=0&&iy<15?horizontal[iy*20+x]:(int8_t)-128;
    if(value>best)best=value;
   }
   // Eight fixed shifts fully replace the previous word. Keep the four
   // pending bytes across a 300-byte channel boundary, exactly as before.
   packed=(packed>>8)|((uint64_t)(uint8_t)best<<56);
   if(lane==7)arena[output_word++]=packed;
   lane=(lane+1)&7u;
  }
 }
}

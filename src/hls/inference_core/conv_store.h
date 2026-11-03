#pragma once
#include <stdint.h>

// One stripe or row block is at most128 valid bytes per channel. Keep the word loop
// unconditional and contiguous, with all partial words outside it.
static void store_output_tile(uint64_t *arena,const uint32_t tile[8192],
                             uint32_t dst,int channel_stride,int lanes,int count,int first_lane=0) {
#pragma HLS INLINE off
 for(int lane=0;lane<lanes;++lane) {
#pragma HLS LOOP_FLATTEN off
  const uint32_t pos=dst+lane*channel_stride;
  const uint16_t tile_base=(uint16_t)((((uint32_t)first_lane+(uint32_t)lane)&255u)<<5);
  const int n4=count/4;
  if((pos&3)==0) {
   const int head=(pos&7)==4?1:0;
   if(head)write_four(arena,pos,tile[tile_base]);
   const int full=(n4-head)/2;
   const uint32_t base=(pos+head*4)>>3;
  store_contiguous:
   for(int j=0;j<full;++j) {
#pragma HLS PIPELINE II=1
    const uint64_t lo=tile[tile_base+head+j*2];
    const uint64_t hi=tile[tile_base+head+j*2+1];
    arena[base+j]=lo|(hi<<32);
   }
   if((n4-head)&1)write_four(arena,pos+(n4-1)*4,tile[tile_base+n4-1]);
  } else {
   // Byte-unaligned destinations were not used by the fixed ROM. Preserve
   // every neighboring byte, including fragments that straddle a word.
   for(int j=0;j<n4;++j)write_fragment(arena,pos+j*4,tile[tile_base+j],4);
  }
 }
}

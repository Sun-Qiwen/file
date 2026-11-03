#pragma once
#include <stdint.h>

// Q30 1<<30 is exact for every int8 value. The existing clamp still maps
// -128 to -127, so preserve it even for callers outside the model value range.
static uint64_t concat_identity_word(uint64_t value) {
#pragma HLS INLINE
 uint64_t result=value;
 for(int lane=0;lane<8;++lane) {
#pragma HLS UNROLL
  if((uint8_t)(value>>(lane*8))==0x80)
   result|=(uint64_t)1<<(lane*8);
 }
 return result;
}

// Caller proves eight-byte alignment, disjoint ranges and bounded addresses.
// Only complete words are transferred. The legacy caller handles any tail.
static void concat_identity_words(uint64_t *arena,uint32_t input,
 uint32_t output,uint32_t words) {
#pragma HLS INLINE off
 uint64_t block[64];
#pragma HLS BIND_STORAGE variable=block type=ram_1p impl=bram
 for(uint32_t base=0;base<words;base+=64) {
  uint32_t count=words-base<64?words-base:64;
  concat_load_words: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   block[j]=concat_identity_word(arena[(input>>3)+base+j]);
  }
  concat_store_words: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   arena[(output>>3)+base+j]=block[j];
  }
 }
}

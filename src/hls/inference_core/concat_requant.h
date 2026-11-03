#pragma once
#include <stdint.h>
#include <limits.h>

// Deliberately bounded scale domain includes every rescaled Concat in the ROM.
// No tails or aliases: those retain the original sequential word behaviour.
static bool concat_requant_eligible(const Command &cmd) {
#pragma HLS INLINE
 const uint64_t input_end=(uint64_t)cmd.a+cmd.n;
 const uint64_t output_end=(uint64_t)cmd.out+cmd.n;
 return cmd.kind==3 && cmd.ma>0 && cmd.ma<(1u<<30) && cmd.n>=8
  && ((cmd.a|cmd.out|cmd.n)&7)==0
  && input_end<=0x100000000ULL && output_end<=0x100000000ULL
  && (input_end<=cmd.out || output_end<=cmd.a);
}

static void concat_requant_words(uint64_t *arena,uint32_t input,
 uint32_t output,uint32_t words,uint32_t ma) {
#pragma HLS INLINE off
 int8_t mapping[256];
#pragma HLS BIND_STORAGE variable=mapping type=ram_2p impl=bram
 uint64_t block[64];
#pragma HLS BIND_STORAGE variable=block type=ram_2p impl=bram
 // At iteration i, product == (i-128)*ma exactly. This is an integer
 // recurrence, avoiding a second Q30 multiplier beside the legacy engine.
 // No retained scale/table state; every invocation writes all 256 entries.
 int64_t product=-((int64_t)ma<<7);
 concat_build_table: for(uint32_t i=0;i<256;++i) {
#pragma HLS PIPELINE II=1
  int64_t q=product>=0?(product+(1LL<<29))>>30
                           :-(((-product)+(1LL<<29))>>30);
  if(q>INT32_MAX)q=INT32_MAX;
  if(q<INT32_MIN)q=INT32_MIN;
  mapping[(uint8_t)(i-128)]=clamp8(q);
  product+=(int64_t)ma;
 }
 for(uint32_t base=0;base<words;base+=64) {
  const uint32_t count=words-base<64?words-base:64;
  concat_requant_load: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   block[j]=arena[(input>>3)+base+j];
  }
  uint64_t value=0,mapped=0;
  concat_requant_map: for(uint32_t pair=0;pair<count*4;++pair) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=block inter false
   if((pair&3)==0)value=block[pair>>2];
   uint8_t y0=(uint8_t)mapping[(uint8_t)value];
   uint8_t y1=(uint8_t)mapping[(uint8_t)(value>>8)];
   value>>=16;
   mapped=(mapped>>16)|((uint64_t)y0<<48)|((uint64_t)y1<<56);
   if((pair&3)==3)block[pair>>2]=mapped;
  }
  concat_requant_store: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   arena[(output>>3)+base+j]=block[j];
  }
 }
}

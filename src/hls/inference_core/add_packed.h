#pragma once
#include <stdint.h>

// For 0 < m <= 2^30, independently rounded int8 rescale is in [-128,127].
// Store that pre-add value, including -128 at identity scale, in signed16.
static bool add_packed_eligible(const Command &cmd) {
#pragma HLS INLINE
 const uint64_t ae=(uint64_t)cmd.a+cmd.n,be=(uint64_t)cmd.b+cmd.n;
 const uint64_t oe=(uint64_t)cmd.out+cmd.n;
 return cmd.kind==2 && cmd.ma>0 && cmd.ma<=(1u<<30)
  && cmd.mb>0 && cmd.mb<=(1u<<30) && cmd.n>=8
  && ((cmd.a|cmd.b|cmd.out|cmd.n)&7)==0
  && ae<=0x100000000ULL && be<=0x100000000ULL && oe<=0x100000000ULL
  && (ae<=cmd.out || oe<=cmd.a) && (be<=cmd.out || oe<=cmd.b);
}

static void add_packed_words(uint64_t *arena,uint32_t a,uint32_t b,
 uint32_t output,uint32_t words,uint32_t ma,uint32_t mb) {
#pragma HLS INLINE off
 int16_t map_a[256],map_b[256];
#pragma HLS BIND_STORAGE variable=map_a type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=map_b type=ram_2p impl=bram
 uint64_t block_a[64],block_b[64];
#pragma HLS BIND_STORAGE variable=block_a type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=block_b type=ram_2p impl=bram
 int64_t pa=-((int64_t)ma<<7),pb=-((int64_t)mb<<7);
 add_build_tables: for(uint32_t i=0;i<256;++i) {
#pragma HLS PIPELINE II=1
  int64_t qa=pa>=0?(pa+(1LL<<29))>>30:-(((-pa)+(1LL<<29))>>30);
  int64_t qb=pb>=0?(pb+(1LL<<29))>>30:-(((-pb)+(1LL<<29))>>30);
  // Proven bounded by the eligibility domain; int32 saturation is a no-op.
  map_a[(uint8_t)(i-128)]=(int16_t)qa;
  map_b[(uint8_t)(i-128)]=(int16_t)qb;
  pa+=(int64_t)ma;pb+=(int64_t)mb;
 }
 for(uint32_t base=0;base<words;base+=64) {
  const uint32_t count=words-base<64?words-base:64;
  add_load_a: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   block_a[j]=arena[(a>>3)+base+j];
  }
  add_load_b: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   block_b[j]=arena[(b>>3)+base+j];
  }
  // Two independent read ports per table, no table replication. A bounded
  // word register holds ownership until all four byte-pairs are packed.
  uint64_t av=0,bv=0,mapped=0;
  add_map_words: for(uint32_t pair=0;pair<count*4;++pair) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=block_a inter false
   if((pair&3)==0){av=block_a[pair>>2];bv=block_b[pair>>2];}
   int16_t va0=map_a[(uint8_t)av],vb0=map_b[(uint8_t)bv];
   int16_t va1=map_a[(uint8_t)(av>>8)],vb1=map_b[(uint8_t)(bv>>8)];
   uint8_t y0=(uint8_t)clamp8((int64_t)va0+(int64_t)vb0);
   uint8_t y1=(uint8_t)clamp8((int64_t)va1+(int64_t)vb1);
   av>>=16;bv>>=16;
   mapped=(mapped>>16)|((uint64_t)y0<<48)|((uint64_t)y1<<56);
   if((pair&3)==3)block_a[pair>>2]=mapped;
  }
  add_store: for(uint32_t j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
   arena[(output>>3)+base+j]=block_a[j];
  }
 }
}

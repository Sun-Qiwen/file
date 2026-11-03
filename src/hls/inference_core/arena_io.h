#pragma once
#include <stdint.h>
static int8_t read_byte(const uint64_t *arena,uint32_t base,uint32_t i) {
#pragma HLS INLINE
 uint32_t pos=base+i;
 return (int8_t)(arena[pos>>3]>>((pos&7)*8));
}
static void write_fragment(uint64_t *arena,uint32_t pos,uint64_t value,int bytes) {
#pragma HLS INLINE
 if((pos&7)==0 && bytes==8) arena[pos>>3]=value;
 else for(int j=0;j<bytes;++j) {
  uint32_t at=pos+j;uint64_t mask=(uint64_t)255<<((at&7)*8);
  arena[at>>3]=(arena[at>>3]&~mask)|(((value>>(j*8))&255)<<((at&7)*8));
 }
}
static void write_four(uint64_t *arena,uint32_t pos,uint32_t value) {
#pragma HLS INLINE
 uint32_t shift=(pos&7)*8;
 uint64_t mask=(uint64_t)0xffffffff<<shift;
 arena[pos>>3]=(arena[pos>>3]&~mask)|((uint64_t)value<<shift);
}

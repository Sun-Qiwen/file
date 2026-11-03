#pragma once
#include <stdint.h>

// Four arbitrary bytes become eight bytes; 0x80 is preserved bit for bit.
static uint64_t resize_duplicate_four(uint32_t x) {
#pragma HLS INLINE
 uint64_t b0=x&0xffu,b1=(x>>8)&0xffu,b2=(x>>16)&0xffu,b3=x>>24;
 return b0|(b0<<8)|(b1<<16)|(b1<<24)|(b2<<32)|(b2<<40)|(b3<<48)|(b3<<56);
}

// Both frozen shapes contain 1920 input rows. Width20 rows alternate
// offsets 0/4 within a 64-bit word, including the 300-byte channel plane.
// The caller checks exact shapes, full lengths, aligned nonoverlapping
// tensor ranges and 64-bit address ends. No read extends past that range:
// width20's last row starts at lane4 and its third word ends at input_end.
static void resize_packed(uint64_t *arena,uint32_t input,uint32_t output,bool small) {
#pragma HLS INLINE off
 uint64_t row[5];
#pragma HLS BIND_STORAGE variable=row type=ram_1p impl=bram
 const uint32_t width=small?20:40;
 const uint32_t load_words=small?3:5;
 const uint32_t output_words=small?5:10;
 uint32_t src=input,dst=output>>3;
 for(uint32_t y=0;y<1920;++y) {
  const uint32_t head=(src&7)>>2;
  resize_load_row: for(uint32_t j=0;j<load_words;++j) {
#pragma HLS PIPELINE II=1
   row[j]=arena[(src>>3)+j];
  }
  for(uint32_t dy=0;dy<2;++dy) {
   resize_store_row: for(uint32_t j=0;j<output_words;++j) {
#pragma HLS PIPELINE II=1
    uint32_t half=j+head;
    uint32_t four=(uint32_t)(row[half>>1]>>((half&1)*32));
    arena[dst+j]=resize_duplicate_four(four);
   }
   dst+=output_words;
  }
  src+=width;
 }
}

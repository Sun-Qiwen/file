#pragma once
#include <stdint.h>

// Join the even byte lanes of two adjacent input words. Shifting both
// inputs by 8 gives the odd lanes, preserving all eight-bit patterns.
static uint64_t focus_pack_even(uint64_t a,uint64_t b) {
#pragma HLS INLINE
 return (a&0xffULL)|((a>>8)&0xff00ULL)|((a>>16)&0xff0000ULL)|((a>>24)&0xff000000ULL)
       |((b&0xffULL)<<32)|((b&0xff0000ULL)<<24)|((b&0xff00000000ULL)<<16)|((b&0xff000000000000ULL)<<8);
}

// Fixed PROGRAM Focus: CHW 3x480x640 -> 12x240x320. Caller checks
// aligned, non-overlapping byte ranges and exact length. One 640-byte
// row serves both column parities, without re-reading DDR for q+2.
static void focus_packed(uint64_t *arena,uint32_t input,uint32_t output) {
#pragma HLS INLINE off
 uint64_t row[80];
#pragma HLS BIND_STORAGE variable=row type=ram_t2p impl=bram
 uint32_t src=input>>3;
 for(uint32_t c=0;c<3;++c) {
  uint32_t dst=(output>>3)+c*9600;
  for(uint32_t y=0;y<240;++y) {
   for(uint32_t parity=0;parity<2;++parity) {
    focus_load_row: for(uint32_t j=0;j<80;++j) {
#pragma HLS PIPELINE II=1
     row[j]=arena[src+j];
    }
    uint32_t target=dst+parity*28800;
    focus_write_even: for(uint32_t j=0;j<40;++j) {
#pragma HLS PIPELINE II=1
     arena[target+j]=focus_pack_even(row[2*j],row[2*j+1]);
    }
    focus_write_odd: for(uint32_t j=0;j<40;++j) {
#pragma HLS PIPELINE II=1
     arena[target+57600+j]=focus_pack_even(row[2*j]>>8,row[2*j+1]>>8);
    }
    src+=80;
   }
   dst+=40;
  }
 }
}

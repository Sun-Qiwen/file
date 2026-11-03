#pragma once
#include <stdint.h>
#include <limits.h>
#include "conv_store.h"
// Build-time schedule: one shared engine, 8 outputs x 8 pixels.
// Raw row reuse, coefficient cache, k1 stripe reuse and quantization inherit ja68.
#define CONV_OUTPUT_LANES 8
#define CONV_MAC_PIXELS 8
#define CONV_X_CHANNEL_BANKS 8
#define CONV_PACKED_X_TYPE uint16_t

static int8_t quantize(int32_t sum,int32_t bias,uint32_t multiplier,int relu) {
#pragma HLS INLINE
    int64_t a=(int64_t)sum+bias;
    if(a>INT32_MAX)a=INT32_MAX; if(a<INT32_MIN)a=INT32_MIN;
    if(relu && a<0)a=0;
    int64_t p=a*(int64_t)multiplier;
    // p = floor(p/2^30)*2^30 + remainder, remainder in [0,2^30).
    // Negative half ties keep floor; positive half ties increment it.
    uint64_t bits=(uint64_t)p;
    int64_t floor_q=(int64_t)(bits>>30)-(p<0?((int64_t)1<<34):0);
    if(floor_q>=127)return 127;
    if(floor_q<=-128)return -127;
    uint32_t remainder=(uint32_t)(bits&(((uint64_t)1<<30)-1));
    int rounded=(int)floor_q+(remainder>(1u<<29)||(remainder==(1u<<29)&&p>=0));
    return (int8_t)rounded;
}
static bool conv_coefficients_cache_safe(uint64_t *arena,const uint32_t *params,
 uint32_t output_offset,uint64_t output_end,uint32_t bias_offset,uint32_t mult_offset,int co) {
#pragma HLS INLINE
 // Different AXI ports can still name the same physical DDR. Do not move
 // parameter reads across stores that may change either coefficient range.
 const uint64_t arena_base=(uint64_t)(uintptr_t)arena;
 const uint64_t params_base=(uint64_t)(uintptr_t)params;
 const uint64_t out_first=arena_base+output_offset,out_last=arena_base+output_end;
 // One conservative enclosing interval shares address/check logic. If the
 // output lies only in the gap between bias and multiplier, use the old
 // sequential path too; no parameter value is ever assumed unchanged.
 const uint32_t first_index=bias_offset<mult_offset?bias_offset:mult_offset;
 const uint32_t last_index=bias_offset>mult_offset?bias_offset:mult_offset;
 const uint64_t last_end=(uint64_t)last_index+(uint32_t)co;
 const uint64_t params_first=params_base+(uint64_t)first_index*4;
 const uint64_t params_last=params_base+last_end*4;
 return output_end<=0x100000000ULL
  && last_end<=0x100000000ULL
  && out_first>=arena_base && out_last>=out_first
  && params_first>=params_base && params_last>=params_first
  && (out_last<=params_first || params_last<=out_first);
}
static bool conv_weights_cache_safe(uint64_t *arena,const uint64_t *weight_mem,
 uint32_t output_offset,uint64_t output_end,uint32_t weight_offset,uint64_t weight_words) {
#pragma HLS INLINE
 const uint64_t arena_base=(uint64_t)(uintptr_t)arena;
 const uint64_t weight_base=(uint64_t)(uintptr_t)weight_mem;
 const uint64_t out_first=arena_base+output_offset,out_last=arena_base+output_end;
 const uint64_t weight_first=weight_base+(uint64_t)weight_offset*8;
 const uint64_t weight_last=weight_first+weight_words*8;
 return output_end<=0x100000000ULL
  && out_first>=arena_base && out_last>=out_first
  && weight_first>=weight_base && weight_last>=weight_first
  && (out_last<=weight_first || weight_last<=out_first);
}
static void conv_engine(uint64_t *arena,const uint64_t *weight_mem,const uint32_t *params,
 uint32_t input_offset,uint32_t output_offset,uint32_t weight_offset,uint32_t bias_offset,uint32_t mult_offset,
 int ci,int co,int h,int w,int k,int stride,int pad,int depthwise,int relu,
 uint32_t *stats,volatile uint32_t *phase,volatile uint32_t *mac_event) {
#pragma HLS INLINE off
 *phase=1;
 if(stride!=1 && stride!=2){stats[15]=1;*phase=7;return;}
 int oh=(h+2*pad-k)/stride+1,ow=(w+2*pad-k)/stride+1;
 if(ci<1||ci>512||co<1||co>256||h<1||w<1||(k!=1&&k!=3)||pad<0||pad>1||oh<1||ow<1||(ow&3)||(depthwise&&ci!=co)) {stats[15]=1;*phase=7;return;}
 uint64_t cache[16384];
#pragma HLS BIND_STORAGE variable=cache type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=cache cyclic factor=8 dim=1
 uint64_t wc[CONV_OUTPUT_LANES][577];
#pragma HLS ARRAY_PARTITION variable=wc complete dim=1
#pragma HLS BIND_STORAGE variable=wc type=ram_2p impl=bram
 // Same1152-byte xc payload: pair adjacent channel banks into one TDP BRAM.
 // DW reads both channel halves concurrently; ordinary unpack writes one half.
 // Packed words hold 16/CONV_MAC_PIXELS pixels, read once per MAC group.
 CONV_PACKED_X_TYPE xc[CONV_X_CHANNEL_BANKS*CONV_MAC_PIXELS/2][18];
#pragma HLS ARRAY_PARTITION variable=xc complete dim=1
#pragma HLS BIND_STORAGE variable=xc type=ram_t2p impl=bram
 // Same 16 KiB stripe capacity; p8 uses twice the banks, half the word width.
 CONV_PACKED_X_TYPE stripe_inputs[CONV_MAC_PIXELS][1024];
#pragma HLS ARRAY_PARTITION variable=stripe_inputs complete dim=1
#pragma HLS BIND_STORAGE variable=stripe_inputs type=ram_s2p impl=bram
 int32_t sums[CONV_OUTPUT_LANES][16];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums cyclic factor=CONV_MAC_PIXELS dim=2
#pragma HLS BIND_STORAGE variable=sums type=ram_s2p impl=lutram
 // At most 128 bytes per output channel, shared across a few short rows.
 // Each slot is written by quantization before its row group can be drained.
 uint32_t output_tile[8192];
#pragma HLS BIND_STORAGE variable=output_tile type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=output_tile cyclic factor=2 dim=1
 // One bias/multiplier pair is consumed per quantize iteration.
 uint64_t coefficients[CONV_OUTPUT_LANES];int woffs[CONV_OUTPUT_LANES];
#pragma HLS BIND_STORAGE variable=coefficients type=ram_s2p impl=lutram
#pragma HLS ARRAY_PARTITION variable=woffs complete
 uint64_t layer_coefficients[256];
#pragma HLS BIND_STORAGE variable=layer_coefficients type=ram_s2p impl=bram
 uint32_t words=0,weights=0,issues=0,stores=0;
 const int terms=depthwise?k*k:ci*k*k;
 const int total_in=(ci*h*w+7)/8,total_w=(co*terms+7)/8;
 // Limit stripe size so all input channels and k rows fit in the BRAM tile.
 int stripe=64;
 while(stripe>16 && (int64_t)ci*k*((stripe*stride+k+14)/8)>16384)stripe-=16;
 if((int64_t)ci*k*((stripe*stride+k+14)/8)>16384){stats[15]=2;*phase=7;return;}
 // Full rows fit in the existing raw-word BRAM for every frozen YOLOX/CNN
 // layer. Preserve stripe order and all weight/MAC loops; reuse input rows
 // across stripes and successive y. Unsupported/alias calls retain loading.
 const uint64_t input_end=(uint64_t)input_offset+(uint64_t)ci*h*w;
 const uint64_t output_end=(uint64_t)output_offset+(uint64_t)co*oh*ow;
 // Reuse only within this invocation, and only when the complete layer fits
 // in the existing eight weight banks. Each output retains the same aligned
 // words and byte offset; no new tensor cache or changed accumulation order.
 const uint16_t weight_cache_pitch=(uint16_t)((terms+14)>>3);
 // Include the complete final AXI word, even its unused high bytes.
 const bool weights_disjoint=conv_weights_cache_safe(arena,weight_mem,output_offset,output_end,weight_offset,((uint64_t)co*terms+7)>>3);
 const bool cache_layer_weights=((co+7)>>3)*(uint32_t)weight_cache_pitch<=577 && weights_disjoint;
 const bool cache_coefficients=conv_coefficients_cache_safe(arena,params,output_offset,output_end,bias_offset,mult_offset,co);
 if(cache_coefficients) {
  load_layer_coefficients: for(int o=0;o<co;++o) {
   const uint32_t bias=params[bias_offset+o];
   const uint32_t multiplier=params[mult_offset+o];
   layer_coefficients[o]=(uint64_t)bias|((uint64_t)multiplier<<32);
  }
 }
 const bool full_rows=((input_offset|output_offset)&7)==0
  && input_end<=0x100000000ULL && output_end<=0x100000000ULL
  && (input_end<=output_offset || output_end<=input_offset)
  && (int64_t)ci*k*((w+14)/8)<=16384;
 // Small disjoint inputs are loaded packed once into the same128KiB raw
 // BRAM. No decoded tensor or extra buffer is allocated. The last aligned
 // word may contain unused input bytes, but every consumed pixel is masked.
 const bool full_tensor=full_rows && input_end-(uint64_t)input_offset<=131072ULL;
 // Wider stores change inter-channel order; preserve original scheduling
 // when input, coefficient, or aligned weight-word intervals may alias.
 // Keep the existing 4x1024-word k1 cache: ci>128 retains 64-pixel stripes.
 if(full_rows && cache_coefficients && weights_disjoint
    && (k!=1 || depthwise || co<=8 || ci<=128)) {
  stripe=128;
  while(stripe>16 && (int64_t)ci*k*((stripe*stride+k+14)/8)>16384)stripe-=16;
 }
 // The source/coefficients/weights must all be disjoint from output:
 // deferred stores otherwise change the legacy observation order.
 const bool buffer_rows=full_rows && cache_coefficients && weights_disjoint && ow<=64;
 // ow is positive, divisible by4. Narrow the guarded denominator before
 // division to avoid synthesizing an unnecessary signed32 divider.
 const uint8_t row_words=(uint8_t)(((uint32_t)ow>>2)&31u);
 const uint8_t rows_per_block=buffer_rows?(uint8_t)(32u/(row_words?row_words:1u)):1;
 uint8_t rows_in_block=0;
 int row_block_start=0;
 const int output_lanes=CONV_OUTPUT_LANES;
 int row_head=0;
 int row_tags[3]={-3,-3,-3};
#pragma HLS ARRAY_PARTITION variable=row_tags complete
 for(int y=0;y<oh;++y) {
  for(int xs=0;xs<ow;xs+=stripe) {
   int count=ow-xs;if(count>stripe)count=stripe;
   // ci<=512 and 1<=count<=128 were established above. The cache holds
   // 1024 words per bank; avoid a wide multiply in its capacity test.
   const uint16_t reuse_channels=(uint16_t)((uint32_t)ci&1023u);
   const uint8_t reuse_tiles=(uint8_t)(((uint32_t)count+15u)>>4);
   const bool reuse_k1_capacity=reuse_tiles<=2
     || (reuse_tiles==3 ? reuse_channels<=341 :
         reuse_tiles<=4 ? reuse_channels<=256 : reuse_channels<=128);
   // Nine packed tap windows per16pixel tile fit the same1024 entries.
   // floor(1024/(9*tiles)), for tiles1..8; no dynamic division or buffer.
   const bool reuse_k3_capacity=reuse_tiles<=1?reuse_channels<=113:
     reuse_tiles==2?reuse_channels<=56:reuse_tiles==3?reuse_channels<=37:
     reuse_tiles==4?reuse_channels<=28:reuse_tiles==5?reuse_channels<=22:
     reuse_tiles==6?reuse_channels<=18:reuse_tiles==7?reuse_channels<=16:reuse_channels<=14;
   const bool reuse_capacity=k==1?reuse_k1_capacity:reuse_k3_capacity;
   const bool reuse_inputs=full_rows && !depthwise && co>CONV_OUTPUT_LANES
     && reuse_capacity;
   int start=xs*stride-pad;if(start<0)start=0;
   int end=(xs+count-1)*stride+k-1-pad;if(end>=w)end=w-1;
   int span=end-start+1;
   int cache_start=full_rows?0:start;
   int rowwords=((full_rows?w:span)+14)/8;
   int row_slots[3];bool row_load[3];
#pragma HLS ARRAY_PARTITION variable=row_slots complete
#pragma HLS ARRAY_PARTITION variable=row_load complete
   for(int ky=0;ky<k;++ky) {
     int slot=row_head+ky;if(slot>=k)slot-=k;
     row_slots[ky]=slot;
     row_load[ky]=!full_rows || row_tags[slot]!=y*stride+ky-pad;
   }
   *phase=1;
   for(int ky=0;ky<k;++ky) {
     int iy=y*stride+ky-pad;
     if(full_tensor?(y==0 && xs==0 && ky==0):(iy>=0 && iy<h && row_load[ky])) {
      for(int c=0;c<(full_tensor?1:ci);++c) {
       int base=full_tensor?0:(c*h+iy)*w+cache_start,first=base>>3;
       int n=full_tensor?total_in:((full_rows?w:span)+(base&7)+7)/8;
       const int cache_base=full_tensor?0:(c*k+row_slots[ky])*rowwords;
       load_cache_words: for(int j=0;j<n;++j) {
#pragma HLS PIPELINE II=1
         cache[cache_base+j]=arena[(input_offset>>3)+first+j];
       }
       words+=n;
      }
     }
   }
   for(int ky=0;ky<k;++ky)row_tags[row_slots[ky]]=y*stride+ky-pad;
   for(int ob=0;ob<co;ob+=output_lanes) {
     *phase=2;
     const uint16_t weight_cache_base=cache_layer_weights?
       (uint16_t)(((uint32_t)ob>>3)*(uint32_t)weight_cache_pitch):0;
     for(int o=0;o<CONV_OUTPUT_LANES;++o) {
       if(cache_coefficients)coefficients[o]=o<output_lanes&&ob+o<co?layer_coefficients[(uint8_t)(ob+o)]:0;
       else {
        uint32_t bias=o<output_lanes&&ob+o<co?params[bias_offset+ob+o]:0;
        uint32_t multiplier=o<output_lanes&&ob+o<co?params[mult_offset+ob+o]:0;
        coefficients[o]=(uint64_t)bias|((uint64_t)multiplier<<32);
       }
       int base=(ob+o)*terms;woffs[o]=base&7;
       if(o<output_lanes&&ob+o<co && (!cache_layer_weights || (y==0 && xs==0))) {
         int first=base>>3,n=(terms+(base&7)+7)/8;
         load_weight_words: for(int j=0;j<n;++j) {
#pragma HLS PIPELINE II=1
           wc[o][weight_cache_base+j]=weight_mem[weight_offset+first+j];
         }
         weights+=n;
       }
     }
     for(int x0=xs;x0<xs+count;x0+=16) {
       // One row per bank per cycle; retain all128 int32 accumulators.
       init_sums_groups: for(int pg=0;pg<16/CONV_MAC_PIXELS;++pg) {
#pragma HLS PIPELINE II=1
         for(int o=0;o<CONV_OUTPUT_LANES;++o) {
#pragma HLS UNROLL
           for(int p=0;p<CONV_MAC_PIXELS;++p) {
#pragma HLS UNROLL
             sums[o][pg*CONV_MAC_PIXELS+p]=0;
           }
         }
       }
       for(int ky=0;ky<(depthwise?1:k);++ky)for(int kx=0;kx<(depthwise?1:k);++kx) {
         int iy=y*stride+ky-pad;
         int limit=depthwise?output_lanes:ci;
         for(int cb=0;cb<limit;cb+=64) {
           int n=limit-cb;if(n>64)n=64;
           // On the active reuse path x0-xs is 0/16/.../112 and every
           // channel address is below1024. Inactive masked values are unused.
           const uint8_t reuse_tile=(uint8_t)(((uint32_t)(x0-xs)>>4)&7u);
           const uint8_t reuse_group=(uint8_t)((uint32_t)reuse_tile*(k==3?9u:1u)
             +(uint32_t)(ky*k+kx));
           const uint16_t reuse_base=(uint16_t)(((uint32_t)reuse_group
             *(uint32_t)reuse_channels+((uint32_t)cb&511u))&1023u);
           // Every reuse read is dominated by this stripe's ob==0 write
           // of the same (x0,tap,channel,bank). Never reuse across stripes.
           reuse_stripe_fill: if(!reuse_inputs || ob==0) {
           *phase=1;
           unpack_channels: for(int c=0;c<(depthwise?k*k*output_lanes:n);++c) {
#pragma HLS PIPELINE II=1
             int channel=depthwise?ob+(c%CONV_OUTPUT_LANES):cb+c;
             // k is1 or3. DW tap runs0..k*k-1: two comparisons replace
             // the variable4-bit divide/remainder that added8 pipeline stages.
             const uint8_t tap=(uint8_t)(((uint32_t)c>>3)&15u);
             const uint8_t tap_y=tap<3?0:(tap<6?1:2);
             const uint8_t tap_x=tap<3?tap:(tap<6?tap-3:tap-6);
             const int unpack_ky=depthwise?(int)tap_y:ky;
             const int unpack_kx=depthwise?(int)tap_x:kx;
             const int unpack_iy=y*stride+unpack_ky-pad;
             int base=(channel*h+unpack_iy)*w+cache_start;
             int offset=(base&7)+(x0*stride+unpack_kx-pad-cache_start);
             int first=offset>=0?offset/8:-((-offset+7)/8);
             // Give HLS one common first address plus constant j offsets.
             // A select between two (base+pos) expressions made it assume
             // five reads on every cyclic bank and forced II3 in packed01.
             const int read_base=full_tensor?(base>>3):(channel*k+row_slots[unpack_ky])*rowwords;
             const int read_first=read_base+first;
             uint64_t b[5];
#pragma HLS ARRAY_PARTITION variable=b complete
             for(int j=0;j<5;++j) {
#pragma HLS UNROLL
               int pos=first+j;
               // The packed mapping has no per-row padding. Guard the global
               // index as well as source coordinates, especially the last row.
               const int address=read_first+j;
               b[j]=(channel<ci&&unpack_iy>=0&&unpack_iy<h&&pos>=0&&pos<rowwords
                 && (!full_tensor || (address>=0 && address<total_in)))?cache[address]:0;
             }
             CONV_PACKED_X_TYPE packed_x[CONV_MAC_PIXELS]={0};
#pragma HLS ARRAY_PARTITION variable=packed_x complete
             for(int p=0;p<16;++p) {
#pragma HLS UNROLL
               int sx=(x0+p)*stride+unpack_kx-pad;
               int off=offset+p*stride-first*8;
               uint64_t word=b[off>>3];
               int8_t xv=(channel<ci && x0+p<xs+count && sx>=0 && sx<w && unpack_iy>=0 && unpack_iy<h)?(int8_t)(word>>((off&7)*8)):(int8_t)0;
               packed_x[p%CONV_MAC_PIXELS]|=(CONV_PACKED_X_TYPE)(uint8_t)xv<<((p/CONV_MAC_PIXELS)*8);
             }
             for(int pl=0;pl<CONV_MAC_PIXELS;++pl) {
#pragma HLS UNROLL
               if(reuse_inputs)stripe_inputs[pl][(reuse_base+((uint32_t)c&63u))&1023u]=packed_x[pl];
               else xc[((c%CONV_X_CHANNEL_BANKS)/2)*CONV_MAC_PIXELS+pl][(depthwise?c/CONV_OUTPUT_LANES:c/CONV_X_CHANNEL_BANKS)*2+(c&1)]=packed_x[pl];
             }
           }
           }
           *phase=3;
           mac_channels: for(int c=0;c<(depthwise?k*k:n);++c)mac_groups: for(int pg=0;pg<16/CONV_MAC_PIXELS;++pg) {
#pragma HLS PIPELINE II=1
             *mac_event=1;
             int8_t xread[CONV_X_CHANNEL_BANKS*CONV_MAC_PIXELS];
#pragma HLS ARRAY_PARTITION variable=xread complete
             int xrow=depthwise?c:(c/CONV_X_CHANNEL_BANKS);
             for(int xb=0;xb<CONV_X_CHANNEL_BANKS*CONV_MAC_PIXELS;++xb) {
#pragma HLS UNROLL
               // Each bank has one explicit read. Unneeded banks are not
               // read: every consumed word was written by this unpack.
               CONV_PACKED_X_TYPE xword=0;
               if(reuse_inputs) {
                 if(xb<CONV_MAC_PIXELS)xword=stripe_inputs[xb][(reuse_base+((uint32_t)c&63u))&1023u];
               } else xword=(depthwise || xb/CONV_MAC_PIXELS==(c%CONV_X_CHANNEL_BANKS))?xc[((xb/CONV_MAC_PIXELS)/2)*CONV_MAC_PIXELS+(xb%CONV_MAC_PIXELS)][xrow*2+((xb/CONV_MAC_PIXELS)&1)]:0;
               xread[xb]=(int8_t)(xword>>(pg*8));
             }
             for(int o=0;o<CONV_OUTPUT_LANES;++o) {
#pragma HLS UNROLL
               for(int p=0;p<CONV_MAC_PIXELS;++p) {
#pragma HLS UNROLL
                 int8_t xv=xread[(reuse_inputs?0:(depthwise?o:(c%CONV_X_CHANNEL_BANKS)))*CONV_MAC_PIXELS+p];
                 int wi=(depthwise?c:(cb+c)*k*k+ky*k+kx)+woffs[o];
                 int8_t wv=(o<output_lanes&&ob+o<co)?(int8_t)(wc[o][weight_cache_base+(wi>>3)]>>((wi&7)*8)):0;
                 int16_t product=(int16_t)xv*(int16_t)wv;
#pragma HLS BIND_OP variable=product op=mul impl=dsp latency=2
                 sums[o][pg*CONV_MAC_PIXELS+p]+=product;
               }
             }
           }
           issues+=(depthwise?k*k:n)*(16/CONV_MAC_PIXELS);
         }
       }
       *phase=4;
       // Keep the o/pg loop nest perfect: one16-iteration pipeline, not
       // eight separate2-iteration pipelines. Each cycle quantizes8 pixels.
       quantize_channels: for(int o=0;o<CONV_OUTPUT_LANES;++o)quantize_groups: for(int pg=0;pg<2;++pg) {
#pragma HLS PIPELINE II=1
         uint64_t coefficient=coefficients[o];
         int32_t bias=(int32_t)(uint32_t)coefficient;
         uint32_t multiplier=(uint32_t)(coefficient>>32);
         uint32_t word0=0,word1=0;
         for(int p=0;p<8;++p) {
#pragma HLS UNROLL
           int8_t q=quantize(sums[o][pg*8+p],bias,multiplier,relu);
           if(p<4)word0|=(uint32_t)(uint8_t)q<<(8*p);
           else word1|=(uint32_t)(uint8_t)q<<(8*(p-4));
         }
         // One selected base, then consecutive+0/+1 word addresses. The
         // cyclic2 banks provide one independent write for each valid word.
         const uint16_t base=(uint16_t)(buffer_rows?
           (((uint32_t)(ob+o)<<5)+(uint32_t)(rows_in_block*(ow/4)+(x0/4))):
           (((uint32_t)o<<5)+(uint32_t)((x0-xs)/4)));
         const uint16_t address=(uint16_t)((uint32_t)base+(uint32_t)(pg*2));
         const bool odd=(address&1u)!=0;
         // Preserve8192 as an invalid value, never mask it back to0. A
         // valid final word8191 disables the paired even write via valid1.
         const uint16_t even_address=(uint16_t)(((uint32_t)address+1u)&~1u);
         const uint16_t odd_address=(uint16_t)((uint32_t)address|1u);
         const bool valid0=x0+pg*8<xs+count;
         const bool valid1=x0+pg*8+4<xs+count;
         if(o<output_lanes&&ob+o<co) {
           // Exactly one store statement for each physical cyclic bank.
           if(odd?valid1:valid0)output_tile[even_address]=odd?word1:word0;
           if(odd?valid0:valid1)output_tile[odd_address]=odd?word0:word1;
         }
       }
       stores+=output_lanes*4;
     }
     *phase=5;
     int lanes=co-ob;if(lanes>output_lanes)lanes=output_lanes;
     // One physical callsite. On a row-block drain, this output-channel
     // group is complete; disjoint input/params/weights permit its early store.
     const bool drain_rows=buffer_rows && xs+count==ow
       && (rows_in_block+1==rows_per_block || y==oh-1);
     if(!buffer_rows || drain_rows) {
       const uint32_t dst=output_offset+ob*oh*ow+(buffer_rows?row_block_start*ow:y*ow+xs);
       store_output_tile(arena,output_tile,dst,oh*ow,lanes,
                         buffer_rows?(rows_in_block+1)*ow:count,buffer_rows?ob:0);
     }
   }
  }
  if(buffer_rows) {
   ++rows_in_block;
   if(rows_in_block==rows_per_block || y==oh-1) {
    row_block_start=y+1;
    rows_in_block=0;
   }
  }
  if(full_rows) {
   row_head+=stride;
   if(row_head>=k)row_head-=k;
   if(k==1)row_head=0;
  }
 }
 *phase=6;stats[0]=words;stats[1]=weights;stats[2]=issues;stats[3]=stores;stats[15]=0;*phase=7;
}

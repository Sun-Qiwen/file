#pragma once
#include <cmath>
static float cnn_from_bits(uint32_t x){union{uint32_t u;float f;}v;v.u=x;return v.f;}
static uint32_t cnn_to_bits(float x){union{uint32_t u;float f;}v;v.f=x;return v.u;}
static float cnn_read_float(const uint64_t*a,uint32_t base,uint32_t i){
#pragma HLS INLINE
 uint64_t word=a[(base>>3)+(i>>1)];return cnn_from_bits((uint32_t)(word>>((i&1)*32)));
}
// One serial floating point arithmetic instance services all CNN special ops.
// Fixed operation order; no FMA; existing integer MAC datapath is untouched.
static float cnn_math(int op,float a,float b){
#pragma HLS INLINE off
 if(op==0)return a+b;
 if(op==1)return a*b;
 if(op==2)return a/b;
 return std::sqrt(a);
}
// GN-only datapaths. The common math instance remains serial for the other
// special ops and the infrequent group-level divide/sqrt. No FP contraction.
static int32_t cnn_gn_load(const uint64_t *a,uint32_t first,int words,uint64_t cache[4608]){
#pragma HLS INLINE off
 int32_t sum=0;
 gn_load_words:for(int i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  const uint64_t word=a[first+i];cache[i]=word;
  int32_t part=0;
  for(int lane=0;lane<8;lane++){
#pragma HLS UNROLL
   part+=(int32_t)(int8_t)(word>>(lane*8));
  }
  // The frozen maximum group sum fits int32. Integer regrouping is exact.
  sum+=part;
 }
 return sum;
}
static float cnn_gn_variance(const uint64_t cache[4608],int size,float mean){
#pragma HLS INLINE off
 float squares[16];
#pragma HLS BIND_STORAGE variable=squares type=ram_s2p impl=lutram
 gn_variance_elements:for(int i=0;i<size;i++){
#pragma HLS PIPELINE II=1
  const uint64_t word=cache[i>>3];
  const int8_t q=(int8_t)(word>>((i&7)*8));
  const float delta=(float)q+(-mean);
  const float square=delta*delta;
  const float previous=i<16?0.f:squares[i%16];
  squares[i%16]=previous+square;
 }
 // Preserve lane0..15 reduction, including its leading +0 operation.
 float total=0.f;
 for(int j=0;j<16;j++)total=total+(j<size?squares[j]:0.f);
 return total;
}
static void cnn_gn_output(const uint64_t cache[4608],uint64_t block[128],int start,int pairs,
                          float mean,float inv,float gamma,float beta){
#pragma HLS INLINE off
 gn_affine_pairs:for(int i=0;i<pairs;i++){
#pragma HLS PIPELINE II=1
  const int index=start+i*2;
  const uint64_t word=cache[index>>3];
  const int8_t q0=(int8_t)(word>>((index&7)*8));
  const int8_t q1=(int8_t)(word>>(((index&7)+1)*8));
  const float delta0=(float)q0+(-mean),delta1=(float)q1+(-mean);
  const float normalized0=delta0*inv,normalized1=delta1*inv;
  const float scaled0=normalized0*gamma,scaled1=normalized1*gamma;
  float value0=scaled0+beta,value1=scaled1+beta;
  if(value0<0.f)value0=0.f;if(value1<0.f)value1=0.f;
  block[i]=(uint64_t)cnn_to_bits(value0)|((uint64_t)cnn_to_bits(value1)<<32);
 }
}
static void cnn_gn_store(uint64_t *a,uint32_t first,int words,const uint64_t block[128]){
#pragma HLS INLINE off
 gn_store_words:for(int i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  a[first+i]=block[i];
 }
}
// Quantization-only block pipeline. Retain a real FP32 division per value;
// no reciprocal approximation and no changes to the serial shared math unit.
static void cnn_quant_load(const uint64_t *a,uint32_t first,int words,uint64_t input[64]){
#pragma HLS INLINE off
 quant_load_words:for(int i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  input[i]=a[first+i];
 }
}
static void cnn_quant_convert(const uint64_t input[64],uint64_t output[16],int count,float scale){
#pragma HLS INLINE off
 uint64_t packed=0;
 quant_convert_elements:for(int i=0;i<count;i++){
#pragma HLS PIPELINE II=1
  const uint64_t word=input[i>>1];
  const float v=cnn_from_bits((uint32_t)(word>>((i&1)*32)));
  const float q=v/scale;
  int value;
  if(q>=127.f)value=127;else if(q<=-127.f)value=-127;
  else {const float magnitude=q<0.f?-q:q;const int rounded=(int)(magnitude+.5f);value=q<0.f?-rounded:rounded;}
  // Fixed shift register avoids a variable 64-bit packing barrel shifter.
  packed=(packed>>8)|((uint64_t)(uint8_t)(int8_t)value<<56);
  if((i&7)==7)output[i>>3]=packed;
 }
}
static void cnn_quant_store(uint64_t *a,uint32_t first,int words,const uint64_t output[16]){
#pragma HLS INLINE off
 quant_store_words:for(int i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  a[first+i]=output[i];
 }
}
// Packed loads retain the old row snapshot and right/bottom-biased ordered
// comparisons (including NaNs and signed zero). Restrict the fast path to the
// bounded, aligned, non-overlapping domain; legacy direct-call behavior stays
// below for every other shape and alias pattern.
static bool cnn_pool_packed_eligible(const Command &s){
#pragma HLS INLINE
 // Bounds below validate these masked operands before the result is used.
 // Keep eligibility hardware bounded instead of inferring 64-bit products.
 const uint32_t output=(s.c&127u)*(s.h&127u)*(s.w&127u),input=output*4u;
 return s.c>0 && s.c<=96 && s.h>0 && s.h<=96 && (s.h&1)==0
   && s.w>0 && s.w<=96 && (s.w&3)==0 && ((s.a|s.out)&7)==0
   && (uint64_t)s.a+input<=0x100000000ULL && (uint64_t)s.out+output<=0x100000000ULL
   && ((uint64_t)s.a+input<=s.out || (uint64_t)s.out+output<=s.a);
}
static void cnn_pool_load_row(const uint64_t *a,uint32_t first,uint8_t words,float row[96]){
#pragma HLS INLINE off
 pool_load_words:for(uint8_t i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  const uint64_t word=a[first+i];
  row[i*2]=cnn_from_bits((uint32_t)word);row[i*2+1]=cnn_from_bits((uint32_t)(word>>32));
 }
}
static void cnn_pool_reduce_row(const float top[96],const float bottom[96],uint8_t width,uint64_t output[24]){
#pragma HLS INLINE off
 uint64_t packed=0;
 pool_reduce_pixels:for(uint8_t x=0;x<width;x++){
#pragma HLS PIPELINE II=1
  const uint8_t k=x*2;
  const float p=top[k]>top[k+1]?top[k]:top[k+1];
  const float q=bottom[k]>bottom[k+1]?bottom[k]:bottom[k+1];
  const float value=p>q?p:q;
  packed=(packed>>32)|((uint64_t)cnn_to_bits(value)<<32);
  if(x&1)output[x>>1]=packed;
 }
}
static void cnn_pool_store_row(uint64_t *a,uint32_t first,uint8_t words,const uint64_t output[24]){
#pragma HLS INLINE off
 pool_store_words:for(uint8_t i=0;i<words;i++){
#pragma HLS PIPELINE II=1
  a[first+i]=output[i];
 }
}
static bool cnn_up_cached_eligible(const Command &s){
#pragma HLS INLINE
 const uint32_t area=(s.h&31u)*(s.w&31u),elements=(s.c&127u)*area;
 const uint32_t input=elements*4u,upsampled=elements*16u;
 const uint32_t skip=(s.co&127u)*area*16u,output=upsampled+skip;
 return s.c>0 && s.c<=96 && s.co<=96 && s.h>0 && s.h<=24
   && s.w>0 && s.w<=24 && (s.w&1)==0 && ((s.a|s.b|s.out)&7)==0
   && (uint64_t)s.a+input<=0x100000000ULL && (uint64_t)s.b+skip<=0x100000000ULL
   && (uint64_t)s.out+output<=0x100000000ULL
   && ((uint64_t)s.a+input<=s.out || (uint64_t)s.out+output<=s.a)
   && ((uint64_t)s.b+skip<=s.out || (uint64_t)s.out+output<=s.b);
}
// One bounded interpolation pipeline, shared between horizontal and vertical
// passes. Keep both multiplies, including border weight zero, then their add.
// Reusing an identical horizontal result changes no FP operation ordering.
static float cnn_up_interpolate(float left,float right,int fraction){
#pragma HLS INLINE off
#pragma HLS PIPELINE II=2
#pragma HLS ALLOCATION operation instances=fmul limit=1
 // All three weights and their complements are exactly representable FP32.
 const float weight=fraction==0?0.f:fraction==1?.25f:.75f;
 const float complement=fraction==0?1.f:fraction==1?.75f:.25f;
 const float first=left*complement,second=right*weight;
 return first+second;
}
static void cnn_up_cached(uint64_t *a,const Command &s){
#pragma HLS INLINE off
#pragma HLS ALLOCATION function instances=cnn_up_interpolate limit=1
 float horizontal[1152],row[24];uint64_t copy[64];
#pragma HLS BIND_STORAGE variable=horizontal type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=row type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=copy type=ram_1p impl=bram
 // The caller has checked these bounded dimensions. Rolling word addresses
 // avoid wide three-dimensional address multipliers on the fast path.
 const uint8_t h=s.h&31u,w=s.w&31u,channels=s.c&127u,skip_channels=s.co&127u;
 const uint8_t oh=h*2,ow=w*2;
 uint32_t input_first=s.a>>3,output_first=s.out>>3;
 for(uint8_t ch=0;ch<channels;ch++){
  for(uint8_t y=0;y<h;y++){
   up_load_words:for(uint8_t i=0;i<w/2;i++){
#pragma HLS PIPELINE II=1
    const uint64_t word=a[input_first+i];
    row[i*2]=cnn_from_bits((uint32_t)word);row[i*2+1]=cnn_from_bits((uint32_t)(word>>32));
   }
   input_first+=w/2;
   up_horizontal_pixels:for(uint8_t x=0;x<ow;x++){
#pragma HLS PIPELINE II=2
    const uint8_t x0=x==0?0:(x-1u)>>1,x1=x0+1<w?x0+1:x0;
    const int dx=x==0?0:(x&1)?1:3;
    horizontal[y*48+x]=cnn_up_interpolate(row[x0],row[x1],dx);
   }
  }
  for(uint8_t y=0;y<oh;y++){
   const uint8_t y0=y==0?0:(y-1u)>>1,y1=y0+1<h?y0+1:y0;
   const int dy=y==0?0:(y&1)?1:3;
   uint64_t packed=0;
   up_vertical_pixels:for(uint8_t x=0;x<ow;x++){
#pragma HLS PIPELINE II=2
    const float value=cnn_up_interpolate(horizontal[y0*48+x],horizontal[y1*48+x],dy);
    packed=(packed>>32)|((uint64_t)cnn_to_bits(value)<<32);
    if(x&1)copy[x>>1]=packed;
   }
   up_store_words:for(uint8_t i=0;i<w;i++){
#pragma HLS PIPELINE II=1
    a[output_first+i]=copy[i];
   }
   output_first+=w;
  }
 }
 const uint32_t words=skip_channels*h*w*2;
 for(uint32_t base=0;base<words;base+=64){
  const uint8_t count=words-base<64?words-base:64;
  up_copy_load_words:for(uint8_t i=0;i<count;i++){
#pragma HLS PIPELINE II=1
   copy[i]=a[(s.b>>3)+base+i];
  }
  up_copy_store_words:for(uint8_t i=0;i<count;i++){
#pragma HLS PIPELINE II=1
   a[output_first+base+i]=copy[i];
  }
 }
}
static void cnn_ops(uint64_t *a,const uint32_t *params,const Command &s,uint32_t *stats,volatile uint32_t *phase){
#pragma HLS INLINE off
#pragma HLS ALLOCATION function instances=cnn_math limit=1
 *phase=s.kind+16;
 const int area=s.h*s.w;
 if(s.kind==7){ // FP32 tensor -> symmetric INT8, nearest ties away.
  const float scale=cnn_from_bits(s.ma);
  const bool blocked=(s.n&7)==0 && ((s.a|s.out)&7)==0
    && ((uint64_t)s.a+4ULL*s.n<=s.out || (uint64_t)s.out+s.n<=s.a);
  uint64_t quant_input[64],quant_output[16];
#pragma HLS BIND_STORAGE variable=quant_input type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=quant_output type=ram_1p impl=lutram
  if(blocked){
   for(uint32_t base=0;base<s.n;base+=128){
    const int count=s.n-base<128?s.n-base:128;
    cnn_quant_load(a,(s.a>>3)+(base>>1),count>>1,quant_input);
    cnn_quant_convert(quant_input,quant_output,count,scale);
    cnn_quant_store(a,(s.out>>3)+(base>>3),count>>3,quant_output);
   }
  }else{
  for(uint32_t i=0;i<s.n;i+=8){
   uint64_t packed=0;
   for(int lane=0;lane<8;lane++){
    float v=cnn_read_float(a,s.a,i+lane);float q=cnn_math(2,v,scale);
    int value;
    if(q>=127.f)value=127;else if(q<=-127.f)value=-127;
    else {float magnitude=q<0.f?-q:q;int rounded=(int)cnn_math(0,magnitude,.5f);value=q<0.f?-rounded:rounded;}
    packed|=(uint64_t)(uint8_t)(int8_t)value<<(lane*8);
   }
   a[(s.out>>3)+(i>>3)]=packed;
  }
  }
 }else if(s.kind==8){ // INT8 conv output -> dynamic GN -> affine/ReLU FP32.
  float gamma[96],beta[96];
#pragma HLS BIND_STORAGE variable=gamma type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=beta type=ram_1p impl=bram
  for(int ch=0;ch<(int)s.c;ch++){gamma[ch]=cnn_from_bits(params[s.weights+ch]);beta[ch]=cnn_from_bits(params[s.bias+ch]);}
  const int group_channels=s.c/4,size=group_channels*area;
  const float scale=cnn_from_bits(s.ma);
  // Fixed model uses aligned, non-aliasing groups, maximum 36KiB. Keep the
  // frozen scalar behavior for other direct-test shapes and overlapping data.
  const bool cached=s.c>0 && s.c<=96 && (s.c%4)==0 && size>0 && size<=36864
    && (area&1)==0 && (size&7)==0 && ((s.a|s.out)&7)==0
    && ((uint64_t)s.a+s.n<=s.out || (uint64_t)s.out+4ULL*s.n<=s.a);
  uint64_t group_cache[4608],output_block[128];
#pragma HLS BIND_STORAGE variable=group_cache type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=output_block type=ram_1p impl=bram
  for(int g=0;g<4;g++){
   const int off=g*size;int32_t sum=0;
   if(cached){
    sum=cnn_gn_load(a,(s.a+off)>>3,size>>3,group_cache);
    const float mean=cnn_math(2,(float)sum,(float)size);
    const float total=cnn_gn_variance(group_cache,size,mean);
    const float qvar=cnn_math(2,total,(float)size);
    const float first=cnn_math(1,qvar,scale),variance=cnn_math(1,first,scale);
    const float added=cnn_math(0,variance,1.e-5f),root=cnn_math(3,added,0.f),inv=cnn_math(2,scale,root);
    for(int local=0;local<group_channels;local++){
     const int ch=g*group_channels+local;
     for(int pixel=0;pixel<area;pixel+=256){
      const int pairs=(area-pixel<256?area-pixel:256)/2;
      cnn_gn_output(group_cache,output_block,local*area+pixel,pairs,mean,inv,gamma[ch],beta[ch]);
      cnn_gn_store(a,(s.out>>3)+(ch*area+pixel)/2,pairs,output_block);
     }
    }
    continue;
   }
   for(int i=0;i<size;i++)sum+=(int32_t)read_byte(a,s.a,off+i);
   const float mean=cnn_math(2,(float)sum,(float)size);
   float squares[16];
#pragma HLS BIND_STORAGE variable=squares type=ram_s2p impl=lutram
   for(int i=0;i<size;i++){
    float delta=cnn_math(0,(float)read_byte(a,s.a,off+i),-mean);
    float square=cnn_math(1,delta,delta);float previous=i<16?0.f:squares[i%16];squares[i%16]=cnn_math(0,previous,square);
   }
   float total=0.f;for(int j=0;j<16;j++)total=cnn_math(0,total,j<size?squares[j]:0.f);
   const float qvar=cnn_math(2,total,(float)size);
   const float first=cnn_math(1,qvar,scale),variance=cnn_math(1,first,scale);
   const float added=cnn_math(0,variance,1.e-5f),root=cnn_math(3,added,0.f),inv=cnn_math(2,scale,root);
   for(int local=0;local<group_channels;local++){
    const int ch=g*group_channels+local;
    for(int pixel=0;pixel<area;pixel+=2){
     uint64_t packed=0;
     for(int lane=0;lane<2;lane++){
      int index=ch*area+pixel+lane;
      float delta=cnn_math(0,(float)read_byte(a,s.a,index),-mean);
      float normalized=cnn_math(1,delta,inv),scaled=cnn_math(1,normalized,gamma[ch]);
      float value=cnn_math(0,scaled,beta[ch]);if(value<0.f)value=0.f;
      packed|=(uint64_t)cnn_to_bits(value)<<(lane*32);
     }
     a[(s.out>>3)+(ch*area+pixel)/2]=packed;
    }
   }
  }
 }else if(s.kind==9){ // CNN float MaxPool2, distinct from YOLOX fixed kernels.
  float top[96],bottom[96];
#pragma HLS BIND_STORAGE variable=top type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=bottom type=ram_2p impl=bram
  int oh=s.h/2,ow=s.w/2;
  uint64_t pool_output[24];
#pragma HLS BIND_STORAGE variable=pool_output type=ram_1p impl=lutram
  const bool packed_rows=cnn_pool_packed_eligible(s);
  // Fast rows consume two complete source rows and one complete output row.
  // The eligibility gate proves the row/channel boundaries have no tails.
  const uint8_t packed_width=s.w&127u;
  uint32_t pool_input_first=s.a>>3,pool_output_first=s.out>>3;
  for(int ch=0;ch<(int)s.c;ch++)for(int y=0;y<oh;y++){
   if(packed_rows){
    cnn_pool_load_row(a,pool_input_first,packed_width/2,top);
    cnn_pool_load_row(a,pool_input_first+packed_width/2,packed_width/2,bottom);
    cnn_pool_reduce_row(top,bottom,packed_width/2,pool_output);
    cnn_pool_store_row(a,pool_output_first,packed_width/4,pool_output);
    pool_input_first+=packed_width;
    pool_output_first+=packed_width/4;
    continue;
   }
   for(int x=0;x<(int)s.w;x++){top[x]=cnn_read_float(a,s.a,(ch*s.h+y*2)*s.w+x);bottom[x]=cnn_read_float(a,s.a,(ch*s.h+y*2+1)*s.w+x);}
   for(int x=0;x<ow;x+=2){
    uint64_t packed=0;
    for(int lane=0;lane<2;lane++){
     int k=(x+lane)*2;float p=top[k]>top[k+1]?top[k]:top[k+1];float q=bottom[k]>bottom[k+1]?bottom[k]:bottom[k+1];float value=p>q?p:q;
     packed|=(uint64_t)cnn_to_bits(value)<<(lane*32);
    }
    a[(s.out>>3)+(ch*oh*ow+y*ow+x)/2]=packed;
   }
  }
 }else if(s.kind==10){ // Bilinear align_corners=False, then channel concat.
  if(cnn_up_cached_eligible(s)){
   cnn_up_cached(a,s);
  }else{
  float tile[24][24];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=bram
  int oh=s.h*2,ow=s.w*2;
  for(int ch=0;ch<(int)s.c;ch++){
   for(int y=0;y<(int)s.h;y++)for(int x=0;x<(int)s.w;x++)tile[y][x]=cnn_read_float(a,s.a,(ch*s.h+y)*s.w+x);
   for(int y=0;y<oh;y++)for(int x=0;x<ow;x+=2){
    uint64_t packed=0;
    int y0=y==0?0:(y-1)/2,y1=y0+1<(int)s.h?y0+1:y0;float dy=y==0?0.f:(y&1)?.25f:.75f;
    for(int lane=0;lane<2;lane++){
     int xx=x+lane,x0=xx==0?0:(xx-1)/2,x1=x0+1<(int)s.w?x0+1:x0;float dx=xx==0?0.f:(xx&1)?.25f:.75f;
     float t00=cnn_math(1,tile[y0][x0],1.f-dx),t01=cnn_math(1,tile[y0][x1],dx);
     float t10=cnn_math(1,tile[y1][x0],1.f-dx),t11=cnn_math(1,tile[y1][x1],dx);
     float upper=cnn_math(0,t00,t01),lower=cnn_math(0,t10,t11);
     float t=cnn_math(1,upper,1.f-dy),b=cnn_math(1,lower,dy),value=cnn_math(0,t,b);
     packed|=(uint64_t)cnn_to_bits(value)<<(lane*32);
    }
    a[(s.out>>3)+(ch*oh*ow+y*ow+x)/2]=packed;
   }
  }
  int count=s.co*oh*ow;
  for(int i=0;i<count/2;i++)a[(s.out>>3)+s.c*oh*ow/2+i]=a[(s.b>>3)+i];
  }
 }else if(s.kind==11){ // FP32 adaptive average + linear valid head.
  float sums[16];
#pragma HLS BIND_STORAGE variable=sums type=ram_s2p impl=lutram
  float channels[96];
#pragma HLS BIND_STORAGE variable=channels type=ram_1p impl=bram
  for(int ch=0;ch<96;ch++){
   for(int i=0;i<144;i++)sums[i%16]=cnn_math(0,i<16?0.f:sums[i%16],cnn_read_float(a,s.a,ch*144+i));
   float total=0.f;for(int j=0;j<16;j++)total=cnn_math(0,total,sums[j]);channels[ch]=cnn_math(2,total,144.f);
  }
  for(int ch=0;ch<96;ch++){float product=cnn_math(1,channels[ch],cnn_from_bits(params[s.weights+ch]));sums[ch%16]=cnn_math(0,ch<16?0.f:sums[ch%16],product);}
  float total=0.f;for(int j=0;j<16;j++)total=cnn_math(0,total,sums[j]);float value=cnn_math(0,total,cnn_from_bits(params[s.bias]));
  write_four(a,s.out,cnn_to_bits(value));
 }else if(s.kind==12){ // Heatmap INT8 logits -> FP32 output. No activation.
  float scale=cnn_from_bits(s.ma);
  for(uint32_t i=0;i<s.n;i+=2){float lo=cnn_math(1,(float)read_byte(a,s.a,i),scale),hi=cnn_math(1,(float)read_byte(a,s.a,i+1),scale);a[(s.out>>3)+(i>>1)]=(uint64_t)cnn_to_bits(lo)|((uint64_t)cnn_to_bits(hi)<<32);}
 }else{stats[15]=3;return;}
 stats[15]=0;
}

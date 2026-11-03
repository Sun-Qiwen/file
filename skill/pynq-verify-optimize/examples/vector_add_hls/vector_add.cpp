#include "vector_add.hpp"

extern "C" std::uint32_t vector_add(const std::uint32_t* a,
                                    const std::uint32_t* b,
                                    std::uint32_t* out,
                                    std::uint32_t n) {
#pragma HLS INTERFACE m_axi port=a offset=slave bundle=gmem_a depth=4096
#pragma HLS INTERFACE m_axi port=b offset=slave bundle=gmem_b depth=4096
#pragma HLS INTERFACE m_axi port=out offset=slave bundle=gmem_out depth=4096
#pragma HLS INTERFACE s_axilite port=a bundle=control
#pragma HLS INTERFACE s_axilite port=b bundle=control
#pragma HLS INTERFACE s_axilite port=out bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if (n > VECTOR_ADD_MAX_N) return 1;
    for (std::uint32_t i = 0; i < n; ++i) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=0 max=4096
        out[i] = a[i] + b[i];
    }
    return 0;
}

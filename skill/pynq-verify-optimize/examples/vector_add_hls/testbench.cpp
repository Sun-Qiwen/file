#include "vector_add.hpp"
#include <array>
#include <cstring>
#include <iostream>

namespace {
constexpr std::size_t PAD = 8;
constexpr std::size_t SIZE = VECTOR_ADD_MAX_N + 2 * PAD;
constexpr std::uint32_t SENTINEL = 0xA5C35A3Cu;
std::uint32_t rng(std::uint32_t& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    return state;
}
}

int main(int argc, char** argv) {
    const bool inject = argc == 2 && std::strcmp(argv[1], "--inject-error") == 0;
    if (argc > 1 && !inject) return 2;
    std::uint32_t state = 0x12345678u;
    bool injected = false;
    unsigned cases = 0;
    // Repeated shapes exercise state reuse; all input values are reproducible.
    const std::uint32_t lengths[] = {0, 1, 3, 63, 64, 65, 1023, 4095, 4096, 4097, 1, 65};
    for (unsigned repeat = 0; repeat < 3; ++repeat) {
        for (std::uint32_t n : lengths) {
            std::array<std::uint32_t, SIZE> a, b, out;
            out.fill(SENTINEL);
            for (std::size_t i = 0; i < SIZE; ++i) {
                a[i] = rng(state); b[i] = rng(state);
            }
            a[PAD] = 0xffffffffu; b[PAD] = 1u;
            a[PAD + 1] = 0u; b[PAD + 1] = 0u;
            a[PAD + 2] = 0xffffffffu; b[PAD + 2] = 0xffffffffu;
            const auto saved_a = a;
            const auto saved_b = b;
            const auto status = vector_add(a.data() + PAD, b.data() + PAD, out.data() + PAD, n);
            const bool valid = n <= VECTOR_ADD_MAX_N;
            if (status != (valid ? 0u : 1u) || a != saved_a || b != saved_b) {
                std::cerr << "STATUS_OR_INPUT_FAILURE n=" << n << '\n'; return 1;
            }
            if (inject && !injected && valid && n > 0) {
                out[PAD] ^= 1u; injected = true;
            }
            for (std::size_t i = 0; i < SIZE; ++i) {
                std::uint32_t expected = SENTINEL;
                if (valid && i >= PAD && i < PAD + n) {
                    const std::uint64_t sum = std::uint64_t(saved_a[i]) + saved_b[i];
                    expected = static_cast<std::uint32_t>(sum & 0xffffffffULL);
                }
                if (out[i] != expected) {
                    std::cerr << (injected ? "INJECTED_ERROR_DETECTED" : "OUTPUT_OR_GUARD_FAILURE")
                              << " n=" << n << " index=" << i << '\n'; return 1;
                }
            }
            ++cases;
        }
    }
    if (inject) { std::cerr << "INJECTION_NOT_EXERCISED\n"; return 2; }
    std::cout << "PASS cases=" << cases << " reference=uint64_mask guards=checked\n";
    return 0;
}

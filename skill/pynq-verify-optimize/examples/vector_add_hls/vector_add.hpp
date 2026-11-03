#ifndef PYNQ_SKILL_VECTOR_ADD_HPP
#define PYNQ_SKILL_VECTOR_ADD_HPP
#include <cstdint>

constexpr std::uint32_t VECTOR_ADD_MAX_N = 4096;
// Disjoint, 4-byte-aligned arrays of at least n words; result wraps modulo 2^32.
// n == 0: success, no memory access. n > MAX_N: status 1, no memory access.
extern "C" std::uint32_t vector_add(const std::uint32_t* a,
                                    const std::uint32_t* b,
                                    std::uint32_t* out,
                                    std::uint32_t n);
#endif

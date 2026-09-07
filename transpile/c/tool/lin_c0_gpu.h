/*
 * lin_c0_gpu.h — Sovereign GPU Verification and Execution for LinVM C0
 *
 * Provides GPU compilation, OpenCL dispatch and differential verification
 * directly from LinVM Compiler 0 with ZERO Zig dependency.
 */
#ifndef LIN_C0_GPU_H
#define LIN_C0_GPU_H

#include "lin_c0_front.h"

/*
 * Run differential GPU verification suite on a .lin source file.
 * Tests every unary kernel function across 7 canonical buffer sizes:
 *   [1, 2, 7, 31, 1024, 65536, 1000000]
 * Compares element-by-element between LinVM (CPU) and Physical GPU (OpenCL).
 *
 * Returns 0 on 100% parity PASS, non-zero on failure.
 */
int c0_gpu_verify(C0Arena *a, const char *file_path);

#endif /* LIN_C0_GPU_H */

/*
 * lin_c0_jit.h — In-Memory C11 JIT Compiler & Runner for LinVM Compiler 0.
 *
 * Compiles VmModule definitions directly to native machine code in RAM
 * using libtcc with zero disk touching.
 */
#ifndef LIN_C0_JIT_H
#define LIN_C0_JIT_H

#include "lin_common.h"
#include "lin_vm.h"

typedef struct {
    int64_t val;
    double compile_ms;
    double exec_us;
    int success;
    const char *err;
} LinJitResult;

/* Check if dynamic libtcc JIT runtime is available */
int c0_jit_is_available(void);

/* Transpiles a VmModule to a standalone C11 source string in memory */
char *c0_jit_emit_c11(const VmModule *mod);

/* Compiles a VmModule in memory via libtcc and executes the named function */
int c0_jit_exec(
    const VmModule *mod,
    const char *fn_name,
    const int64_t *args,
    size_t nargs,
    LinJitResult *out
);

/* Runs roundtrip between interpreted LinVM and in-memory JIT, checking consensus */
int c0_jit_roundtrip(
    const VmModule *mod,
    const char *fn_name,
    const int64_t *args,
    size_t nargs
);

/* Verifies all eligible functions in a module under JIT */
int c0_jit_verify_module(const VmModule *mod);

#endif /* LIN_C0_JIT_H */

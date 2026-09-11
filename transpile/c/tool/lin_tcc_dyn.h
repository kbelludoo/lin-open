/*
 * lin_tcc_dyn.h — Dynamic TinyCC (libtcc) loader for LinVM C0 in-memory JIT.
 *
 * Provides a clean runtime abstraction for libtcc with zero hard dependencies
 * on system headers. Resolves symbols via dlopen/dlsym with fallback paths.
 */
#ifndef LIN_TCC_DYN_H
#define LIN_TCC_DYN_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

#define TCC_OUTPUT_MEMORY 1

struct TCCState;
typedef struct TCCState TCCState;

typedef TCCState *(*fn_tcc_new)(void);
typedef void (*fn_tcc_delete)(TCCState *s);
typedef void (*fn_tcc_set_lib_path)(TCCState *s, const char *path);
typedef int (*fn_tcc_set_output_type)(TCCState *s, int output_type);
typedef int (*fn_tcc_add_symbol)(TCCState *s, const char *name, const void *val);
typedef int (*fn_tcc_compile_string)(TCCState *s, const char *buf);
typedef int (*fn_tcc_relocate)(TCCState *s1);
typedef void *(*fn_tcc_get_symbol)(TCCState *s, const char *name);

typedef struct {
    void *lib;
    fn_tcc_new tcc_new;
    fn_tcc_delete tcc_delete;
    fn_tcc_set_lib_path tcc_set_lib_path;
    fn_tcc_set_output_type tcc_set_output_type;
    fn_tcc_add_symbol tcc_add_symbol;
    fn_tcc_compile_string tcc_compile_string;
    fn_tcc_relocate tcc_relocate;
    fn_tcc_get_symbol tcc_get_symbol;
    const char *lib_path;
} LinTccDyn;

static inline int lin_tcc_dyn_load(LinTccDyn *dyn) {
    if (!dyn) return 0;
    memset(dyn, 0, sizeof(*dyn));

    const char *candidates[] = {
        getenv("LIN_TCC_LIB"),
        "/tmp/tinycc/libtcc.so",
        "./libtcc.so",
        "libtcc.so.1",
        "libtcc.so",
        "/usr/local/lib/libtcc.so",
        "/usr/lib/libtcc.so"
    };
    size_t n_cands = sizeof(candidates) / sizeof(candidates[0]);

    for (size_t i = 0; i < n_cands; i++) {
        const char *path = candidates[i];
        if (!path) continue;
        dyn->lib = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (dyn->lib) {
            dyn->lib_path = path;
            break;
        }
    }

    if (!dyn->lib) return 0;

    dyn->tcc_new = (fn_tcc_new)dlsym(dyn->lib, "tcc_new");
    dyn->tcc_delete = (fn_tcc_delete)dlsym(dyn->lib, "tcc_delete");
    dyn->tcc_set_lib_path = (fn_tcc_set_lib_path)dlsym(dyn->lib, "tcc_set_lib_path");
    dyn->tcc_set_output_type = (fn_tcc_set_output_type)dlsym(dyn->lib, "tcc_set_output_type");
    dyn->tcc_add_symbol = (fn_tcc_add_symbol)dlsym(dyn->lib, "tcc_add_symbol");
    dyn->tcc_compile_string = (fn_tcc_compile_string)dlsym(dyn->lib, "tcc_compile_string");
    dyn->tcc_relocate = (fn_tcc_relocate)dlsym(dyn->lib, "tcc_relocate");
    dyn->tcc_get_symbol = (fn_tcc_get_symbol)dlsym(dyn->lib, "tcc_get_symbol");

    if (!dyn->tcc_new || !dyn->tcc_delete || !dyn->tcc_set_output_type ||
        !dyn->tcc_compile_string || !dyn->tcc_relocate || !dyn->tcc_get_symbol) {
        dlclose(dyn->lib);
        memset(dyn, 0, sizeof(*dyn));
        return 0;
    }
    return 1;
}

static inline void lin_tcc_dyn_unload(LinTccDyn *dyn) {
    if (dyn && dyn->lib) {
        dlclose(dyn->lib);
        memset(dyn, 0, sizeof(*dyn));
    }
}

#endif /* LIN_TCC_DYN_H */

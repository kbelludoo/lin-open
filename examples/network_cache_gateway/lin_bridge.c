/*
 * lin_bridge.c — Persistent In-Memory JIT Bridge for LIN Network Cache Service
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <dlfcn.h>

#include "../../transpile/c/lin_c0_front.h"
#include "../../transpile/c/tool/lin_c0_jit.h"
#include "../../transpile/c/tool/lin_tcc_dyn.h"

typedef int64_t (*LinJitFn)(const int64_t *args);

typedef struct {
    C0Arena *arena;
    VmModule *mod;
    LinTccDyn dyn;
    TCCState *tcc_state;
    LinJitFn fn_compute;
    LinJitFn fn_eval;
    double compile_ms;
    uint64_t call_count;
    double total_exec_ns;
    int is_initialized;
} LinBridge;

static LinBridge g_bridge = {0};

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

int lin_bridge_init(const char *lin_file_path) {
    if (g_bridge.is_initialized) return 1;

    FILE *f = fopen(lin_file_path, "rb");
    if (!f) return -1;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *src = (char *)malloc(sz + 1);
    if (!src) { fclose(f); return -2; }
    fread(src, 1, sz, f);
    src[sz] = '\0';
    fclose(f);

    double t0 = get_time_sec();
    g_bridge.arena = c0_arena_new();
    if (!g_bridge.arena) { free(src); return -3; }

    g_bridge.mod = c0_build(g_bridge.arena, src, (size_t)sz);
    free(src);
    if (!g_bridge.mod) return -4;

    char *c11_code = c0_jit_emit_c11(g_bridge.mod);
    if (!c11_code) return -5;

    if (!lin_tcc_dyn_load(&g_bridge.dyn)) {
        free(c11_code);
        return -6;
    }

    g_bridge.tcc_state = g_bridge.dyn.tcc_new();
    if (!g_bridge.tcc_state) {
        free(c11_code);
        lin_tcc_dyn_unload(&g_bridge.dyn);
        return -7;
    }

    const char *env_tcc_dir = getenv("LIN_TCC_DIR");
    if (env_tcc_dir) {
        g_bridge.dyn.tcc_set_lib_path(g_bridge.tcc_state, env_tcc_dir);
    } else if (access("/tmp/tinycc/libtcc1.a", 0) == 0) {
        g_bridge.dyn.tcc_set_lib_path(g_bridge.tcc_state, "/tmp/tinycc");
    } else if (access("./libtcc1.a", 0) == 0) {
        g_bridge.dyn.tcc_set_lib_path(g_bridge.tcc_state, ".");
    }

    g_bridge.dyn.tcc_set_output_type(g_bridge.tcc_state, TCC_OUTPUT_MEMORY);
    if (g_bridge.dyn.tcc_compile_string(g_bridge.tcc_state, c11_code) < 0) {
        free(c11_code);
        g_bridge.dyn.tcc_delete(g_bridge.tcc_state);
        lin_tcc_dyn_unload(&g_bridge.dyn);
        return -8;
    }
    free(c11_code);

    if (g_bridge.dyn.tcc_relocate(g_bridge.tcc_state) < 0) {
        g_bridge.dyn.tcc_delete(g_bridge.tcc_state);
        lin_tcc_dyn_unload(&g_bridge.dyn);
        return -9;
    }

    g_bridge.fn_compute = (LinJitFn)g_bridge.dyn.tcc_get_symbol(g_bridge.tcc_state, "lin_fn_siphash24_compute");
    g_bridge.fn_eval = (LinJitFn)g_bridge.dyn.tcc_get_symbol(g_bridge.tcc_state, "lin_fn_siphash24_eval_vector");
    if (!g_bridge.fn_eval) {
        g_bridge.dyn.tcc_delete(g_bridge.tcc_state);
        lin_tcc_dyn_unload(&g_bridge.dyn);
        return -10;
    }

    double t1 = get_time_sec();
    g_bridge.compile_ms = (t1 - t0) * 1000.0;
    g_bridge.is_initialized = 1;
    g_bridge.call_count = 0;
    g_bridge.total_exec_ns = 0;
    return 0;
}

int64_t lin_bridge_hash(int64_t in_len, int64_t k0, int64_t k1) {
    if (!g_bridge.is_initialized || !g_bridge.fn_compute) return 0;
    int64_t args[3] = {in_len, k0, k1};
    double t0 = get_time_sec();
    int64_t ret = g_bridge.fn_compute(args);
    double t1 = get_time_sec();
    g_bridge.call_count++;
    g_bridge.total_exec_ns += (t1 - t0) * 1e9;
    return ret;
}

int64_t lin_bridge_eval(int64_t len) {
    if (!g_bridge.is_initialized || !g_bridge.fn_eval) return 0;
    int64_t args[1] = {len};
    double t0 = get_time_sec();
    int64_t ret = g_bridge.fn_eval(args);
    double t1 = get_time_sec();
    g_bridge.call_count++;
    g_bridge.total_exec_ns += (t1 - t0) * 1e9;
    return ret;
}

double lin_bridge_get_compile_ms(void) {
    return g_bridge.compile_ms;
}

uint64_t lin_bridge_get_call_count(void) {
    return g_bridge.call_count;
}

double lin_bridge_get_avg_exec_ns(void) {
    if (g_bridge.call_count == 0) return 0.0;
    return g_bridge.total_exec_ns / (double)g_bridge.call_count;
}

void lin_bridge_cleanup(void) {
    if (!g_bridge.is_initialized) return;
    if (g_bridge.tcc_state) g_bridge.dyn.tcc_delete(g_bridge.tcc_state);
    lin_tcc_dyn_unload(&g_bridge.dyn);
    memset(&g_bridge, 0, sizeof(g_bridge));
}

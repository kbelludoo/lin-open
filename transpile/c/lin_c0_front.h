/*
 * lin_c0_front.h — public surface of the Compiler 0 front-end (host C11).
 *
 * What this is: a C11 port of the LIN-source front-end of the Stage0 Zig
 * compiler, so that `.lin` text can be compiled and executed WITHOUT Zig.
 *
 * Ported, function for function, from compiler/lin.zig:
 *
 *   parse_fn_type_infos  lin.zig:5287   -> c0_parse_fn_infos
 *   vmTokenize           lin.zig:5678   -> c0_tokenize
 *   VmComp               lin.zig:5733   -> C0Comp + c0_expr/c0_stmt/...
 *   vmBuild              lin.zig:6296   -> c0_build
 *   vmSigEligible        lin.zig:6275   -> c0_sig_eligible
 *   vmArrLenOf           lin.zig:6262   -> c0_arr_len_of
 *   vmResolveDeps        lin.zig:6284   -> c0_resolve_deps
 *
 * The interpreter it feeds is the already-audited `vm_exec`
 * (transpile/c/lin_c/lin_vm.c, port of vmExecWithSp). The base subset remains
 * BIT-IDENTICAL to the Zig Stage0. This C11 frontend additionally accepts
 * C-like `for (init; cond; step)` and integer division; those extensions have
 * dedicated tests and intentionally do not claim parity with the frozen
 * Stage0 source-compiler rejection set. Published goldens remain the oracle.
 *
 * Enabled by amendment R6 (AGENTS.md@1.4.4): HOST_RUNTIME_MINIMO_C11_PERMITIDO,
 * limited to transpile/c/{lin_c,tool,test}. Zero new Zig files (R1).
 *
 * Memory: the front-end allocates (unlike the VM, which stays heap-free).
 * Everything lives in one arena owned by the caller and released in one call,
 * so the tool is sanitizer-clean (test/verify_c0.sh runs it under ASan+UBSan).
 */
#ifndef LIN_C0_FRONT_H
#define LIN_C0_FRONT_H

#include "lin_vm.h"

/* Opaque bump arena (single malloc'd block, grown with realloc). */
typedef struct C0Arena C0Arena;

C0Arena *c0_arena_new(void);
void     c0_arena_free(C0Arena *a);
void    *c0_arena_alloc(C0Arena *a, size_t n);      /* 8-byte aligned, zeroed */
char    *c0_arena_strdup_n(C0Arena *a, const char *s, size_t n);

/* One parsed `!name(params) -> ret { body }` declaration. All strings alias
 * either the source buffer or the arena (NUL-terminated copies). */
typedef struct {
    const char *name;
    const char *type_name;
} C0Param;

typedef struct {
    const char *name;
    C0Param    *params;
    size_t      nparams;
    const char *return_type;
    const char *body;          /* text between the outer braces (aliasing) */
    size_t      body_len;
    size_t      line;
} C0FnInfo;

/* parse_fn_type_infos (lin.zig:5287). `*out_n` receives the count. */
const C0FnInfo *c0_parse_fn_infos(C0Arena *a, const char *src, size_t len,
                                  size_t *out_n);

/* vmBuild (lin.zig:6296): source text -> executable VmModule.
 * Never fails: per-function rejection is recorded in fns[i].reject, exactly
 * like the Zig. Returns NULL only on arena exhaustion. */
VmModule *c0_build(C0Arena *a, const char *src, size_t len);

/* Experimental research profile: same front-end as c0_build but the parser is
 * additionally allowed to emit OP_SHL/OP_SHR/OP_USHR. Division and modulo are
 * already enabled by the default C11 frontend. */
VmModule *c0_build_full(C0Arena *a, const char *src, size_t len);

/* LINBC1 image encoder (docs/LINBC1_FORMAT.rulel §2/§3, profile 1).
 * Refuses (returns NULL, sets *err) when any function is not ok or when a
 * loader invariant of §3 would be violated — fail-closed, never a partial
 * image. The emitted bytes are deterministic: same module -> same bytes. */
uint8_t *c0_image_encode(C0Arena *a, const VmModule *mod, size_t *out_len,
                         const char **err);

/* Number of opcodes of the ISA (VM_OPCODE_COUNT in the Zig). */
#define C0_OPCODE_COUNT 33

#endif /* LIN_C0_FRONT_H */

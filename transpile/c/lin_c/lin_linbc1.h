/*
 * lin_linbc1.h — LINBC1 image loader (fail-closed), per docs/LINBC1_FORMAT.rulel.
 *
 * Enabled by amendment R6 (AGENTS.md@1.4.4). Loader code counts toward the C11
 * host TCB budget (target ≤ 2 500 lines total — V1 measures).
 *
 * Fail-closed contract (spec §3/§5): any malformed field, out-of-range index,
 * unknown opcode/abi/profile, length mismatch, trailing bytes or bad self-hash
 * ⇒ LIN_BC1_ERR_* and NOTHING executes; `out` contents are only meaningful on
 * LIN_BC1_OK. No allocation inside the loader — everything lands in
 * caller-owned storage (heap-free ethos).
 */
#ifndef LIN_C_LINBC1_H
#define LIN_C_LINBC1_H

#include "lin_vm.h"

/* Limits of THIS loader (V1). They are loader bounds, not spec ceilings: a
 * conforming host may accept more; exceeding these is a plain deterministic
 * rejection, never undefined behaviour. */
#define LIN_BC1_MAX_FNS        64
#define LIN_BC1_MAX_INS_TOTAL  16384
#define LIN_BC1_MAX_STR_BYTES  4096
#define LIN_BC1_MAX_REGIONS    64
#define LIN_BC1_C0_MAX_CELLS   (1u << 20)   /* 8 MiB of i64 cells, profile C0 */
#define LIN_BC1_MAX_LOCALS     64           /* VM_MAX_LOCALS (ISA §6)          */

typedef enum {
    LIN_BC1_OK = 0,
    LIN_BC1_ERR_SHORT,        /* truncated / impossible length          */
    LIN_BC1_ERR_MAGIC,        /* "LINBC1" missing                       */
    LIN_BC1_ERR_VERSION,      /* format_version != 1                    */
    LIN_BC1_ERR_PROFILE,      /* profile not in {1,2}                   */
    LIN_BC1_ERR_FLAGS,        /* reserved flags != 0                    */
    LIN_BC1_ERR_COUNT,        /* section count exceeds loader bounds    */
    LIN_BC1_ERR_SECTION,      /* section walk overrun / malformed field */
    LIN_BC1_ERR_FN,           /* nparams/nlocals/arr invariants broken  */
    LIN_BC1_ERR_OPCODE,       /* opcode ordinal > 32                    */
    LIN_BC1_ERR_JUMP,         /* jump target outsizes the function      */
    LIN_BC1_ERR_CALL,         /* call target outside the module         */
    LIN_BC1_ERR_LOCAL,        /* local-index operand out of range       */
    LIN_BC1_ERR_REGION,       /* region rules violated (profile/ceiling)*/
    LIN_BC1_ERR_ABI,          /* abi_id outside HOST-ABI-1 table 0..8   */
    LIN_BC1_ERR_TRAILING,     /* bytes after self_hash                  */
    LIN_BC1_ERR_SELFHASH,     /* linbc1:img: digest mismatch            */
} LinBc1Err;

const char *lin_bc1_err_name(LinBc1Err e);

/* Caller-owned materialization. Strings in VmFn.name point INTO the image
 * (aliasing — the image buffer must outlive the module); names are not
 * NUL-terminated there, so valid lengths live in name_len[]. */
typedef struct {
    VmModule  mod;                                     /* ready for vm_exec */
    VmFn      fns[LIN_BC1_MAX_FNS];
    VmIns     ins[LIN_BC1_MAX_INS_TOTAL];
    uint16_t  arrn_dense[LIN_BC1_MAX_FNS * LIN_BC1_MAX_LOCALS];
    uint16_t  name_len[LIN_BC1_MAX_FNS];
    uint8_t   profile;                                 /* 1 = LINVM-1, 2 = C0 */
    uint32_t  n_regions;
    uint32_t  region_cells[LIN_BC1_MAX_REGIONS];
    uint8_t   abis[9];                                 /* bitmask: abi 0..8   */
    uint8_t   img_sha256[32];                          /* == tail on OK       */
    size_t    img_len;
} LinBc1Vm;

/* Parse + validate + verify self-hash (domain "linbc1:img:"). */
LinBc1Err lin_bc1_load(const uint8_t *img, size_t len, LinBc1Vm *out);

/* Exact-name lookup (pool-length aware). -1 if absent. */
int lin_bc1_find_fn(const LinBc1Vm *m, const char *name);

/* Display fold of a 32-byte digest: 8 big-endian u32 words folded as
 * f = f·2^32 + w (w zero-extended), modulo 2^64, returned as i64. Lets tests
 * cross-compare digests across hosts as one scalar. */
int64_t lin_bc1_fold_digest(const uint8_t digest[32]);

#endif /* LIN_C_LINBC1_H */

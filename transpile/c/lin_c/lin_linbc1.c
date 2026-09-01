/* lin_linbc1.c — fail-closed LINBC1 loader. Spec: docs/LINBC1_FORMAT.rulel. */
#include "lin_linbc1.h"
#include "lin_sha256.h"

static const char *const BC1_ERR_NAMES[] = {
    "ok", "short", "magic", "version", "profile", "flags", "count",
    "section", "fn", "opcode", "jump", "call", "local", "region", "abi",
    "trailing", "selfhash",
};

const char *lin_bc1_err_name(LinBc1Err e) {
    if (e < 0 || e > LIN_BC1_ERR_SELFHASH) return "unknown";
    return BC1_ERR_NAMES[e];
}

typedef struct { const uint8_t *p; size_t len, at; } Cur;

static int rd_u8(Cur *c, uint32_t *v) {
    if (c->at + 1 > c->len) return 0;
    *v = c->p[c->at]; c->at += 1; return 1;
}
static int rd_u16(Cur *c, uint32_t *v) {
    if (c->at + 2 > c->len) return 0;
    *v = (uint32_t)c->p[c->at] | ((uint32_t)c->p[c->at + 1] << 8);
    c->at += 2; return 1;
}
static int rd_u32(Cur *c, uint32_t *v) {
    if (c->at + 4 > c->len) return 0;
    *v = (uint32_t)c->p[c->at] | ((uint32_t)c->p[c->at + 1] << 8)
       | ((uint32_t)c->p[c->at + 2] << 16) | ((uint32_t)c->p[c->at + 3] << 24);
    c->at += 4; return 1;
}
static int rd_i64(Cur *c, int64_t *v) {
    uint64_t r = 0; int k;
    if (c->at + 8 > c->len) return 0;
    for (k = 0; k < 8; k++) r |= (uint64_t)c->p[c->at + k] << (8 * k);
    c->at += 8; *v = (int64_t)r; return 1;
}

int64_t lin_bc1_fold_digest(const uint8_t d[32]) {
    uint64_t f = 0;
    for (int i = 0; i < 8; i++) {
        uint32_t w = ((uint32_t)d[4*i] << 24) | ((uint32_t)d[4*i+1] << 16)
                   | ((uint32_t)d[4*i+2] << 8) | (uint32_t)d[4*i+3];
        f = f * 4294967296ull + (uint64_t)w;
    }
    return (int64_t)f;
}

LinBc1Err lin_bc1_load(const uint8_t *img, size_t len, LinBc1Vm *out) {
    static const uint8_t DOM[] = "linbc1:img:";
    uint32_t v, n_strings, n_fns, n_regions, n_abis;
    /* string pool views: index → (offset,len); cap = 4 per fn worst case */
    uint32_t s_off[LIN_BC1_MAX_FNS * 4], s_len[LIN_BC1_MAX_FNS * 4];
    const uint32_t s_cap = LIN_BC1_MAX_FNS * 4;
    size_t ins_total = 0, str_bytes = 0;
    uint8_t digest[32];
    LinSha256 h;
    Cur c;

    if (!img || !out) return LIN_BC1_ERR_SECTION;
    if (len < 25 + 32) return LIN_BC1_ERR_SHORT;
    if (memcmp(img, "LINBC1", 6) != 0) return LIN_BC1_ERR_MAGIC;

    c.p = img; c.len = len - 32; c.at = 6;   /* body excludes the hash tail */
    if (!rd_u8(&c, &v) || v != 1) return LIN_BC1_ERR_VERSION;
    if (!rd_u8(&c, &v)) return LIN_BC1_ERR_SECTION;
    if (v != 1 && v != 2) return LIN_BC1_ERR_PROFILE;
    out->profile = (uint8_t)v;
    if (!rd_u8(&c, &v) || v != 0) return LIN_BC1_ERR_FLAGS;
    if (!rd_u32(&c, &n_strings)) return LIN_BC1_ERR_SHORT;
    if (!rd_u32(&c, &n_fns))     return LIN_BC1_ERR_SHORT;
    if (!rd_u32(&c, &n_regions)) return LIN_BC1_ERR_SHORT;
    if (!rd_u32(&c, &n_abis))    return LIN_BC1_ERR_SHORT;
    if (n_strings > s_cap || n_fns > LIN_BC1_MAX_FNS ||
        n_regions > LIN_BC1_MAX_REGIONS || n_abis > 9)
        return LIN_BC1_ERR_COUNT;

    /* string pool: { len u32 ; bytes } */
    for (uint32_t i = 0; i < n_strings; i++) {
        uint32_t sl;
        if (!rd_u32(&c, &sl)) return LIN_BC1_ERR_SECTION;
        if (c.at + sl > c.len) return LIN_BC1_ERR_SHORT;
        if (str_bytes + sl > LIN_BC1_MAX_STR_BYTES) return LIN_BC1_ERR_COUNT;
        s_off[i] = (uint32_t)c.at; s_len[i] = sl;
        c.at += sl; str_bytes += sl;
    }

    /* regions: profile 1 declares none; C0 cells are counted and capped */
    if (out->profile == 1 && n_regions != 0) return LIN_BC1_ERR_REGION;
    {
        uint64_t total_cells = 0;
        out->n_regions = n_regions;
        for (uint32_t i = 0; i < n_regions; i++) {
            uint32_t rid, cells;
            if (!rd_u32(&c, &rid)) return LIN_BC1_ERR_SECTION;
            if (!rd_u32(&c, &cells)) return LIN_BC1_ERR_SECTION;
            if (rid != i) return LIN_BC1_ERR_REGION;   /* canonical order */
            total_cells += cells;
            if (total_cells > LIN_BC1_C0_MAX_CELLS) return LIN_BC1_ERR_REGION;
            out->region_cells[i] = cells;
        }
    }

    /* abi table: every id must be in HOST-ABI-1 (0..8) */
    memset(out->abis, 0, sizeof(out->abis));
    for (uint32_t i = 0; i < n_abis; i++) {
        uint32_t id;
        if (!rd_u8(&c, &id)) return LIN_BC1_ERR_SECTION;
        if (id > 8) return LIN_BC1_ERR_ABI;
        out->abis[id] = 1;
    }

    /* functions */
    out->mod.fns = out->fns;
    out->mod.fns_len = n_fns;
    for (uint32_t fi = 0; fi < n_fns; fi++) {
        uint32_t name_idx, code_len, nparams, nlocals, n_arrs;
        uint16_t *dense = &out->arrn_dense[fi * LIN_BC1_MAX_LOCALS];
        VmFn *f = &out->fns[fi];

        if (!rd_u32(&c, &name_idx)) return LIN_BC1_ERR_SECTION;
        if (name_idx >= n_strings) return LIN_BC1_ERR_FN;
        if (!rd_u8(&c, &nparams)) return LIN_BC1_ERR_SECTION;
        if (!rd_u8(&c, &nlocals)) return LIN_BC1_ERR_SECTION;
        if (!rd_u8(&c, &n_arrs))  return LIN_BC1_ERR_SECTION;
        if (!rd_u32(&c, &code_len)) return LIN_BC1_ERR_SECTION;
        if (code_len == 0) return LIN_BC1_ERR_FN;
        if (nparams > nlocals || nlocals > LIN_BC1_MAX_LOCALS) return LIN_BC1_ERR_FN;
        if (n_arrs > 8) return LIN_BC1_ERR_FN;                 /* ISA §6 */

        f->name = (const char *)(img + s_off[name_idx]);      /* aliasing */
        out->name_len[fi] = (uint16_t)s_len[name_idx];
        f->nparams = nparams;
        f->nlocals = nlocals;
        f->sig_ok = 1; f->ok = 1; f->reject = "";

        /* array literal descriptors (local_idx u8, len u16), dense by local */
        memset(dense, 0, LIN_BC1_MAX_LOCALS * sizeof(uint16_t));
        for (uint32_t k = 0; k < n_arrs; k++) {
            uint32_t li, alen;
            if (!rd_u8(&c, &li)) return LIN_BC1_ERR_SECTION;
            if (!rd_u16(&c, &alen)) return LIN_BC1_ERR_SECTION;
            if (li >= nlocals) return LIN_BC1_ERR_LOCAL;
            if (alen == 0 || alen > 256) return LIN_BC1_ERR_FN;  /* ISA §6 */
            if (dense[li] != 0) return LIN_BC1_ERR_FN;           /* duplicates */
            dense[li] = (uint16_t)alen;
        }
        f->arr_n = dense;
        f->arr_n_len = nlocals;

        f->code = &out->ins[ins_total];
        f->code_len = code_len;
        if (ins_total + code_len > LIN_BC1_MAX_INS_TOTAL) return LIN_BC1_ERR_COUNT;
        for (uint32_t pc = 0; pc < code_len; pc++) {
            uint32_t op; int64_t a;
            if (!rd_u8(&c, &op)) return LIN_BC1_ERR_SECTION;
            if (!rd_i64(&c, &a))  return LIN_BC1_ERR_SECTION;
            if (op > 32) return LIN_BC1_ERR_OPCODE;
            switch (op) {   /* static intent checks (spec §3 invariants) */
            case 23: case 24: case 25: case 26:              /* jumps */
                if (a < 0 || (uint64_t)a >= code_len) return LIN_BC1_ERR_JUMP;
                break;
            case 28:                                          /* call */
                if (a < 0 || (uint64_t)a >= n_fns) return LIN_BC1_ERR_CALL;
                break;
            case 1: case 2: case 30: case 31: case 32:        /* local-indexed */
                if (a < 0 || (uint64_t)a >= nlocals) return LIN_BC1_ERR_LOCAL;
                break;
            default: break;
            }
            out->ins[ins_total + pc].op = (VmOp)op;
            out->ins[ins_total + pc].a  = a;
        }
        ins_total += code_len;
    }

    /* nothing between last function and self-hash */
    if (c.at != c.len) return LIN_BC1_ERR_TRAILING;
    if (c.len + 32 != len) return LIN_BC1_ERR_SHORT;

    /* self-hash, domain linbc1:img: over the whole body */
    lin_sha256_init(&h);
    lin_sha256_update(&h, DOM, sizeof(DOM) - 1);
    lin_sha256_update(&h, img, c.len);
    lin_sha256_final(&h, digest);
    if (memcmp(digest, img + len - 32, 32) != 0) return LIN_BC1_ERR_SELFHASH;

    memcpy(out->img_sha256, digest, 32);
    out->img_len = len;
    return LIN_BC1_OK;
}

int lin_bc1_find_fn(const LinBc1Vm *m, const char *name) {
    size_t want = strlen(name);
    for (size_t i = 0; i < m->mod.fns_len; i++) {
        if ((size_t)m->name_len[i] == want &&
            memcmp(m->mod.fns[i].name, name, want) == 0)
            return (int)i;
    }
    return -1;
}

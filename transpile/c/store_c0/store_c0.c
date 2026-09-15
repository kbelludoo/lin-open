#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "store_c0.h"
#include "../lin_c/lin_sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>

/* --- Little Endian Encoders / Decoders --- */

static inline void write_u16_le(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
}

static inline void write_u32_le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
    p[2] = (uint8_t)((v >> 16) & 0xFF);
    p[3] = (uint8_t)((v >> 24) & 0xFF);
}

static inline void write_u64_le(uint8_t *p, uint64_t v) {
    for (int i = 0; i < 8; i++) {
        p[i] = (uint8_t)((v >> (i * 8)) & 0xFF);
    }
}

static inline uint16_t read_u16_le(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static inline uint32_t read_u32_le(const uint8_t *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static inline uint64_t read_u64_le(const uint8_t *p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; i++) {
        v |= ((uint64_t)p[i] << (i * 8));
    }
    return v;
}

/* --- Lexicographical Key Comparison --- */

static int key_compare(const uint8_t *k1, uint16_t len1, const uint8_t *k2, uint16_t len2) {
    size_t min_len = (len1 < len2) ? len1 : len2;
    int cmp = memcmp(k1, k2, min_len);
    if (cmp != 0) return cmp;
    if (len1 < len2) return -1;
    if (len1 > len2) return 1;
    return 0;
}

/* --- In-Memory Sorted Table (Memtable) --- */

typedef struct {
    uint8_t  *key;
    uint16_t  key_len;
    uint8_t  *val;
    uint32_t  val_len;
} MemEntry;

typedef struct {
    MemEntry *entries;
    size_t    count;
    size_t    capacity;
} MemTable;

static void memtable_init(MemTable *mt) {
    mt->entries = NULL;
    mt->count = 0;
    mt->capacity = 0;
}

static void memtable_free(MemTable *mt) {
    if (mt->entries) {
        for (size_t i = 0; i < mt->count; i++) {
            free(mt->entries[i].key);
            free(mt->entries[i].val);
        }
        free(mt->entries);
    }
    memtable_init(mt);
}

/* Returns index where key is located, or insertion point if not found */
static size_t memtable_find(const MemTable *mt, const uint8_t *key, uint16_t key_len, bool *found) {
    size_t low = 0;
    size_t high = mt->count;
    while (low < high) {
        size_t mid = low + (high - low) / 2;
        int cmp = key_compare(mt->entries[mid].key, mt->entries[mid].key_len, key, key_len);
        if (cmp == 0) {
            *found = true;
            return mid;
        } else if (cmp < 0) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }
    *found = false;
    return low;
}

static StoreResult memtable_put(MemTable *mt, const uint8_t *key, uint16_t key_len,
                                const uint8_t *val, uint32_t val_len) {
    bool found = false;
    size_t idx = memtable_find(mt, key, key_len, &found);

    if (found) {
        /* Update existing entry */
        uint8_t *new_val = malloc(val_len ? val_len : 1);
        if (!new_val) return STORE_ERR_NOMEM;
        if (val_len > 0) memcpy(new_val, val, val_len);

        free(mt->entries[idx].val);
        mt->entries[idx].val = new_val;
        mt->entries[idx].val_len = val_len;
        return STORE_OK;
    }

    /* Grow capacity if necessary */
    if (mt->count >= mt->capacity) {
        size_t new_cap = mt->capacity == 0 ? 16 : mt->capacity * 2;
        MemEntry *new_entries = realloc(mt->entries, new_cap * sizeof(MemEntry));
        if (!new_entries) return STORE_ERR_NOMEM;
        mt->entries = new_entries;
        mt->capacity = new_cap;
    }

    uint8_t *kcopy = malloc(key_len);
    if (!kcopy) return STORE_ERR_NOMEM;
    memcpy(kcopy, key, key_len);

    uint8_t *vcopy = malloc(val_len ? val_len : 1);
    if (!vcopy) {
        free(kcopy);
        return STORE_ERR_NOMEM;
    }
    if (val_len > 0) memcpy(vcopy, val, val_len);

    /* Shift right to maintain sorted order */
    if (idx < mt->count) {
        memmove(&mt->entries[idx + 1], &mt->entries[idx], (mt->count - idx) * sizeof(MemEntry));
    }

    mt->entries[idx].key = kcopy;
    mt->entries[idx].key_len = key_len;
    mt->entries[idx].val = vcopy;
    mt->entries[idx].val_len = val_len;
    mt->count++;

    return STORE_OK;
}

static StoreResult memtable_del(MemTable *mt, const uint8_t *key, uint16_t key_len) {
    bool found = false;
    size_t idx = memtable_find(mt, key, key_len, &found);
    if (!found) {
        return STORE_ERR_NOT_FOUND;
    }

    free(mt->entries[idx].key);
    free(mt->entries[idx].val);

    if (idx + 1 < mt->count) {
        memmove(&mt->entries[idx], &mt->entries[idx + 1], (mt->count - idx - 1) * sizeof(MemEntry));
    }
    mt->count--;
    return STORE_OK;
}

/* --- Internal Store Structure --- */

typedef struct {
    uint8_t   op;
    uint8_t  *key;
    uint16_t  key_len;
    uint8_t  *val;
    uint32_t  val_len;
} StagedOp;

struct Store {
    char        dir_path[800];
    int         lock_fd;
    int         wal_fd;
    MemTable    memtable;
    StagedOp   *staged_ops;
    size_t      staged_count;
    size_t      staged_capacity;
    uint64_t    frame_count;
    int64_t     wal_size;
};

/* --- Internal Helpers for WAL & Recovery --- */

static StoreResult write_wal_header(int fd) {
    StoreWalHeader hdr;
    memcpy(hdr.magic, STORE_MAGIC_WAL, 4);
    hdr.version = 1;
    hdr.page_size = STORE_PAGE_SIZE;
    hdr.reserved = 0;

    uint8_t raw[12];
    memcpy(raw, hdr.magic, 4);
    write_u16_le(raw + 4, hdr.version);
    write_u32_le(raw + 6, hdr.page_size);
    write_u16_le(raw + 10, hdr.reserved);

    if (pwrite(fd, raw, 12, 0) != 12) {
        return STORE_ERR_IO;
    }
    if (fdatasync(fd) != 0 && fsync(fd) != 0) {
        return STORE_ERR_IO;
    }
    return STORE_OK;
}

static StoreResult recover_and_replay_wal(Store *s) {
    struct stat st;
    if (fstat(s->wal_fd, &st) != 0) {
        return STORE_ERR_IO;
    }

    if (st.st_size == 0) {
        StoreResult res = write_wal_header(s->wal_fd);
        if (res != STORE_OK) return res;
        s->wal_size = 12;
        s->frame_count = 0;
        return STORE_OK;
    }

    if (st.st_size > 0 && st.st_size < 12) {
        /* Existing WAL with partial header is corrupt: fail-closed */
        return STORE_ERR_CORRUPT;
    }

    uint8_t hdr_raw[12];
    if (pread(s->wal_fd, hdr_raw, 12, 0) != 12) {
        return STORE_ERR_IO;
    }

    if (memcmp(hdr_raw, STORE_MAGIC_WAL, 4) != 0) {
        return STORE_ERR_CORRUPT;
    }
    uint16_t ver = read_u16_le(hdr_raw + 4);
    uint32_t page = read_u32_le(hdr_raw + 6);
    uint16_t reserved = read_u16_le(hdr_raw + 10);
    if (ver != STORE_VER_1 || page != STORE_PAGE_SIZE || reserved != 0) {
        return STORE_ERR_CORRUPT;
    }

    off_t offset = 12;
    uint64_t valid_frames = 0;

    while (offset < st.st_size) {
        off_t frame_start = offset;

        /* Check if we can read frame_len (4 bytes LE) */
        uint8_t len_bytes[4];
        ssize_t n = pread(s->wal_fd, len_bytes, 4, offset);
        if (n == 0) {
            /* Clean EOF */
            break;
        }
        if (n < 4) {
            /* Short read on frame_len: torn write at tail */
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        uint32_t frame_len = read_u32_le(len_bytes);
        /* Minimum frame: 1(op) + 2(klen) + 4(vlen) + 0 + 0 + 32(sum) = 39 bytes */
        if (frame_len < 39 || frame_len > (STORE_MAX_KEY_LEN + STORE_MAX_VAL_LEN + 39)) {
            /* Invalid length field: truncate tail */
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        offset += 4;

        /* Read the rest of the frame */
        uint8_t *frame_buf = malloc(frame_len);
        if (!frame_buf) return STORE_ERR_NOMEM;

        n = pread(s->wal_fd, frame_buf, frame_len, offset);
        if (n < (ssize_t)frame_len) {
            /* Short read on frame body: torn write at tail */
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        uint8_t op = frame_buf[0];
        uint16_t klen = read_u16_le(frame_buf + 1);
        uint32_t vlen = read_u32_le(frame_buf + 3);

        if ((uint32_t)(7 + klen + vlen + 32) != frame_len) {
            /* Frame internal fields do not match frame_len */
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        if (op != STORE_OP_PUT && op != STORE_OP_DEL) {
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        /* Strict caps mirroring the commit path: such a frame could never
         * have been produced by a valid store_put/store_del, so the tail
         * from here on is untrusted and must be truncated fail-closed. */
        if (klen == 0 || klen > STORE_MAX_KEY_LEN ||
            vlen > STORE_MAX_VAL_LEN) {
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }
        if (op == STORE_OP_DEL && vlen != 0) {
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        const uint8_t *key = frame_buf + 7;
        const uint8_t *val = frame_buf + 7 + klen;
        const uint8_t *stored_sum = frame_buf + 7 + klen + vlen;

        /* Verify SHA-256 over (op || klen || vlen || key || val) */
        LinSha256 ctx;
        lin_sha256_init(&ctx);
        lin_sha256_update(&ctx, frame_buf, 7 + klen + vlen);
        uint8_t calc_sum[32];
        lin_sha256_final(&ctx, calc_sum);

        if (memcmp(calc_sum, stored_sum, 32) != 0) {
            /* Bit-flip or corrupt sum in tail: truncate */
            free(frame_buf);
            if (ftruncate(s->wal_fd, frame_start) != 0) return STORE_ERR_IO;
            offset = frame_start;
            break;
        }

        /* Frame is cryptographically verified! Replay into memtable */
        if (op == STORE_OP_PUT) {
            StoreResult put_res = memtable_put(&s->memtable, key, klen, val, vlen);
            if (put_res != STORE_OK) {
                free(frame_buf);
                return put_res;
            }
        } else if (op == STORE_OP_DEL) {
            memtable_del(&s->memtable, key, klen);
        }

        free(frame_buf);
        offset += frame_len;
        valid_frames++;
    }

    s->wal_size = offset;
    s->frame_count = valid_frames;
    (void)fsync(s->wal_fd);

    return STORE_OK;
}

static StoreResult verify_checkpoint_on_open(Store *s) {
    char chk_path[1024];
    snprintf(chk_path, sizeof(chk_path), "%s/store.chk", s->dir_path);

    int chk_fd = open(chk_path, O_RDONLY);
    if (chk_fd < 0) {
        if (errno == ENOENT) {
            return STORE_OK; /* No checkpoint is valid on new/un-checkpointed stores */
        }
        return STORE_ERR_IO;
    }

    struct stat st;
    if (fstat(chk_fd, &st) != 0 || st.st_size != 80) {
        close(chk_fd);
        /* Corrupted/partial checkpoint: ignore fail-closed to WAL */
        return STORE_OK;
    }

    uint8_t raw[80];
    if (read(chk_fd, raw, 80) != 80) {
        close(chk_fd);
        return STORE_OK;
    }
    close(chk_fd);

    if (memcmp(raw, STORE_MAGIC_CHK, 6) != 0) {
        return STORE_OK; /* Ignore invalid checkpoint */
    }

    uint16_t ver = read_u16_le(raw + 6);
    if (ver != 1) return STORE_OK;

    uint64_t chk_frames = read_u64_le(raw + 8);
    const uint8_t *chk_root = raw + 16;
    const uint8_t *chk_sum = raw + 48;

    /* Verify checksum over fields: magic(6) + ver(2) + frames(8) + root(32) = 48 bytes */
    uint8_t calc_sum[32];
    lin_sha256(raw, 48, calc_sum);
    if (memcmp(calc_sum, chk_sum, 32) != 0) {
        /* Checksum invalid: ignore checkpoint */
        return STORE_OK;
    }

    /* .checkpoint_stale: if checkpoint.frames > valid_frames_in_WAL: IGNORADO */
    if (chk_frames > s->frame_count) {
        return STORE_OK;
    }

    /* If checkpoint.frames == s->frame_count, verify root matches exactly */
    if (chk_frames == s->frame_count) {
        uint8_t current_root[32];
        StoreResult rres = store_get_merkle_root(s, current_root);
        if (rres != STORE_OK) return rres;

        if (memcmp(current_root, chk_root, 32) != 0) {
            /* Divergence: reject fail-closed! */
            return STORE_ERR_CHK_MISMATCH;
        }
    }

    return STORE_OK;
}

/* --- Public API Implementation --- */

StoreResult store_open(const char *dir_path, Store **out_store) {
    if (!dir_path || !out_store) return STORE_ERR_INVALID_ARG;

    /* Ensure directory exists */
    struct stat st;
    if (stat(dir_path, &st) != 0) {
        if (mkdir(dir_path, 0755) != 0 && errno != EEXIST) {
            return STORE_ERR_IO;
        }
    }

    Store *s = calloc(1, sizeof(Store));
    if (!s) return STORE_ERR_NOMEM;
    strncpy(s->dir_path, dir_path, sizeof(s->dir_path) - 1);
    memtable_init(&s->memtable);

    /* 1. Acquire exclusive lock */
    char lock_path[1024];
    snprintf(lock_path, sizeof(lock_path), "%s/store.lock", dir_path);
    s->lock_fd = open(lock_path, O_RDWR | O_CREAT, 0644);
    if (s->lock_fd < 0) {
        free(s);
        return STORE_ERR_IO;
    }
    if (flock(s->lock_fd, LOCK_EX | LOCK_NB) != 0) {
        close(s->lock_fd);
        free(s);
        return STORE_ERR_LOCKED;
    }

    /* 2. Open or create WAL */
    char wal_path[1024];
    snprintf(wal_path, sizeof(wal_path), "%s/store.wal", dir_path);
    s->wal_fd = open(wal_path, O_RDWR | O_CREAT, 0644);
    if (s->wal_fd < 0) {
        flock(s->lock_fd, LOCK_UN);
        close(s->lock_fd);
        free(s);
        return STORE_ERR_IO;
    }

    /* 3. Replay and recover WAL */
    StoreResult res = recover_and_replay_wal(s);
    if (res != STORE_OK) {
        close(s->wal_fd);
        flock(s->lock_fd, LOCK_UN);
        close(s->lock_fd);
        memtable_free(&s->memtable);
        free(s);
        return res;
    }

    /* 4. Validate checkpoint */
    res = verify_checkpoint_on_open(s);
    if (res != STORE_OK) {
        close(s->wal_fd);
        flock(s->lock_fd, LOCK_UN);
        close(s->lock_fd);
        memtable_free(&s->memtable);
        free(s);
        return res;
    }

    *out_store = s;
    return STORE_OK;
}

StoreResult store_put(Store *s, const uint8_t *key, uint16_t key_len,
                      const uint8_t *val, uint32_t val_len) {
    if (!s || !key || key_len == 0) return STORE_ERR_INVALID_ARG;
    if (key_len > STORE_MAX_KEY_LEN) return STORE_ERR_LIMIT_KEY;
    if (val_len > STORE_MAX_VAL_LEN) return STORE_ERR_LIMIT_VAL;
    if (!val && val_len > 0) return STORE_ERR_INVALID_ARG;

    /* Grow the staging queue BEFORE touching the memtable so a NOMEM
     * never leaves the memtable ahead of the staging queue. */
    if (s->staged_count >= s->staged_capacity) {
        size_t new_cap = s->staged_capacity == 0 ? 16 : s->staged_capacity * 2;
        StagedOp *new_ops = realloc(s->staged_ops, new_cap * sizeof(StagedOp));
        if (!new_ops) return STORE_ERR_NOMEM;
        s->staged_ops = new_ops;
        s->staged_capacity = new_cap;
    }

    /* Allocate staging copies next; NOMEM here changes neither layer. */
    uint8_t *kcopy = malloc(key_len);
    if (!kcopy) return STORE_ERR_NOMEM;

    uint8_t *vcopy = malloc(val_len ? val_len : 1);
    if (!vcopy) {
        free(kcopy);
        return STORE_ERR_NOMEM;
    }
    memcpy(kcopy, key, key_len);
    if (val_len > 0) memcpy(vcopy, val, val_len);

    /* Apply to memtable for read-your-own-writes; on NOMEM here the
     * staging copies are released and neither layer changes. */
    StoreResult mres = memtable_put(&s->memtable, key, key_len, val, val_len);
    if (mres != STORE_OK) {
        free(kcopy);
        free(vcopy);
        return mres;
    }

    s->staged_ops[s->staged_count].op = STORE_OP_PUT;
    s->staged_ops[s->staged_count].key = kcopy;
    s->staged_ops[s->staged_count].key_len = key_len;
    s->staged_ops[s->staged_count].val = vcopy;
    s->staged_ops[s->staged_count].val_len = val_len;
    s->staged_count++;

    return STORE_OK;
}

StoreResult store_del(Store *s, const uint8_t *key, uint16_t key_len) {
    if (!s || !key || key_len == 0) return STORE_ERR_INVALID_ARG;
    if (key_len > STORE_MAX_KEY_LEN) return STORE_ERR_LIMIT_KEY;

    /* Peek before mutating so NOMEM below never leaves the memtable
     * ahead of the staging queue. */
    {
        bool found = false;
        (void)memtable_find(&s->memtable, key, key_len, &found);
        if (!found) return STORE_ERR_NOT_FOUND;
    }

    if (s->staged_count >= s->staged_capacity) {
        size_t new_cap = s->staged_capacity == 0 ? 16 : s->staged_capacity * 2;
        StagedOp *new_ops = realloc(s->staged_ops, new_cap * sizeof(StagedOp));
        if (!new_ops) return STORE_ERR_NOMEM;
        s->staged_ops = new_ops;
        s->staged_capacity = new_cap;
    }

    uint8_t *kcopy = malloc(key_len);
    if (!kcopy) return STORE_ERR_NOMEM;
    memcpy(kcopy, key, key_len);

    StoreResult mres = memtable_del(&s->memtable, key, key_len);
    if (mres != STORE_OK) {
        free(kcopy);
        return mres;
    }

    s->staged_ops[s->staged_count].op = STORE_OP_DEL;
    s->staged_ops[s->staged_count].key = kcopy;
    s->staged_ops[s->staged_count].key_len = key_len;
    s->staged_ops[s->staged_count].val = NULL;
    s->staged_ops[s->staged_count].val_len = 0;
    s->staged_count++;

    return STORE_OK;
}

StoreResult store_commit(Store *s) {
    if (!s) return STORE_ERR_INVALID_ARG;
    if (s->staged_count == 0) return STORE_OK;

    /* Check limits: compute total bytes needed */
    uint64_t total_bytes = 0;
    for (size_t i = 0; i < s->staged_count; i++) {
        uint32_t flen = 1 + 2 + 4 + s->staged_ops[i].key_len + s->staged_ops[i].val_len + 32;
        total_bytes += (4 + flen);
    }

    if (s->wal_size + (int64_t)total_bytes > STORE_MAX_WAL_SIZE) {
        return STORE_ERR_LIMIT_WAL;
    }

    /* Write all staged frames to WAL. Two-phase: no per-frame free and
     * no wal_size/frame_count mutation until the frame hits the file, so
     * an I/O or NOMEM mid-batch leaves the staging queue intact for a
     * retry at the same offsets (never dangling pointers, never a half-
     * counted batch). */
    int64_t write_cursor = s->wal_size;
    size_t i = 0;
    for (; i < s->staged_count; i++) {
        StagedOp *sop = &s->staged_ops[i];
        uint32_t frame_len = 1 + 2 + 4 + sop->key_len + sop->val_len + 32;

        uint8_t *buf = malloc(4 + frame_len);
        if (!buf) return STORE_ERR_NOMEM;

        write_u32_le(buf, frame_len);
        buf[4] = sop->op;
        write_u16_le(buf + 5, sop->key_len);
        write_u32_le(buf + 7, sop->val_len);
        memcpy(buf + 11, sop->key, sop->key_len);
        if (sop->val_len > 0) memcpy(buf + 11 + sop->key_len, sop->val, sop->val_len);

        uint8_t sum[32];
        LinSha256 ctx;
        lin_sha256_init(&ctx);
        lin_sha256_update(&ctx, buf + 4, 7 + sop->key_len + sop->val_len);
        lin_sha256_final(&ctx, sum);

        memcpy(buf + 11 + sop->key_len + sop->val_len, sum, 32);

        ssize_t written = pwrite(s->wal_fd, buf, 4 + frame_len, write_cursor);
        free(buf);

        if (written != (ssize_t)(4 + frame_len)) {
            return STORE_ERR_IO;
        }

        write_cursor += (4 + frame_len);
    }

    /* All frames durable in the file image; publish cursors, then fsync. */
    s->wal_size = write_cursor;
    s->frame_count += (uint64_t)s->staged_count;

    for (size_t j = 0; j < s->staged_count; j++) {
        free(s->staged_ops[j].key);
        free(s->staged_ops[j].val);
    }

    /* fsync per commit for absolute durability guarantee */
    if (fdatasync(s->wal_fd) != 0 && fsync(s->wal_fd) != 0) {
        return STORE_ERR_IO;
    }

    free(s->staged_ops);
    s->staged_ops = NULL;
    s->staged_count = 0;
    s->staged_capacity = 0;

    return STORE_OK;
}

StoreResult store_get(Store *s, const uint8_t *key, uint16_t key_len,
                      uint8_t *out_val, uint32_t cap, uint32_t *out_vlen) {
    if (!s || !key || key_len == 0 || !out_vlen) {
        return STORE_ERR_INVALID_ARG;
    }

    bool found = false;
    size_t idx = memtable_find(&s->memtable, key, key_len, &found);
    if (!found) {
        *out_vlen = 0;
        return STORE_ERR_NOT_FOUND;
    }

    *out_vlen = s->memtable.entries[idx].val_len;
    if (cap < s->memtable.entries[idx].val_len) {
        return STORE_ERR_LIMIT_VAL;
    }

    if (out_val && s->memtable.entries[idx].val_len > 0) {
        memcpy(out_val, s->memtable.entries[idx].val, s->memtable.entries[idx].val_len);
    }
    return STORE_OK;
}

StoreResult store_get_merkle_root(Store *s, uint8_t out_root[32]) {
    if (!s || !out_root) return STORE_ERR_INVALID_ARG;

    size_t n = s->memtable.count;
    if (n == 0) {
        /* .merkle_empty=SHA-256("STR_EMPTY_v1") */
        lin_sha256("STR_EMPTY_v1", 12, out_root);
        return STORE_OK;
    }

    /* Compute leaf hashes:
     * leaf = SHA-256(0x00 || key_len u16LE || key || val_len u32LE || val)
     */
    uint8_t (*level_hashes)[32] = malloc(n * 32);
    if (!level_hashes) return STORE_ERR_NOMEM;

    for (size_t i = 0; i < n; i++) {
        MemEntry *e = &s->memtable.entries[i];
        LinSha256 ctx;
        lin_sha256_init(&ctx);

        uint8_t prefix = 0x00;
        lin_sha256_update(&ctx, &prefix, 1);

        uint8_t klen_bytes[2];
        write_u16_le(klen_bytes, e->key_len);
        lin_sha256_update(&ctx, klen_bytes, 2);
        lin_sha256_update(&ctx, e->key, e->key_len);

        uint8_t vlen_bytes[4];
        write_u32_le(vlen_bytes, e->val_len);
        lin_sha256_update(&ctx, vlen_bytes, 4);
        if (e->val_len > 0) {
            lin_sha256_update(&ctx, e->val, e->val_len);
        }

        lin_sha256_final(&ctx, level_hashes[i]);
    }

    /* Level reduction with Bitcoin-style odd node duplication */
    size_t count = n;
    while (count > 1) {
        size_t next_count = (count + 1) / 2;
        uint8_t (*next_level)[32] = malloc(next_count * 32);
        if (!next_level) {
            free(level_hashes);
            return STORE_ERR_NOMEM;
        }

        for (size_t i = 0; i < count; i += 2) {
            size_t left_idx = i;
            size_t right_idx = (i + 1 < count) ? i + 1 : i; /* Duplicate last if odd */

            uint8_t parent_buf[65];
            parent_buf[0] = 0x01; /* Parent node prefix */
            memcpy(parent_buf + 1, level_hashes[left_idx], 32);
            memcpy(parent_buf + 33, level_hashes[right_idx], 32);

            lin_sha256(parent_buf, 65, next_level[i / 2]);
        }

        free(level_hashes);
        level_hashes = next_level;
        count = next_count;
    }

    memcpy(out_root, level_hashes[0], 32);
    free(level_hashes);
    return STORE_OK;
}

StoreResult store_checkpoint(Store *s) {
    if (!s) return STORE_ERR_INVALID_ARG;

    /* 1. fsync WAL */
    if (fdatasync(s->wal_fd) != 0 && fsync(s->wal_fd) != 0) {
        return STORE_ERR_IO;
    }

    /* 2. Compute canonical Merkle root */
    uint8_t root[32];
    StoreResult rres = store_get_merkle_root(s, root);
    if (rres != STORE_OK) return rres;

    /* 3. Build Checkpoint struct (80 bytes) */
    uint8_t chk_raw[80];
    memcpy(chk_raw, STORE_MAGIC_CHK, 6);
    write_u16_le(chk_raw + 6, 1);
    write_u64_le(chk_raw + 8, s->frame_count);
    memcpy(chk_raw + 16, root, 32);

    /* sum = SHA-256 over magic..root (48 bytes) */
    uint8_t sum[32];
    lin_sha256(chk_raw, 48, sum);
    memcpy(chk_raw + 48, sum, 32);

    /* 4. Write to temp file, fsync, atomic rename */
    char tmp_path[1024];
    char chk_path[1024];
    snprintf(tmp_path, sizeof(tmp_path), "%s/store.chk.tmp", s->dir_path);
    snprintf(chk_path, sizeof(chk_path), "%s/store.chk", s->dir_path);

    int tmp_fd = open(tmp_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (tmp_fd < 0) return STORE_ERR_IO;

    if (write(tmp_fd, chk_raw, 80) != 80) {
        close(tmp_fd);
        unlink(tmp_path);
        return STORE_ERR_IO;
    }

    if (fsync(tmp_fd) != 0) {
        close(tmp_fd);
        unlink(tmp_path);
        return STORE_ERR_IO;
    }
    close(tmp_fd);

    if (rename(tmp_path, chk_path) != 0) {
        unlink(tmp_path);
        return STORE_ERR_IO;
    }

    /* 5. Directory fsync to persist entry metadata */
    int dir_fd = open(s->dir_path, O_RDONLY | O_DIRECTORY);
    if (dir_fd >= 0) {
        (void)fsync(dir_fd);
        close(dir_fd);
    }

    return STORE_OK;
}

uint64_t store_get_frame_count(Store *s) {
    return s ? s->frame_count : 0;
}

size_t store_get_active_keys_count(Store *s) {
    return s ? s->memtable.count : 0;
}

int64_t store_get_wal_size(Store *s) {
    return s ? s->wal_size : 0;
}

StoreResult store_close(Store *s) {
    if (!s) return STORE_ERR_INVALID_ARG;

    if (s->wal_fd >= 0) {
        (void)fsync(s->wal_fd);
        close(s->wal_fd);
        s->wal_fd = -1;
    }

    if (s->lock_fd >= 0) {
        flock(s->lock_fd, LOCK_UN);
        close(s->lock_fd);
        s->lock_fd = -1;
    }

    /* Discard any uncommitted staged operations */
    if (s->staged_ops) {
        for (size_t i = 0; i < s->staged_count; i++) {
            free(s->staged_ops[i].key);
            free(s->staged_ops[i].val);
        }
        free(s->staged_ops);
        s->staged_ops = NULL;
    }

    memtable_free(&s->memtable);
    free(s);
    return STORE_OK;
}

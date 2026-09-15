#ifndef STORE_C0_H
#define STORE_C0_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define STORE_MAGIC_WAL         "STRW"
#define STORE_MAGIC_CHK         "STRCHK"
#define STORE_VER_1             1
#define STORE_PAGE_SIZE         4096

#define STORE_MAX_KEY_LEN       1024
#define STORE_MAX_VAL_LEN       (1024 * 1024)       /* 1 MiB */
#define STORE_MAX_WAL_SIZE      (1024 * 1024 * 1024)/* 1 GiB */

#define STORE_OP_PUT            1
#define STORE_OP_DEL            2

typedef enum {
    STORE_OK                = 0,
    STORE_ERR_INVALID_ARG   = -1,
    STORE_ERR_NOT_FOUND     = -2,
    STORE_ERR_LIMIT_KEY     = -3,
    STORE_ERR_LIMIT_VAL     = -4,
    STORE_ERR_LIMIT_WAL     = -5,
    STORE_ERR_IO            = -6,
    STORE_ERR_LOCKED        = -7,
    STORE_ERR_CORRUPT       = -8,
    STORE_ERR_CHK_MISMATCH  = -9,
    STORE_ERR_NOMEM         = -10
} StoreResult;

#pragma pack(push, 1)
typedef struct {
    char     magic[4];      /* "STRW" */
    uint16_t version;       /* 1 (LE) */
    uint32_t page_size;     /* 4096 (LE) */
    uint16_t reserved;      /* 0 */
} StoreWalHeader;

typedef struct {
    char     magic[6];      /* "STRCHK" */
    uint16_t version;       /* 1 (LE) */
    uint64_t frames;        /* Total committed frames */
    uint8_t  root[32];      /* Canonical Merkle root */
    uint8_t  sum[32];       /* SHA-256 over magic..root */
} StoreCheckpoint;
#pragma pack(pop)

/* Forward declaration of internal Store instance */
typedef struct Store Store;

/**
 * Open or create a store instance in the specified directory.
 * Acquires exclusive flock on the lockfile.
 * Replays valid WAL frames and verifies checkpoint.
 */
StoreResult store_open(const char *dir_path, Store **out_store);

/**
 * Stage a PUT operation into the memory table and staging log.
 * Does NOT persist to disk until store_commit() is called.
 */
StoreResult store_put(Store *s, const uint8_t *key, uint16_t key_len,
                      const uint8_t *val, uint32_t val_len);

/**
 * Stage a DEL operation into the memory table and staging log.
 * Does NOT persist to disk until store_commit() is called.
 */
StoreResult store_del(Store *s, const uint8_t *key, uint16_t key_len);

/**
 * Persists all staged PUT/DEL operations to the WAL and performs fsync.
 * Uncommitted operations are discarded on crash or close.
 */
StoreResult store_commit(Store *s);

/**
 * Look up a key in the memory table.
 * Caller provides out_val buffer with capacity cap.
 * Sets *out_vlen to actual value length.
 * If cap < actual length, returns STORE_ERR_LIMIT_VAL without copying.
 * If not found, returns STORE_ERR_NOT_FOUND.
 */
StoreResult store_get(Store *s, const uint8_t *key, uint16_t key_len,
                      uint8_t *out_val, uint32_t cap, uint32_t *out_vlen);

/**
 * Computes and returns the 32-byte canonical Merkle Root over all active keys.
 * Empty state returns SHA-256("STR_EMPTY_v1").
 */
StoreResult store_get_merkle_root(Store *s, uint8_t out_root[32]);

/**
 * Persists an atomic checkpoint to store.chk:
 * 1. fsync(wal_fd)
 * 2. write & fsync store.chk.tmp
 * 3. rename to store.chk
 * 4. fsync parent directory
 */
StoreResult store_checkpoint(Store *s);

/**
 * Returns statistics about the store instance.
 */
uint64_t store_get_frame_count(Store *s);
size_t   store_get_active_keys_count(Store *s);
int64_t  store_get_wal_size(Store *s);

/**
 * Closes the store instance, discards uncommitted staging, releases flock, and frees memory.
 */
StoreResult store_close(Store *s);

#ifdef __cplusplus
}
#endif

#endif /* STORE_C0_H */

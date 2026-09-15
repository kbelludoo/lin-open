#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "store_c0.h"
#include "../lin_c/lin_sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <assert.h>
#include <time.h>
#include <sys/stat.h>

#define COLOR_GREEN "\033[92m"
#define COLOR_RED   "\033[91m"
#define COLOR_BLUE  "\033[94m"
#define COLOR_RESET "\033[0m"

static void rm_rf(const char *path) {
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "rm -rf %s", path);
    (void)system(cmd);
}

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* 1. Golden Fixed Vectors (C vs Python Cross-Verification) */
static void test_golden_vectors(void) {
    printf("[1/9] Testing Golden Fixed Vectors & Merkle State Commitments... ");
    const char *dir = "test_data_golden";
    rm_rf(dir);

    Store *s = NULL;
    StoreResult res = store_open(dir, &s);
    assert(res == STORE_OK);

    /* Empty state root */
    uint8_t root_empty[32];
    res = store_get_merkle_root(s, root_empty);
    assert(res == STORE_OK);

    uint8_t expected_empty[32];
    lin_sha256("STR_EMPTY_v1", 12, expected_empty);
    assert(memcmp(root_empty, expected_empty, 32) == 0);

    /* Insert test entries: PUT stages in memtable */
    res = store_put(s, (const uint8_t*)"charlie", 7, (const uint8_t*)"val_300", 7);
    assert(res == STORE_OK);
    res = store_put(s, (const uint8_t*)"alice", 5, (const uint8_t*)"val_100", 7);
    assert(res == STORE_OK);
    res = store_put(s, (const uint8_t*)"eve", 3, (const uint8_t*)"val_500", 7);
    assert(res == STORE_OK);
    res = store_put(s, (const uint8_t*)"bob", 3, (const uint8_t*)"val_200", 7);
    assert(res == STORE_OK);

    /* COMMIT persists to WAL + fsync */
    res = store_commit(s);
    assert(res == STORE_OK);

    assert(store_get_active_keys_count(s) == 4);
    assert(store_get_frame_count(s) == 4);

    uint8_t root_4[32];
    res = store_get_merkle_root(s, root_4);
    assert(res == STORE_OK);

    char hex_4[65];
    lin_sha256_hex(root_4, hex_4);

    /* Save KVs to JSON and call Python oracle to verify bit-by-bit identity */
    FILE *fjson = fopen("test_data_golden/kvs.json", "w");
    assert(fjson != NULL);
    fprintf(fjson, "{\"alice\":\"val_100\",\"bob\":\"val_200\",\"charlie\":\"val_300\",\"eve\":\"val_500\"}\n");
    fclose(fjson);

    char cmd[512];
    snprintf(cmd, sizeof(cmd), "python3 oracle_store.py --root-of-kvs test_data_golden/kvs.json > test_data_golden/oracle_root.txt");
    int py_res = system(cmd);
    assert(py_res == 0);

    FILE *fpy = fopen("test_data_golden/oracle_root.txt", "r");
    assert(fpy != NULL);
    char py_hex[65] = {0};
    assert(fscanf(fpy, "%64s", py_hex) == 1);
    fclose(fpy);

    assert(strcmp(hex_4, py_hex) == 0);

    /* Test DEL + COMMIT and re-verification */
    res = store_del(s, (const uint8_t*)"bob", 3);
    assert(res == STORE_OK);
    res = store_commit(s);
    assert(res == STORE_OK);
    assert(store_get_active_keys_count(s) == 3);

    res = store_close(s);
    assert(res == STORE_OK);

    /* Re-verify WAL with Python oracle */
    snprintf(cmd, sizeof(cmd), "python3 oracle_store.py --verify-wal test_data_golden/store.wal > test_data_golden/oracle_wal.txt");
    py_res = system(cmd);
    assert(py_res == 0);

    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 2. Caller-Provided Buffer for store_get */
static void test_store_get_buffer(void) {
    printf("[2/9] Testing Caller-Provided Buffer (Zero-Malloc get)... ");
    const char *dir = "test_data_get";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"my_key", 6, (const uint8_t*)"secret_value_123", 16) == STORE_OK);
    assert(store_commit(s) == STORE_OK);

    /* Exact capacity */
    uint8_t buf[64];
    uint32_t out_len = 0;
    assert(store_get(s, (const uint8_t*)"my_key", 6, buf, sizeof(buf), &out_len) == STORE_OK);
    assert(out_len == 16);
    assert(memcmp(buf, "secret_value_123", 16) == 0);

    /* Too small capacity: must fail-closed with STORE_ERR_LIMIT_VAL */
    out_len = 0;
    assert(store_get(s, (const uint8_t*)"my_key", 6, buf, 10, &out_len) == STORE_ERR_LIMIT_VAL);
    assert(out_len == 16);

    /* Key not found */
    assert(store_get(s, (const uint8_t*)"nonexistent", 11, buf, sizeof(buf), &out_len) == STORE_ERR_NOT_FOUND);

    store_close(s);
    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 3. Uncommitted Staging Lost on Crash / Close */
static void test_uncommitted_lost(void) {
    printf("[3/9] Testing PUT Staging & Explicit Commit Semantics... ");
    const char *dir = "test_data_uncommitted";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);

    /* Commit key1 */
    assert(store_put(s, (const uint8_t*)"k1", 2, (const uint8_t*)"v1", 2) == STORE_OK);
    assert(store_commit(s) == STORE_OK);

    /* Stage key2 WITHOUT calling commit */
    assert(store_put(s, (const uint8_t*)"k2", 2, (const uint8_t*)"v2", 2) == STORE_OK);

    /* Close without commit: key2 is uncommitted and must vanish */
    store_close(s);

    /* Reopen: only k1 must exist */
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_get_active_keys_count(s) == 1);
    assert(store_get_frame_count(s) == 1);

    uint8_t buf[16];
    uint32_t out_len = 0;
    assert(store_get(s, (const uint8_t*)"k1", 2, buf, sizeof(buf), &out_len) == STORE_OK);
    assert(store_get(s, (const uint8_t*)"k2", 2, buf, sizeof(buf), &out_len) == STORE_ERR_NOT_FOUND);

    store_close(s);
    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 4. Corrupted WAL Header & Magic Rejection (Fail-Closed) */
static void test_corrupted_header(void) {
    printf("[4/9] Testing Corrupted Header & Bad Magic (Fail-Closed)... ");
    const char *dir = "test_data_corrupt_hdr";
    rm_rf(dir);
    mkdir(dir, 0755);

    /* Create WAL with bad magic */
    char wal_path[512];
    snprintf(wal_path, sizeof(wal_path), "%s/store.wal", dir);
    int fd = open(wal_path, O_WRONLY | O_CREAT, 0644);
    assert(write(fd, "BADM\x01\x00\x00\x10\x00\x00\x00\x00", 12) == 12);
    close(fd);

    Store *s = NULL;
    /* Must return STORE_ERR_CORRUPT, never treat as empty */
    assert(store_open(dir, &s) == STORE_ERR_CORRUPT);

    /* Create WAL with partial header < 12 bytes */
    fd = open(wal_path, O_WRONLY | O_TRUNC, 0644);
    assert(write(fd, "STRW\x01", 5) == 5);
    close(fd);

    assert(store_open(dir, &s) == STORE_ERR_CORRUPT);

    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 5. Stale Checkpoint Detection & Directory fsync */
static void test_checkpoint_stale_and_dir_fsync(void) {
    printf("[5/9] Testing Stale Checkpoint & Directory Metadata Sync... ");
    const char *dir = "test_data_chk";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"chk_key", 7, (const uint8_t*)"chk_val", 7) == STORE_OK);
    assert(store_commit(s) == STORE_OK);

    /* Create valid checkpoint (performs directory fsync after rename) */
    assert(store_checkpoint(s) == STORE_OK);
    store_close(s);

    /* Synthesize a fake checkpoint with frames = 9999 ahead of WAL */
    char chk_path[512];
    snprintf(chk_path, sizeof(chk_path), "%s/store.chk", dir);

    uint8_t fake_chk[80];
    memcpy(fake_chk, "STRCHK", 6);
    fake_chk[6] = 1; fake_chk[7] = 0; /* version 1 */
    uint64_t fake_frames = 9999;
    memcpy(fake_chk + 8, &fake_frames, 8);
    memset(fake_chk + 16, 0xAA, 32); /* fake root */
    lin_sha256(fake_chk, 48, fake_chk + 48);

    int cfd = open(chk_path, O_WRONLY | O_TRUNC);
    assert(write(cfd, fake_chk, 80) == 80);
    close(cfd);

    /* Reopen: checkpoint must be ignored since frames (9999) > WAL frames (1) */
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_get_frame_count(s) == 1);
    assert(store_get_active_keys_count(s) == 1);

    store_close(s);
    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 6. Idempotent Reopen */
static void test_idempotent_reopen(void) {
    printf("[6/9] Testing Idempotent Reopen (5 Cycles)... ");
    const char *dir = "test_data_reopen";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"user:001", 8, (const uint8_t*)"state_A", 7) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"user:002", 8, (const uint8_t*)"state_B", 7) == STORE_OK);
    assert(store_commit(s) == STORE_OK);

    uint8_t root_initial[32];
    assert(store_get_merkle_root(s, root_initial) == STORE_OK);
    store_close(s);

    for (int cycle = 0; cycle < 5; cycle++) {
        assert(store_open(dir, &s) == STORE_OK);
        uint8_t root_cycle[32];
        assert(store_get_merkle_root(s, root_cycle) == STORE_OK);
        assert(memcmp(root_initial, root_cycle, 32) == 0);
        store_close(s);
    }

    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 7. Hard caps: key/val limits + WAL accounting the 1 GiB gate relies on */
static void test_hard_caps(void) {
    printf("[7/9] Testing Hard Caps (key/val limits + WAL accounting)... ");
    const char *dir = "test_data_caps";
    rm_rf(dir);

    /* The 1 GiB fail-closed gate is a hard constant, not a promise. */
    assert(STORE_MAX_KEY_LEN == 1024);
    assert(STORE_MAX_VAL_LEN == 1024 * 1024);
    assert(STORE_MAX_WAL_SIZE == 1024 * 1024 * 1024);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_get_wal_size(s) == 12); /* header only */

    /* Oversized key must fail-closed before touching memtable/staging. */
    uint8_t big_key[1025];
    memset(big_key, 'K', sizeof(big_key));
    assert(store_put(s, big_key, 1025, (const uint8_t*)"v", 1) == STORE_ERR_LIMIT_KEY);
    assert(store_get_active_keys_count(s) == 0);

    /* Oversized value must fail-closed (1 MiB + 1). */
    uint32_t huge = (uint32_t)(1024 * 1024 + 1);
    uint8_t *big_val = malloc(huge);
    assert(big_val != NULL);
    memset(big_val, 'V', huge);
    assert(store_put(s, (const uint8_t*)"k", 1, big_val, huge) == STORE_ERR_LIMIT_VAL);
    free(big_val);
    assert(store_get_active_keys_count(s) == 0);

    /* Boundary keys/vals (exactly at cap) must be accepted + committed. */
    uint8_t max_key[1024];
    memset(max_key, 'M', sizeof(max_key));
    assert(store_put(s, max_key, 1024, (const uint8_t*)"ok", 2) == STORE_OK);
    assert(store_commit(s) == STORE_OK);
    /* Frame = 4 + (1+2+4+1024+2+32) = 1069 bytes; WAL = 12 + 1069. */
    assert(store_get_wal_size(s) == 12 + 1069);
    assert(store_get_frame_count(s) == 1);

    /* DEL on a missing key must not stage anything. */
    assert(store_del(s, (const uint8_t*)"nope", 4) == STORE_ERR_NOT_FOUND);
    assert(store_commit(s) == STORE_OK); /* no-op commit */
    assert(store_get_frame_count(s) == 1);

    store_close(s);
    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 8. Torn-write tail: partial frame bytes appended after a clean commit
 * must be truncated on reopen, replaying exactly the valid prefix. */
static void test_torn_write_tail(void) {
    printf("[8/9] Testing Torn-Write Tail Truncation (crash mid-frame)... ");
    const char *dir = "test_data_torn";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"t1", 2, (const uint8_t*)"v1", 2) == STORE_OK);
    assert(store_put(s, (const uint8_t*)"t2", 2, (const uint8_t*)"v2", 2) == STORE_OK);
    assert(store_commit(s) == STORE_OK);

    uint8_t root_before[32];
    assert(store_get_merkle_root(s, root_before) == STORE_OK);
    int64_t wal_clean = store_get_wal_size(s);
    /* Each frame here: 4 + (1+2+4+2+2+32) = 47 bytes; 12 + 2*47 = 106. */
    assert(wal_clean == 106);
    assert(store_get_frame_count(s) == 2);
    store_close(s);

    /* Simulate a crash mid-frame: append 10 garbage bytes to the WAL. */
    char wal_path[512];
    snprintf(wal_path, sizeof(wal_path), "%s/store.wal", dir);
    int fd = open(wal_path, O_WRONLY | O_APPEND);
    assert(fd >= 0);
    assert(write(fd, "\x2A\x00\x00\x00\x01\xFF\xFF\xFF\xFF\xFF", 10) == 10);
    close(fd);

    /* Reopen must truncate the tail and replay exactly the 2 valid frames. */
    assert(store_open(dir, &s) == STORE_OK);
    assert(store_get_frame_count(s) == 2);
    assert(store_get_active_keys_count(s) == 2);
    assert(store_get_wal_size(s) == wal_clean);
    uint8_t root_after[32];
    assert(store_get_merkle_root(s, root_after) == STORE_OK);
    assert(memcmp(root_before, root_after, 32) == 0);

    uint8_t buf[16];
    uint32_t out_len = 0;
    assert(store_get(s, (const uint8_t*)"t1", 2, buf, sizeof(buf), &out_len) == STORE_OK);
    assert(out_len == 2 && memcmp(buf, "v1", 2) == 0);
    assert(store_get(s, (const uint8_t*)"t2", 2, buf, sizeof(buf), &out_len) == STORE_OK);
    assert(out_len == 2 && memcmp(buf, "v2", 2) == 0);

    /* Bit-flip in the last frame's checksum must drop exactly that frame. */
    store_close(s);
    fd = open(wal_path, O_RDWR);
    assert(fd >= 0);
    /* Last byte of the file is the final checksum byte: flip bit0. */
    uint8_t last = 0;
    assert(pread(fd, &last, 1, wal_clean - 1) == 1);
    last ^= 0x01;
    assert(pwrite(fd, &last, 1, wal_clean - 1) == 1);
    close(fd);

    assert(store_open(dir, &s) == STORE_OK);
    assert(store_get_frame_count(s) == 1);
    assert(store_get_active_keys_count(s) == 1);
    assert(store_get(s, (const uint8_t*)"t2", 2, buf, sizeof(buf), &out_len) == STORE_ERR_NOT_FOUND);
    assert(store_get(s, (const uint8_t*)"t1", 2, buf, sizeof(buf), &out_len) == STORE_OK);

    store_close(s);
    rm_rf(dir);
    printf(COLOR_GREEN "PASS" COLOR_RESET "\n");
}

/* 9. Real fsync IOPS Measurement (EACH iteration commits through fsync) */
static void test_fsync_benchmark(void) {
    printf("[9/9] Benchmarking Real fsync IOPS Durability... \n");
    const char *dir = "test_data_iops";
    rm_rf(dir);

    Store *s = NULL;
    assert(store_open(dir, &s) == STORE_OK);

    const int N = 100;
    double t0 = get_time_sec();

    for (int i = 0; i < N; i++) {
        char k[32], v[32];
        snprintf(k, sizeof(k), "k_%06d", i);
        snprintf(v, sizeof(v), "v_%06d", i);
        StoreResult res = store_put(s, (const uint8_t*)k, strlen(k), (const uint8_t*)v, strlen(v));
        assert(res == STORE_OK);
        res = store_commit(s);
        assert(res == STORE_OK);
    }

    double t1 = get_time_sec();
    double elapsed = t1 - t0;
    double iops = (double)N / elapsed;

    printf("      -> %d commits fsync'd in %.3f s | " COLOR_BLUE "%.1f commits/sec (IOPS)" COLOR_RESET "\n",
           N, elapsed, iops);

    store_close(s);
    rm_rf(dir);
    printf("      " COLOR_GREEN "PASS" COLOR_RESET "\n");
}

int main(void) {
    printf("==============================================================\n");
    printf(" Native STORE (store_c0) Contract Invariant Test Suite \n");
    printf("==============================================================\n");

    test_golden_vectors();
    test_store_get_buffer();
    test_uncommitted_lost();
    test_corrupted_header();
    test_checkpoint_stale_and_dir_fsync();
    test_idempotent_reopen();
    test_hard_caps();
    test_torn_write_tail();
    test_fsync_benchmark();

    printf("==============================================================\n");
    printf(COLOR_GREEN " ALL CONTRACT INVARIANTS SATISFIED WITH ZERO DEFECTS\n" COLOR_RESET);
    printf("==============================================================\n");
    return 0;
}

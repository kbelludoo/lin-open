/* test_region.c — unit tests for the LIN-ETH-1 host region boundary. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "../lin_c/lin_region.h"

static int pass_count;
static int fail_count;

#define CHECK(condition, label) do { \
    if (condition) { \
        pass_count++; \
    } else { \
        fail_count++; \
        fprintf(stderr, "FAIL: %s (line %d)\n", label, __LINE__); \
    } \
} while (0)

static void test_empty_and_zero_byte(void) {
    int64_t cells[2];
    LinRegionSet set;
    const LinRegion *region = NULL;
    uint8_t byte = 0xff;

    lin_region_set_init(&set);
    CHECK(lin_region_bind(&set, 0, cells, 2, 0) == LIN_REGION_OK,
          "bind empty region");
    CHECK(lin_region_get(&set, 0, &region) == LIN_REGION_OK,
          "get empty region");
    CHECK(lin_region_write_bytes((LinRegion *)region, NULL, 0) == LIN_REGION_OK,
          "write empty payload");
    CHECK(lin_region_load_byte(region, 0, &byte) == LIN_REGION_ERR_TRUNCATED,
          "empty payload rejects byte zero");

    {
        const uint8_t zero = 0;
        CHECK(lin_region_write_bytes((LinRegion *)region, &zero, 1) == LIN_REGION_OK,
              "write one zero byte");
        CHECK(lin_region_load_byte(region, 0, &byte) == LIN_REGION_OK,
              "zero byte is readable");
        CHECK(byte == 0, "zero byte is not confused with error");
    }
}

static void test_little_endian_and_bounds(void) {
    int64_t cells[2];
    LinRegionSet set;
    const LinRegion *region = NULL;
    uint8_t payload[9] = {0x00, 0x01, 0x7f, 0x80, 0xfe, 0xff, 0x55, 0xaa, 0x42};
    uint8_t byte = 0;
    int64_t cell = 0;

    lin_region_set_init(&set);
    CHECK(lin_region_bind(&set, 0, cells, 2, 0) == LIN_REGION_OK,
          "bind two-cell region");
    region = &set.regions[0];
    CHECK(lin_region_write_bytes(&set.regions[0], payload, sizeof(payload)) == LIN_REGION_OK,
          "write nine bytes");
    CHECK(lin_region_load_cell(region, 0, &cell) == LIN_REGION_OK,
          "load first cell");
    CHECK((uint64_t)cell == UINT64_C(0xaa55fffe807f0100),
          "first cell little-endian");
    CHECK(lin_region_load_byte(region, 8, &byte) == LIN_REGION_OK && byte == 0x42,
          "last payload byte");
    CHECK(lin_region_load_byte(region, 9, &byte) == LIN_REGION_ERR_TRUNCATED,
          "byte after payload is truncated");
    CHECK(lin_region_load_byte(region, 16, &byte) == LIN_REGION_ERR_BOUNDS,
          "byte at physical capacity is out of bounds");
    CHECK(lin_region_check_range(region, 2, 7) == LIN_REGION_OK,
          "valid range");
    CHECK(lin_region_check_range(region, 8, 2) == LIN_REGION_ERR_TRUNCATED,
          "range past payload");
}

static void test_invalid_bindings(void) {
    int64_t cells[1];
    LinRegionSet set;

    lin_region_set_init(&set);
    CHECK(lin_region_bind(&set, 1, cells, 1, 0) == LIN_REGION_ERR_ABI,
          "non-canonical first region id");
    CHECK(lin_region_bind(&set, 0, cells, LIN_REGION_MAX_CELLS + 1u, 0) == LIN_REGION_ERR_BOUNDS,
          "capacity ceiling");
    CHECK(lin_region_bind(&set, 0, cells, 1, 9) == LIN_REGION_ERR_TRUNCATED,
          "payload above capacity");
    CHECK(lin_region_bind(&set, 0, cells, 1, LIN_ETH_MAX_INPUT_BYTES + 1u) == LIN_REGION_ERR_TRUNCATED,
          "payload above one-cell capacity is rejected first");
    CHECK(lin_region_get(&set, -1, NULL) == LIN_REGION_ERR_INVALID,
          "negative region id with null output");
}

int main(void) {
    test_empty_and_zero_byte();
    test_little_endian_and_bounds();
    test_invalid_bindings();

    printf("region tests: %d passed, %d failed\n", pass_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}

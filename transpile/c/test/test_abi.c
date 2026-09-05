/* test_abi.c — HOST-ABI-2 region intrinsic tests. */
#include <stdio.h>
#include <stdint.h>

#include "../lin_c/lin_abi.h"

static int pass_count;
static int fail_count;

#define CHECK(condition, label) do { \
    if (condition) { \
        pass_count++; \
    } else { \
        fail_count++; \
        fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, label); \
    } \
} while (0)

static LinAbiResult call(
    const LinAbiContext *ctx,
    uint8_t abi_id,
    int64_t *stack,
    size_t *sp
) {
    return lin_abi2_dispatch(ctx, abi_id, stack, sp);
}

static void test_declaration_and_descriptors(void) {
    int64_t cells[2];
    LinRegionSet regions;
    LinAbiContext ctx;

    lin_region_set_init(&regions);
    CHECK(lin_region_bind(&regions, 0, cells, 2, 0) == LIN_REGION_OK,
          "bind region");
    lin_abi2_context_init(&ctx, &regions);

    CHECK(lin_abi2_desc(9) != NULL, "descriptor 9 exists");
    CHECK(lin_abi2_desc(10) != NULL, "descriptor 10 exists");
    CHECK(lin_abi2_desc(11) != NULL, "descriptor 11 exists");
    CHECK(lin_abi2_desc(8) == NULL, "legacy id is not ABI-2 region id");
    CHECK(lin_abi2_enable(&ctx, 9) == LIN_REGION_OK, "enable id 9");
    CHECK(lin_abi2_enable(&ctx, 10) == LIN_REGION_OK, "enable id 10");
    CHECK(lin_abi2_enable(&ctx, 11) == LIN_REGION_OK, "enable id 11");
    CHECK(lin_abi2_enable(&ctx, 8) == LIN_REGION_ERR_ABI,
          "reject unknown id");
    CHECK(lin_abi2_is_enabled(&ctx, 9), "id 9 enabled");
    CHECK(!lin_abi2_is_enabled(&ctx, 8), "id 8 disabled");
}

static void test_capacity_and_stack_preservation(void) {
    int64_t cells[2];
    LinRegionSet regions;
    LinAbiContext ctx;
    int64_t stack[3] = {0, 0, 0};
    size_t sp = 1;
    LinAbiResult result;

    lin_region_set_init(&regions);
    lin_region_bind(&regions, 0, cells, 2, 0);
    lin_abi2_context_init(&ctx, &regions);
    lin_abi2_enable(&ctx, LIN_ABI2_REGION_CAPACITY);

    stack[0] = 0;
    result = call(&ctx, LIN_ABI2_REGION_CAPACITY, stack, &sp);
    CHECK(result.vm_error == LIN_OK && result.region_error == LIN_REGION_OK,
          "capacity success");
    CHECK(result.value == 16 && sp == 0, "capacity is 16 bytes");

    sp = 0;
    result = call(&ctx, LIN_ABI2_REGION_CAPACITY, stack, &sp);
    CHECK(result.vm_error == LIN_ERR_VM_STACK_UNDERFLOW && sp == 0,
          "underflow preserves stack pointer");

    sp = 1;
    stack[0] = -1;
    result = call(&ctx, LIN_ABI2_REGION_CAPACITY, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_INVALID && sp == 1,
          "invalid region preserves arguments");
}

static void test_check_range_statuses(void) {
    int64_t cells[2];
    uint8_t payload[3] = {0x00, 0x11, 0x22};
    LinRegionSet regions;
    LinAbiContext ctx;
    int64_t stack[3];
    size_t sp;
    LinAbiResult result;

    lin_region_set_init(&regions);
    lin_region_bind(&regions, 0, cells, 2, 0);
    lin_region_write_bytes(&regions.regions[0], payload, sizeof(payload));
    lin_abi2_context_init(&ctx, &regions);
    lin_abi2_enable(&ctx, LIN_ABI2_REGION_CHECK_RANGE);

    stack[0] = 0; stack[1] = 1; stack[2] = 2; sp = 3;
    result = call(&ctx, LIN_ABI2_REGION_CHECK_RANGE, stack, &sp);
    CHECK(result.value == LIN_REGION_OK && result.region_error == LIN_REGION_OK && sp == 0,
          "valid range returns zero");

    stack[0] = 0; stack[1] = 2; stack[2] = 2; sp = 3;
    result = call(&ctx, LIN_ABI2_REGION_CHECK_RANGE, stack, &sp);
    CHECK(result.value == LIN_REGION_ERR_TRUNCATED &&
          result.region_error == LIN_REGION_ERR_TRUNCATED && sp == 0,
          "truncated range returns status");

    stack[0] = 0; stack[1] = -1; stack[2] = 1; sp = 3;
    result = call(&ctx, LIN_ABI2_REGION_CHECK_RANGE, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_INVALID && sp == 3,
          "negative offset rejected without consuming stack");
}

static void test_load_byte_and_fail_closed(void) {
    int64_t cells[2];
    uint8_t payload[2] = {0x00, 0xab};
    LinRegionSet regions;
    LinAbiContext ctx;
    int64_t stack[2];
    size_t sp;
    LinAbiResult result;

    lin_region_set_init(&regions);
    lin_region_bind(&regions, 0, cells, 2, 0);
    lin_region_write_bytes(&regions.regions[0], payload, sizeof(payload));
    lin_abi2_context_init(&ctx, &regions);
    lin_abi2_enable(&ctx, LIN_ABI2_REGION_LOAD_BYTE);

    stack[0] = 0; stack[1] = 0; sp = 2;
    result = call(&ctx, LIN_ABI2_REGION_LOAD_BYTE, stack, &sp);
    CHECK(result.vm_error == LIN_OK && result.region_error == LIN_REGION_OK,
          "load zero byte succeeds");
    CHECK(result.value == 0 && sp == 0, "zero byte is data, not error");

    stack[0] = 0; stack[1] = 1; sp = 2;
    result = call(&ctx, LIN_ABI2_REGION_LOAD_BYTE, stack, &sp);
    CHECK(result.value == 0xab && sp == 0, "load nonzero byte");

    stack[0] = 0; stack[1] = 2; sp = 2;
    result = call(&ctx, LIN_ABI2_REGION_LOAD_BYTE, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_TRUNCATED && sp == 2,
          "load after payload fails closed");

    stack[0] = 0; stack[1] = -1; sp = 2;
    result = call(&ctx, LIN_ABI2_REGION_LOAD_BYTE, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_INVALID && sp == 2,
          "negative byte index fails closed");
}

static void test_undeclared_and_missing_context(void) {
    int64_t cells[1];
    LinRegionSet regions;
    LinAbiContext ctx;
    int64_t stack[1] = {0};
    size_t sp = 1;
    LinAbiResult result;

    lin_region_set_init(&regions);
    lin_region_bind(&regions, 0, cells, 1, 0);
    lin_abi2_context_init(&ctx, &regions);

    result = call(&ctx, LIN_ABI2_REGION_CAPACITY, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_ABI && sp == 1,
          "undeclared intrinsic rejected");

    lin_abi2_enable(&ctx, LIN_ABI2_REGION_CAPACITY);
    ctx.regions = NULL;
    result = call(&ctx, LIN_ABI2_REGION_CAPACITY, stack, &sp);
    CHECK(result.region_error == LIN_REGION_ERR_INVALID && sp == 1,
          "missing region context rejected");
}

int main(void) {
    test_declaration_and_descriptors();
    test_capacity_and_stack_preservation();
    test_check_range_statuses();
    test_load_byte_and_fail_closed();
    test_undeclared_and_missing_context();

    printf("ABI-2 tests: %d passed, %d failed\n", pass_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}

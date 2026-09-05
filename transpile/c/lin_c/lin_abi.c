/*
 * lin_abi.c — HOST-ABI-2 region intrinsic dispatcher.
 */
#include "lin_abi.h"

static const LinAbiDesc ABI2_DESCRIPTORS[] = {
    { LIN_ABI2_REGION_CAPACITY,    1u, 1u },
    { LIN_ABI2_REGION_CHECK_RANGE, 3u, 1u },
    { LIN_ABI2_REGION_LOAD_BYTE,   2u, 1u }
};

static LinAbiResult abi_result_ok(int64_t value) {
    LinAbiResult result;
    result.vm_error = LIN_OK;
    result.region_error = LIN_REGION_OK;
    result.value = value;
    return result;
}

static LinAbiResult abi_result_vm_error(LinErr error) {
    LinAbiResult result;
    result.vm_error = error;
    result.region_error = LIN_REGION_OK;
    result.value = 0;
    return result;
}

static LinAbiResult abi_result_region_error(LinRegionErr error) {
    LinAbiResult result;
    result.vm_error = LIN_OK;
    result.region_error = error;
    result.value = 0;
    return result;
}

void lin_abi2_context_init(
    LinAbiContext *ctx,
    const LinRegionSet *regions
) {
    if (ctx == NULL) return;

    ctx->regions = regions;
    ctx->abi_version = LIN_HOST_ABI_2;
    for (size_t i = 0; i < LIN_ABI2_MAX_DECLARED; i++) {
        ctx->declared[i] = 0;
    }
}

LinRegionErr lin_abi2_enable(
    LinAbiContext *ctx,
    uint8_t abi_id
) {
    if (ctx == NULL) return LIN_REGION_ERR_INVALID;
    if (ctx->abi_version != LIN_HOST_ABI_2) {
        return LIN_REGION_ERR_ABI;
    }
    if (lin_abi2_desc(abi_id) == NULL) {
        return LIN_REGION_ERR_ABI;
    }

    ctx->declared[abi_id] = 1u;
    return LIN_REGION_OK;
}

const LinAbiDesc *lin_abi2_desc(uint8_t abi_id) {
    for (size_t i = 0;
         i < sizeof ABI2_DESCRIPTORS / sizeof ABI2_DESCRIPTORS[0];
         i++) {
        if (ABI2_DESCRIPTORS[i].abi_id == abi_id) {
            return &ABI2_DESCRIPTORS[i];
        }
    }
    return NULL;
}

int lin_abi2_is_enabled(
    const LinAbiContext *ctx,
    uint8_t abi_id
) {
    if (ctx == NULL) return 0;
    if (abi_id >= LIN_ABI2_MAX_DECLARED) return 0;
    return ctx->abi_version == LIN_HOST_ABI_2 &&
           ctx->declared[abi_id] != 0;
}

static LinAbiResult dispatch_region_capacity(
    const LinAbiContext *ctx,
    int64_t *stack,
    size_t *sp
) {
    if (*sp < 1u) return abi_result_vm_error(LIN_ERR_VM_STACK_UNDERFLOW);

    int64_t region_id = stack[*sp - 1u];
    const LinRegion *region = NULL;
    LinRegionErr error = lin_region_get(ctx->regions, region_id, &region);
    if (error != LIN_REGION_OK) return abi_result_region_error(error);

    uint64_t capacity = lin_region_capacity_bytes(region);
    /* LIN-ETH-1 is capped at 16 KiB, so this conversion is safe. Keep the
     * guard explicit because this is an ABI boundary, not an assumption. */
    if (capacity > INT64_MAX) return abi_result_region_error(LIN_REGION_ERR_OVERFLOW);

    *sp -= 1u;
    return abi_result_ok((int64_t)capacity);
}

static LinAbiResult dispatch_region_check_range(
    const LinAbiContext *ctx,
    int64_t *stack,
    size_t *sp
) {
    if (*sp < 3u) return abi_result_vm_error(LIN_ERR_VM_STACK_UNDERFLOW);

    int64_t region_id = stack[*sp - 3u];
    int64_t offset = stack[*sp - 2u];
    int64_t len = stack[*sp - 1u];

    if (offset < 0 || len < 0) {
        return abi_result_region_error(LIN_REGION_ERR_INVALID);
    }

    const LinRegion *region = NULL;
    LinRegionErr error = lin_region_get(ctx->regions, region_id, &region);
    if (error != LIN_REGION_OK) return abi_result_region_error(error);

    error = lin_region_check_range(
        region,
        (uint64_t)offset,
        (uint64_t)len
    );

    /* check_range is a status-producing intrinsic: the caller receives the
     * exact range status as its value, including TRUNCATED. The stack is
     * consumed because the dispatch itself succeeded. */
    *sp -= 3u;
    LinAbiResult result = abi_result_ok((int64_t)error);
    result.region_error = error;
    return result;
}

static LinAbiResult dispatch_region_load_byte(
    const LinAbiContext *ctx,
    int64_t *stack,
    size_t *sp
) {
    if (*sp < 2u) return abi_result_vm_error(LIN_ERR_VM_STACK_UNDERFLOW);

    int64_t region_id = stack[*sp - 2u];
    int64_t byte_index = stack[*sp - 1u];
    if (byte_index < 0) {
        return abi_result_region_error(LIN_REGION_ERR_INVALID);
    }

    const LinRegion *region = NULL;
    LinRegionErr error = lin_region_get(ctx->regions, region_id, &region);
    if (error != LIN_REGION_OK) return abi_result_region_error(error);

    uint8_t byte = 0;
    error = lin_region_load_byte(region, (uint64_t)byte_index, &byte);
    if (error != LIN_REGION_OK) return abi_result_region_error(error);

    *sp -= 2u;
    return abi_result_ok((int64_t)byte);
}

LinAbiResult lin_abi2_dispatch(
    const LinAbiContext *ctx,
    uint8_t abi_id,
    int64_t *stack,
    size_t *sp
) {
    if (ctx == NULL || sp == NULL) {
        return abi_result_region_error(LIN_REGION_ERR_INVALID);
    }
    if (ctx->abi_version != LIN_HOST_ABI_2) {
        return abi_result_region_error(LIN_REGION_ERR_ABI);
    }
    if (lin_abi2_desc(abi_id) == NULL) {
        return abi_result_region_error(LIN_REGION_ERR_ABI);
    }
    if (!lin_abi2_is_enabled(ctx, abi_id)) {
        return abi_result_region_error(LIN_REGION_ERR_ABI);
    }
    if (ctx->regions == NULL) {
        return abi_result_region_error(LIN_REGION_ERR_INVALID);
    }

    const LinAbiDesc *desc = lin_abi2_desc(abi_id);
    if (desc == NULL) {
        return abi_result_region_error(LIN_REGION_ERR_ABI);
    }
    if (stack == NULL && desc->nparams != 0u) {
        return abi_result_vm_error(LIN_ERR_VM_BAD_FN);
    }

    switch (abi_id) {
    case LIN_ABI2_REGION_CAPACITY:
        return dispatch_region_capacity(ctx, stack, sp);
    case LIN_ABI2_REGION_CHECK_RANGE:
        return dispatch_region_check_range(ctx, stack, sp);
    case LIN_ABI2_REGION_LOAD_BYTE:
        return dispatch_region_load_byte(ctx, stack, sp);
    default:
        return abi_result_region_error(LIN_REGION_ERR_ABI);
    }
}

const char *lin_abi2_status_name(const LinAbiResult *result) {
    if (result == NULL) return "invalid-result";
    if (result->vm_error != LIN_OK) return lin_err_name(result->vm_error);
    if (result->region_error != LIN_REGION_OK) {
        return lin_region_err_name(result->region_error);
    }
    return "ok";
}

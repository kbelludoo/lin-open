/*
 * lin_abi.h — HOST-ABI-2 read-only region intrinsics.
 *
 * This module deliberately does not modify the legacy VM opcode set yet. It
 * provides the fail-closed dispatcher that an OP_ABI_CALL implementation can
 * invoke once the profile-2 opcode/loader path is enabled.
 *
 * ABI 2 is additive to HOST-ABI-1:
 *   9  region_capacity(region_id) -> capacity bytes
 *   10 region_check_range(region_id, offset, len) -> 0 or region error
 *   11 region_load_byte(region_id, byte_index) -> byte
 *
 * The caller must explicitly enable each ABI id declared by an image. An
 * undeclared or unknown intrinsic is rejected; no fallback value is returned.
 */
#ifndef LIN_C_ABI_H
#define LIN_C_ABI_H

#include <stddef.h>
#include <stdint.h>

#include "lin_common.h"
#include "lin_region.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LIN_HOST_ABI_1 1u
#define LIN_HOST_ABI_2 2u
#define LIN_ABI2_FIRST_ID 9u
#define LIN_ABI2_LAST_ID  11u
#define LIN_ABI2_MAX_DECLARED 12u

#define LIN_ABI2_REGION_CAPACITY   9u
#define LIN_ABI2_REGION_CHECK_RANGE 10u
#define LIN_ABI2_REGION_LOAD_BYTE  11u

typedef struct {
    uint8_t abi_id;
    uint8_t nparams;
    uint8_t returns_value;
} LinAbiDesc;

/* One execution's ABI view. The region set is borrowed and read-only. */
typedef struct {
    const LinRegionSet *regions;
    uint8_t abi_version;
    uint8_t declared[LIN_ABI2_MAX_DECLARED];
} LinAbiContext;

/* A call can fail in the VM (for example stack underflow) or at the region
 * boundary. Keeping both channels avoids turning a valid byte 0x00 into an
 * error sentinel and preserves the exact region classification for receipts.
 */
typedef struct {
    LinErr vm_error;
    LinRegionErr region_error;
    int64_t value;
} LinAbiResult;

/* Initialize a context with no enabled intrinsics. */
void lin_abi2_context_init(
    LinAbiContext *ctx,
    const LinRegionSet *regions
);

/* Enable one ABI id after the image loader has verified its declaration. */
LinRegionErr lin_abi2_enable(
    LinAbiContext *ctx,
    uint8_t abi_id
);

/* Return the canonical descriptor, or NULL for an unknown id. */
const LinAbiDesc *lin_abi2_desc(uint8_t abi_id);

/* Return nonzero only when the image explicitly enabled this ABI id. */
int lin_abi2_is_enabled(
    const LinAbiContext *ctx,
    uint8_t abi_id
);

/*
 * Dispatch one intrinsic using the top of a caller-owned i64 stack.
 *
 * Arguments are consumed only after all preconditions for the selected call
 * have been validated. On failure, `*sp` and stack contents are unchanged.
 * On success, the intrinsic consumes its arguments and writes one result to
 * `out` (or to result.value in the returned struct).
 *
 * Required stack layout:
 *   id 9:  [region_id]
 *   id 10: [region_id, offset, len]
 *   id 11: [region_id, byte_index]
 */
LinAbiResult lin_abi2_dispatch(
    const LinAbiContext *ctx,
    uint8_t abi_id,
    int64_t *stack,
    size_t *sp
);

const char *lin_abi2_status_name(const LinAbiResult *result);

#ifdef __cplusplus
}
#endif

#endif /* LIN_C_ABI_H */

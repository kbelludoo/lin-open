/*
 * lin_region.h — immutable, bounds-checked input regions for LIN-ETH-1.
 *
 * Regions are host-owned i64 cells exposed to the VM through a narrow
 * read-only byte API. They are deliberately separate from the legacy local
 * array pool: legacy load_index returns zero out of bounds, while a region
 * access must fail closed on every invalid or truncated read.
 *
 * The caller owns the storage passed to lin_region_bind(). No allocation,
 * pointer value, clock, environment, or network state is part of the ABI.
 */
#ifndef LIN_C_REGION_H
#define LIN_C_REGION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LIN_REGION_MAX_COUNT       64u
#define LIN_REGION_MAX_CELLS       2048u
#define LIN_ETH_MAX_INPUT_BYTES    16384u
#define LIN_REGION_CELL_BYTES      8u

/* Region-layer errors are intentionally distinct from LinErr and from the
 * public KECCAK_* status namespace. The caller maps them at the ABI boundary.
 */
typedef enum {
    LIN_REGION_OK = 0,
    LIN_REGION_ERR_INVALID = 1,
    LIN_REGION_ERR_BOUNDS = 2,
    LIN_REGION_ERR_TRUNCATED = 3,
    LIN_REGION_ERR_OVERFLOW = 4,
    LIN_REGION_ERR_ABI = 5
} LinRegionErr;

typedef struct {
    uint32_t region_id;
    uint32_t capacity_cells;
    uint32_t payload_len;
    int64_t *cells;
} LinRegion;

typedef struct {
    LinRegion regions[LIN_REGION_MAX_COUNT];
    size_t len;
} LinRegionSet;

/* Initialize an empty set. The set does not own or allocate cell storage. */
void lin_region_set_init(LinRegionSet *set);

/* Clear bindings while retaining no pointers into caller storage. */
void lin_region_set_clear(LinRegionSet *set);

/*
 * Bind one canonical region to caller-owned cells.
 *
 * Requirements:
 *   - region_id must equal the next canonical id, i.e. set->len;
 *   - cells must be non-NULL when capacity_cells != 0;
 *   - capacity_cells must be <= LIN_REGION_MAX_CELLS;
 *   - payload_len must be <= capacity_cells * 8;
 *   - payload_len must be <= LIN_ETH_MAX_INPUT_BYTES.
 */
LinRegionErr lin_region_bind(
    LinRegionSet *set,
    uint32_t region_id,
    int64_t *cells,
    uint32_t capacity_cells,
    uint32_t payload_len
);

/* Look up a region using a signed ABI value without signed-to-size_t bugs. */
LinRegionErr lin_region_get(
    const LinRegionSet *set,
    int64_t region_id,
    const LinRegion **out
);

/* Return capacity in bytes, or 0 for an invalid region pointer. */
uint64_t lin_region_capacity_bytes(const LinRegion *region);

/*
 * Copy an external byte payload into a bound region in canonical little-endian
 * cell order. `src` must not alias region->cells. The payload becomes the
 * region's logical message and all unused cells/bytes are zeroed. The
 * operation is atomic with respect to metadata: on failure, payload_len and
 * cell contents are left unchanged.
 */
LinRegionErr lin_region_write_bytes(
    LinRegion *region,
    const uint8_t *src,
    size_t src_len
);

/* Validate that [offset, offset + len) is entirely within the logical payload. */
LinRegionErr lin_region_check_range(
    const LinRegion *region,
    uint64_t offset,
    uint64_t len
);

/* Read one complete i64 cell with bounds checking. */
LinRegionErr lin_region_load_cell(
    const LinRegion *region,
    uint64_t cell_index,
    int64_t *out
);

/* Read one byte in little-endian cell order. Never returns zero for an error. */
LinRegionErr lin_region_load_byte(
    const LinRegion *region,
    uint64_t byte_index,
    uint8_t *out
);

const char *lin_region_err_name(LinRegionErr err);

#ifdef __cplusplus
}
#endif

#endif /* LIN_C_REGION_H */

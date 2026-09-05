/*
 * lin_region.c — implementation of the LIN-ETH-1 region boundary.
 */
#include "lin_region.h"

#include <limits.h>
#include <string.h>

static int region_struct_valid(const LinRegion *region) {
    if (region == NULL) return 0;
    if (region->capacity_cells > LIN_REGION_MAX_CELLS) return 0;
    if (region->capacity_cells != 0 && region->cells == NULL) return 0;
    if ((uint64_t)region->payload_len > lin_region_capacity_bytes(region)) return 0;
    if (region->payload_len > LIN_ETH_MAX_INPUT_BYTES) return 0;
    return 1;
}

void lin_region_set_init(LinRegionSet *set) {
    if (set == NULL) return;
    memset(set, 0, sizeof(*set));
}

void lin_region_set_clear(LinRegionSet *set) {
    if (set == NULL) return;
    /* Do not erase caller-owned cells. Only discard the bindings. */
    memset(set, 0, sizeof(*set));
}

uint64_t lin_region_capacity_bytes(const LinRegion *region) {
    if (region == NULL) return 0;
    return (uint64_t)region->capacity_cells * LIN_REGION_CELL_BYTES;
}

LinRegionErr lin_region_bind(
    LinRegionSet *set,
    uint32_t region_id,
    int64_t *cells,
    uint32_t capacity_cells,
    uint32_t payload_len
) {
    if (set == NULL) return LIN_REGION_ERR_INVALID;
    if (set->len >= LIN_REGION_MAX_COUNT) return LIN_REGION_ERR_BOUNDS;

    /* LINBC1 regions are canonical and contiguous: 0, 1, 2, ... */
    if (region_id != (uint32_t)set->len) return LIN_REGION_ERR_ABI;
    if (capacity_cells > LIN_REGION_MAX_CELLS) return LIN_REGION_ERR_BOUNDS;
    if (capacity_cells != 0 && cells == NULL) return LIN_REGION_ERR_INVALID;

    uint64_t capacity_bytes =
        (uint64_t)capacity_cells * LIN_REGION_CELL_BYTES;
    if ((uint64_t)payload_len > capacity_bytes) {
        return LIN_REGION_ERR_TRUNCATED;
    }
    if (payload_len > LIN_ETH_MAX_INPUT_BYTES) {
        return LIN_REGION_ERR_BOUNDS;
    }

    LinRegion *region = &set->regions[set->len];
    region->region_id = region_id;
    region->capacity_cells = capacity_cells;
    region->payload_len = payload_len;
    region->cells = cells;
    set->len += 1;
    return LIN_REGION_OK;
}

LinRegionErr lin_region_get(
    const LinRegionSet *set,
    int64_t region_id,
    const LinRegion **out
) {
    if (out == NULL) return LIN_REGION_ERR_INVALID;
    *out = NULL;

    if (set == NULL) return LIN_REGION_ERR_INVALID;
    if (region_id < 0) return LIN_REGION_ERR_INVALID;
    if ((uint64_t)region_id >= set->len) return LIN_REGION_ERR_INVALID;

    const LinRegion *region = &set->regions[(size_t)region_id];
    if (region->region_id != (uint32_t)region_id) {
        return LIN_REGION_ERR_ABI;
    }
    if (!region_struct_valid(region)) {
        return LIN_REGION_ERR_ABI;
    }

    *out = region;
    return LIN_REGION_OK;
}

LinRegionErr lin_region_write_bytes(
    LinRegion *region,
    const uint8_t *src,
    size_t src_len
) {
    if (region == NULL) return LIN_REGION_ERR_INVALID;
    if (!region_struct_valid(region)) return LIN_REGION_ERR_ABI;
    if (src == NULL && src_len != 0) return LIN_REGION_ERR_INVALID;
    if (src_len > LIN_ETH_MAX_INPUT_BYTES) return LIN_REGION_ERR_BOUNDS;
    if ((uint64_t)src_len > lin_region_capacity_bytes(region)) {
        return LIN_REGION_ERR_TRUNCATED;
    }

    /* The caller must provide source bytes outside region->cells. The host
     * boundary owns the input buffer; keeping that contract avoids an alias
     * that would be destroyed by the zero-fill below. */
    size_t cell_bytes = (size_t)region->capacity_cells * sizeof(int64_t);
    memset(region->cells, 0, cell_bytes);

    for (size_t i = 0; i < src_len; i++) {
        size_t cell_index = i / LIN_REGION_CELL_BYTES;
        unsigned byte_offset = (unsigned)(i % LIN_REGION_CELL_BYTES);
        uint64_t word = (uint64_t)region->cells[cell_index];
        word |= ((uint64_t)src[i]) << (byte_offset * 8u);
        region->cells[cell_index] = (int64_t)word;
    }

    region->payload_len = (uint32_t)src_len;
    return LIN_REGION_OK;
}

LinRegionErr lin_region_check_range(
    const LinRegion *region,
    uint64_t offset,
    uint64_t len
) {
    if (region == NULL) return LIN_REGION_ERR_INVALID;
    if (!region_struct_valid(region)) return LIN_REGION_ERR_ABI;
    if (offset > region->payload_len) return LIN_REGION_ERR_TRUNCATED;
    if (len > (uint64_t)region->payload_len - offset) {
        return LIN_REGION_ERR_TRUNCATED;
    }
    return LIN_REGION_OK;
}

LinRegionErr lin_region_load_cell(
    const LinRegion *region,
    uint64_t cell_index,
    int64_t *out
) {
    if (out == NULL) return LIN_REGION_ERR_INVALID;
    if (region == NULL) return LIN_REGION_ERR_INVALID;
    if (!region_struct_valid(region)) return LIN_REGION_ERR_ABI;
    if (cell_index >= region->capacity_cells) {
        return LIN_REGION_ERR_BOUNDS;
    }

    *out = region->cells[cell_index];
    return LIN_REGION_OK;
}

LinRegionErr lin_region_load_byte(
    const LinRegion *region,
    uint64_t byte_index,
    uint8_t *out
) {
    if (out == NULL) return LIN_REGION_ERR_INVALID;
    if (region == NULL) return LIN_REGION_ERR_INVALID;
    if (!region_struct_valid(region)) return LIN_REGION_ERR_ABI;

    uint64_t capacity_bytes = lin_region_capacity_bytes(region);
    if (byte_index >= capacity_bytes) return LIN_REGION_ERR_BOUNDS;
    if (byte_index >= region->payload_len) {
        return LIN_REGION_ERR_TRUNCATED;
    }

    uint64_t cell_index = byte_index / LIN_REGION_CELL_BYTES;
    unsigned byte_offset = (unsigned)(byte_index % LIN_REGION_CELL_BYTES);
    if (cell_index >= region->capacity_cells) {
        return LIN_REGION_ERR_BOUNDS;
    }

    uint64_t word = (uint64_t)region->cells[cell_index];
    *out = (uint8_t)((word >> (byte_offset * 8u)) & 0xffu);
    return LIN_REGION_OK;
}

const char *lin_region_err_name(LinRegionErr err) {
    switch (err) {
    case LIN_REGION_OK: return "ok";
    case LIN_REGION_ERR_INVALID: return "invalid";
    case LIN_REGION_ERR_BOUNDS: return "bounds";
    case LIN_REGION_ERR_TRUNCATED: return "truncated";
    case LIN_REGION_ERR_OVERFLOW: return "overflow";
    case LIN_REGION_ERR_ABI: return "abi";
    default: return "unknown";
    }
}

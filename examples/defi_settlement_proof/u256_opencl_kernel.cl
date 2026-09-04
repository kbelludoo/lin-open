// OpenCL Kernel para Liquidação uint256 da Uniswap V2
// Executa a aritmética multiword exata (16 limbs de 16 bits) em hardware GPU

void u256_divmod(const ushort *num, const ushort *den, ushort *quot) {
    ushort rem[32];
    for (int i = 0; i < 32; i++) {
        rem[i] = num[i];
    }
    for (int i = 0; i < 16; i++) {
        quot[i] = 0;
    }

    int den_len = 0;
    for (int i = 15; i >= 0; i--) {
        if (den[i] != 0) {
            den_len = i + 1;
            break;
        }
    }
    if (den_len == 0) return;

    for (int shift = 16; shift >= 0; shift--) {
        for (int bit = 15; bit >= 0; bit--) {
            // Comparação rem >= (den << (shift*16 + bit))
            bool ge = true;
            for (int i = 31; i >= 0; i--) {
                int den_idx = i - shift;
                uint shifted_den = 0;
                if (den_idx >= 0 && den_idx < 16) {
                    shifted_den |= ((uint)den[den_idx]) << bit;
                }
                if (den_idx - 1 >= 0 && den_idx - 1 < 16 && bit > 0) {
                    shifted_den |= ((uint)den[den_idx - 1]) >> (16 - bit);
                }
                ushort d_limb = (ushort)(shifted_den & 0xFFFF);
                if (rem[i] > d_limb) { ge = true; break; }
                if (rem[i] < d_limb) { ge = false; break; }
            }

            if (ge) {
                if (shift < 16) {
                    quot[shift] |= (1 << bit);
                }
                // Subtrai
                int borrow = 0;
                for (int i = 0; i < 32; i++) {
                    int den_idx = i - shift;
                    uint shifted_den = 0;
                    if (den_idx >= 0 && den_idx < 16) {
                        shifted_den |= ((uint)den[den_idx]) << bit;
                    }
                    if (den_idx - 1 >= 0 && den_idx - 1 < 16 && bit > 0) {
                        shifted_den |= ((uint)den[den_idx - 1]) >> (16 - bit);
                    }
                    ushort d_limb = (ushort)(shifted_den & 0xFFFF);
                    int diff = (int)rem[i] - (int)d_limb - borrow;
                    if (diff < 0) {
                        diff += 65536;
                        borrow = 1;
                    } else {
                        borrow = 0;
                    }
                    rem[i] = (ushort)diff;
                }
            }
        }
    }
}

__kernel void settle_u256_batch(
    __global const uchar *in_records, // 128 bytes per record: ain(32), rin(32), rout(32), exp(32)
    __global uchar *out_results,      // 32 bytes per record: amount_out
    __global int *out_match,          // 1 if match, 0 if divergence
    const uint total_swaps
) {
    uint gid = get_global_id(0);
    if (gid >= total_swaps) return;

    uint offset = gid * 128;
    __global const uchar *ain_b = in_records + offset;
    __global const uchar *rin_b = in_records + offset + 32;
    __global const uchar *rout_b = in_records + offset + 64;
    __global const uchar *exp_b = in_records + offset + 96;

    ushort ain[16], rin[16], rout[16];
    for (int i = 0; i < 16; i++) {
        int base = 30 - 2 * i;
        ain[i] = (((ushort)ain_b[base]) << 8) | (ushort)ain_b[base + 1];
        rin[i] = (((ushort)rin_b[base]) << 8) | (ushort)rin_b[base + 1];
        rout[i] = (((ushort)rout_b[base]) << 8) | (ushort)rout_b[base + 1];
    }

    // ain_with_fee = ain * 997
    ushort ain_fee[16];
    uint carry = 0;
    for (int i = 0; i < 16; i++) {
        uint prod = ((uint)ain[i]) * 997 + carry;
        ain_fee[i] = (ushort)(prod & 0xFFFF);
        carry = prod >> 16;
    }

    // num = ain_fee * rout
    ushort num[32];
    for (int i = 0; i < 32; i++) num[i] = 0;
    for (int i = 0; i < 16; i++) {
        carry = 0;
        for (int j = 0; j < 16; j++) {
            uint cur = ((uint)num[i + j]) + ((uint)ain_fee[i]) * ((uint)rout[j]) + carry;
            num[i + j] = (ushort)(cur & 0xFFFF);
            carry = cur >> 16;
        }
        num[i + 16] += (ushort)carry;
    }

    // den = rin * 1000 + ain_fee
    ushort den[16];
    carry = 0;
    for (int i = 0; i < 16; i++) {
        uint p = ((uint)rin[i]) * 1000 + (uint)ain_fee[i] + carry;
        den[i] = (ushort)(p & 0xFFFF);
        carry = p >> 16;
    }

    ushort quot[16];
    u256_divmod(num, den, quot);

    // Converte de volta para 32 bytes big-endian
    __global uchar *res_b = out_results + (gid * 32);
    bool match = true;
    for (int i = 0; i < 16; i++) {
        int base = 30 - 2 * i;
        uchar b0 = (uchar)(quot[i] >> 8);
        uchar b1 = (uchar)(quot[i] & 0xFF);
        res_b[base] = b0;
        res_b[base + 1] = b1;
        if (res_b[base] != exp_b[base] || res_b[base + 1] != exp_b[base + 1]) {
            match = false;
        }
    }

    out_match[gid] = match ? 1 : 0;
}

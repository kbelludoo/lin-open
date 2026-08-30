pub fn nested_matrix_sum_aot(arg0: i64, arg1: i64) i64 {
    var r: [256]i64 = [_]i64{0} ** 256;
    r[0] = arg0;
    r[1] = arg1;
    var current_block: u32 = 0;
    var prev_block: u32 = 0;
    while (true) {
        switch (current_block) {
            0 => {
                r[0] = r[0];
                r[1] = r[1];
                r[2] = 0;
                r[3] = 1;
                prev_block = 0;
                current_block = 1;
                continue;
            },
            1 => {
                r[4] = switch (prev_block) {
                    0 => r[2],
                    6 => r[13],
                    else => r[2],
                };
                r[5] = switch (prev_block) {
                    0 => r[2],
                    6 => r[14],
                    else => r[2],
                };
                r[6] = if (r[5] < r[0]) 1 else 0;
                prev_block = 1;
                current_block = if (r[6] != 0) 2 else 5;
                continue;
            },
            2 => {
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[7] = switch (prev_block) {
                    2 => r[4],
                    4 => r[11],
                    else => r[4],
                };
                r[8] = switch (prev_block) {
                    2 => r[2],
                    4 => r[12],
                    else => r[2],
                };
                r[9] = if (r[8] < r[1]) 1 else 0;
                prev_block = 3;
                current_block = if (r[9] != 0) 4 else 6;
                continue;
            },
            4 => {
                r[10] = r[5] *% r[1];
                r[11] = r[7] +% r[3];
                r[12] = r[8] +% r[3];
                prev_block = 4;
                current_block = 3;
                continue;
            },
            5 => {
                return r[4];
            },
            6 => {
                r[13] = r[7] +% r[2];
                r[14] = r[5] +% r[3];
                prev_block = 6;
                current_block = 1;
                continue;
            },
            else => unreachable,
        }
    }
}

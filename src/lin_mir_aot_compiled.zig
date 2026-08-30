pub fn mir_abs_diff(arg0: i64, arg1: i64) i64 {
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
                r[2] = if (r[0] < r[1]) 1 else 0;
                prev_block = 0;
                current_block = if (r[2] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[3] = r[1] -% r[0];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[4] = r[0] -% r[1];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[5] = switch (prev_block) {
                    1 => r[3],
                    2 => r[4],
                    else => r[3],
                };
                return r[5];
            },
            else => unreachable,
        }
    }
}

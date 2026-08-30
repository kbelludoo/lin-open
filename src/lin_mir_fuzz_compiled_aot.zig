// AUTO-GENERATED COMPILED AOT MODULE FOR LIN-MIR-FUZZ-005B
const std = @import("std");

pub fn fuzz_fn_0(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_1(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_2(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_3(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_4(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_5(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_6(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_7(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_8(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_9(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_10(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_11(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_12(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_13(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_14(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_15(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_16(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_17(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_18(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_19(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_20(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_21(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_22(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_23(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_24(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_25(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_26(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_27(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_28(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_29(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_30(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_31(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_32(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_33(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_34(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_35(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] +% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_36(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_37(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_38(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_39(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_40(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_41(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_42(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_43(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_44(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_45(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_46(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_47(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_48(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_49(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_50(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_51(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_52(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_53(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_54(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_55(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_56(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_57(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_58(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_59(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_60(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_61(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_62(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_63(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_64(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_65(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_66(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_67(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_68(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_69(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_70(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_71(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] -% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_72(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_73(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_74(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_75(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_76(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_77(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_78(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_79(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_80(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_81(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_82(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_83(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_84(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_85(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_86(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_87(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_88(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_89(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_90(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_91(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_92(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_93(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_94(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_95(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_96(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_97(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_98(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_99(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_100(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_101(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_102(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_103(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_104(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_105(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_106(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_107(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] *% r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_108(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_109(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_110(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_111(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_112(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_113(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_114(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_115(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_116(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_117(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_118(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_119(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_120(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_121(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_122(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_123(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_124(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_125(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_126(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_127(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_128(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_129(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_130(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_131(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_132(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_133(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_134(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_135(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_136(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_137(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_138(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_139(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_140(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_141(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_142(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_143(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] & r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_144(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_145(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_146(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_147(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_148(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_149(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_150(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_151(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_152(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_153(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_154(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_155(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_156(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_157(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_158(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_159(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_160(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_161(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_162(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_163(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_164(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_165(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_166(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_167(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_168(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_169(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_170(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_171(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_172(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_173(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_174(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_175(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_176(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_177(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_178(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_179(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] | r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_180(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_181(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_182(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_183(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_184(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_185(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] +% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_186(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_187(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_188(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_189(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_190(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_191(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] -% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_192(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_193(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_194(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_195(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_196(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_197(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] *% r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_198(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_199(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_200(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_201(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_202(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_203(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] & r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_204(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_205(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_206(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_207(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_208(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_209(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] | r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_210(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] +% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_211(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] -% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_212(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] *% r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_213(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] & r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_214(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] | r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub fn fuzz_fn_215(arg0: i64, arg1: i64) i64 {
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
                r[2] = r[0] ^ r[1];
                r[3] = if (r[2] < r[0]) 1 else 0;
                prev_block = 0;
                current_block = if (r[3] != 0) 1 else 2;
                continue;
            },
            1 => {
                r[4] = r[0] ^ r[1];
                prev_block = 1;
                current_block = 3;
                continue;
            },
            2 => {
                r[5] = r[1] ^ r[0];
                prev_block = 2;
                current_block = 3;
                continue;
            },
            3 => {
                r[6] = switch (prev_block) {
                    1 => r[4],
                    2 => r[5],
                    else => r[4],
                };
                return r[6];
            },
            else => unreachable,
        }
    }
}

pub const all_aot_fns = [_]*const fn(i64, i64) i64{
    fuzz_fn_0,
    fuzz_fn_1,
    fuzz_fn_2,
    fuzz_fn_3,
    fuzz_fn_4,
    fuzz_fn_5,
    fuzz_fn_6,
    fuzz_fn_7,
    fuzz_fn_8,
    fuzz_fn_9,
    fuzz_fn_10,
    fuzz_fn_11,
    fuzz_fn_12,
    fuzz_fn_13,
    fuzz_fn_14,
    fuzz_fn_15,
    fuzz_fn_16,
    fuzz_fn_17,
    fuzz_fn_18,
    fuzz_fn_19,
    fuzz_fn_20,
    fuzz_fn_21,
    fuzz_fn_22,
    fuzz_fn_23,
    fuzz_fn_24,
    fuzz_fn_25,
    fuzz_fn_26,
    fuzz_fn_27,
    fuzz_fn_28,
    fuzz_fn_29,
    fuzz_fn_30,
    fuzz_fn_31,
    fuzz_fn_32,
    fuzz_fn_33,
    fuzz_fn_34,
    fuzz_fn_35,
    fuzz_fn_36,
    fuzz_fn_37,
    fuzz_fn_38,
    fuzz_fn_39,
    fuzz_fn_40,
    fuzz_fn_41,
    fuzz_fn_42,
    fuzz_fn_43,
    fuzz_fn_44,
    fuzz_fn_45,
    fuzz_fn_46,
    fuzz_fn_47,
    fuzz_fn_48,
    fuzz_fn_49,
    fuzz_fn_50,
    fuzz_fn_51,
    fuzz_fn_52,
    fuzz_fn_53,
    fuzz_fn_54,
    fuzz_fn_55,
    fuzz_fn_56,
    fuzz_fn_57,
    fuzz_fn_58,
    fuzz_fn_59,
    fuzz_fn_60,
    fuzz_fn_61,
    fuzz_fn_62,
    fuzz_fn_63,
    fuzz_fn_64,
    fuzz_fn_65,
    fuzz_fn_66,
    fuzz_fn_67,
    fuzz_fn_68,
    fuzz_fn_69,
    fuzz_fn_70,
    fuzz_fn_71,
    fuzz_fn_72,
    fuzz_fn_73,
    fuzz_fn_74,
    fuzz_fn_75,
    fuzz_fn_76,
    fuzz_fn_77,
    fuzz_fn_78,
    fuzz_fn_79,
    fuzz_fn_80,
    fuzz_fn_81,
    fuzz_fn_82,
    fuzz_fn_83,
    fuzz_fn_84,
    fuzz_fn_85,
    fuzz_fn_86,
    fuzz_fn_87,
    fuzz_fn_88,
    fuzz_fn_89,
    fuzz_fn_90,
    fuzz_fn_91,
    fuzz_fn_92,
    fuzz_fn_93,
    fuzz_fn_94,
    fuzz_fn_95,
    fuzz_fn_96,
    fuzz_fn_97,
    fuzz_fn_98,
    fuzz_fn_99,
    fuzz_fn_100,
    fuzz_fn_101,
    fuzz_fn_102,
    fuzz_fn_103,
    fuzz_fn_104,
    fuzz_fn_105,
    fuzz_fn_106,
    fuzz_fn_107,
    fuzz_fn_108,
    fuzz_fn_109,
    fuzz_fn_110,
    fuzz_fn_111,
    fuzz_fn_112,
    fuzz_fn_113,
    fuzz_fn_114,
    fuzz_fn_115,
    fuzz_fn_116,
    fuzz_fn_117,
    fuzz_fn_118,
    fuzz_fn_119,
    fuzz_fn_120,
    fuzz_fn_121,
    fuzz_fn_122,
    fuzz_fn_123,
    fuzz_fn_124,
    fuzz_fn_125,
    fuzz_fn_126,
    fuzz_fn_127,
    fuzz_fn_128,
    fuzz_fn_129,
    fuzz_fn_130,
    fuzz_fn_131,
    fuzz_fn_132,
    fuzz_fn_133,
    fuzz_fn_134,
    fuzz_fn_135,
    fuzz_fn_136,
    fuzz_fn_137,
    fuzz_fn_138,
    fuzz_fn_139,
    fuzz_fn_140,
    fuzz_fn_141,
    fuzz_fn_142,
    fuzz_fn_143,
    fuzz_fn_144,
    fuzz_fn_145,
    fuzz_fn_146,
    fuzz_fn_147,
    fuzz_fn_148,
    fuzz_fn_149,
    fuzz_fn_150,
    fuzz_fn_151,
    fuzz_fn_152,
    fuzz_fn_153,
    fuzz_fn_154,
    fuzz_fn_155,
    fuzz_fn_156,
    fuzz_fn_157,
    fuzz_fn_158,
    fuzz_fn_159,
    fuzz_fn_160,
    fuzz_fn_161,
    fuzz_fn_162,
    fuzz_fn_163,
    fuzz_fn_164,
    fuzz_fn_165,
    fuzz_fn_166,
    fuzz_fn_167,
    fuzz_fn_168,
    fuzz_fn_169,
    fuzz_fn_170,
    fuzz_fn_171,
    fuzz_fn_172,
    fuzz_fn_173,
    fuzz_fn_174,
    fuzz_fn_175,
    fuzz_fn_176,
    fuzz_fn_177,
    fuzz_fn_178,
    fuzz_fn_179,
    fuzz_fn_180,
    fuzz_fn_181,
    fuzz_fn_182,
    fuzz_fn_183,
    fuzz_fn_184,
    fuzz_fn_185,
    fuzz_fn_186,
    fuzz_fn_187,
    fuzz_fn_188,
    fuzz_fn_189,
    fuzz_fn_190,
    fuzz_fn_191,
    fuzz_fn_192,
    fuzz_fn_193,
    fuzz_fn_194,
    fuzz_fn_195,
    fuzz_fn_196,
    fuzz_fn_197,
    fuzz_fn_198,
    fuzz_fn_199,
    fuzz_fn_200,
    fuzz_fn_201,
    fuzz_fn_202,
    fuzz_fn_203,
    fuzz_fn_204,
    fuzz_fn_205,
    fuzz_fn_206,
    fuzz_fn_207,
    fuzz_fn_208,
    fuzz_fn_209,
    fuzz_fn_210,
    fuzz_fn_211,
    fuzz_fn_212,
    fuzz_fn_213,
    fuzz_fn_214,
    fuzz_fn_215,
};

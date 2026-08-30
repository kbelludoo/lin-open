const std = @import("std");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== EXECUTING 34-TARGET CORPUS VIA 'lin hypo' WITH RULEL VERDICTS ===\n", .{});
    try stdout.print("================================================================================\n\n", .{});

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const alloc = gpa.allocator();

    const targets = [_]struct { file: []const u8, fn_name: []const u8, args: []const []const u8, expected: []const u8 }{
        .{ .file = "test/corpus/adler32.lin", .fn_name = "test_adler32_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/aead_poly1305.lin", .fn_name = "test_aead_poly1305_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/aes128.lin", .fn_name = "test_aes_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/alac_flac.lin", .fn_name = "test_alac_flac_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/blake2b.lin", .fn_name = "test_blake2b_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/blake3.lin", .fn_name = "test_blake3_g", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/brotli_bit.lin", .fn_name = "test_brotli_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/brotli_huffman.lin", .fn_name = "test_brotli_huffman_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/chacha20.lin", .fn_name = "test_chacha_rfc_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/cityhash64.lin", .fn_name = "test_cityhash_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/crc32.lin", .fn_name = "test_crc32_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/cswap_montgomery.lin", .fn_name = "test_cswap_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/curve25519_fe.lin", .fn_name = "test_curve25519_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/fast_bitset.lin", .fn_name = "test_bitset_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/fnv1a.lin", .fn_name = "test_fnv1a_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/hilbert3d.lin", .fn_name = "test_morton3d_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/keccak.lin", .fn_name = "test_keccak_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/morton_spatial.lin", .fn_name = "test_morton_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/murmur3.lin", .fn_name = "test_murmur3_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/nested_matrix_sum.lin", .fn_name = "test_nested_matrix_sum_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/pcg_random.lin", .fn_name = "test_pcg_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/philox.lin", .fn_name = "test_philox_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/poly1305.lin", .fn_name = "test_poly1305_rfc_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/popcount_massey.lin", .fn_name = "test_massey_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/prng_bryc.lin", .fn_name = "test_prng_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/prospector_skeeto.lin", .fn_name = "test_prospector_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/protobuf_varint.lin", .fn_name = "test_protobuf_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/ripemd160.lin", .fn_name = "test_ripemd160_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/roaring_search.lin", .fn_name = "test_roaring_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/siphash.lin", .fn_name = "test_sipround_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/splitmix64.lin", .fn_name = "test_splitmix64_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/vp8_dct.lin", .fn_name = "test_vp8_dct_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/wyhash.lin", .fn_name = "test_wyhash_vectors", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/xoshiro256.lin", .fn_name = "test_xoshiro256_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/xxhash64.lin", .fn_name = "test_xxh64_vector", .args = &.{}, .expected = "1" },
        .{ .file = "test/corpus/xxhash_kernels.lin", .fn_name = "test_xxhash_vectors", .args = &.{}, .expected = "1" },
    };

    var verified_count: usize = 0;

    for (targets, 0..) |t, idx| {
        var argv = std.ArrayList([]const u8).init(alloc);
        defer argv.deinit();

        try argv.append("bin/lin_native");
        try argv.append("hypo");
        try argv.append(t.file);
        try argv.append(t.fn_name);
        for (t.args) |arg| {
            try argv.append(arg);
        }
        try argv.append("--expected");
        try argv.append(t.expected);

        var child = std.process.Child.init(argv.items, alloc);
        child.stdout_behavior = .Pipe;
        child.stderr_behavior = .Pipe;

        try child.spawn();
        const out = try child.stdout.?.readToEndAlloc(alloc, 1024 * 1024);
        defer alloc.free(out);
        _ = try child.wait();

        const confirmed = std.mem.indexOf(u8, out, ".verdict=\"CONFIRMED\"") != null;
        if (confirmed) {
            verified_count += 1;
            try stdout.print("[HYPO {d:02}/{d:02}] {s:34} :: {s:26} -> CONFIRMED\n", .{
                idx + 1, targets.len, t.file, t.fn_name,
            });
        } else {
            try stdout.print("[HYPO {d:02}/{d:02}] {s:34} :: {s:26} -> REFUTED / FAILED\nOutput:\n{s}\n", .{
                idx + 1, targets.len, t.file, t.fn_name, out,
            });
        }
    }

    try stdout.print("\n================================================================================\n", .{});
    try stdout.print("=== SUMMARY: {d}/{d} CORPUS HYPOTHESES CONFIRMED VIA 'lin hypo' ===\n", .{ verified_count, targets.len });
    try stdout.print("================================================================================\n\n", .{});
}

//! lin_attestation_guard.zig — fail-closed gate for attestation commands whose
//! published verdicts are not backed by any computation in this repository.
//!
//! Why this file exists (see SECURITY_AUDIT.md, section 7):
//!
//! A number of `lin *-verify` sub-commands used to print `[PASS]` lines and write
//! `.rulel` receipts asserting things like `verified_ed25519_seal=true`,
//! `polyglot_conformance_status="BIT_EXACT_INTEROPERABILITY_CONFIRMED"` or
//! `final_verdict="PASS"` without executing the algorithm the label describes:
//! no signature was checked, no second implementation was invoked, and the
//! fixtures they claim to read (`test/conformance_vectors`, `test/packages`,
//! `test/registry`, `repos/qoi`, `repos/darknet`) are not in the repository.
//!
//! A receipt that a third party cannot reproduce is not evidence. Publishing one
//! as evidence is the "passivo juridico" case: it reads as a technical claim the
//! product does not make good on. Every command listed in `registry` below is
//! therefore refused with `error.NotImplemented` unless the operator explicitly
//! asks for the simulation with `--allow-simulated`, in which case the run is
//! announced on stderr and appended to `simulated_attestations.log` in the CWD.
//!
//! Nothing in this module decides whether a verdict is *good*; it only stops
//! verdicts that were never computed from being emitted silently.

const std = @import("std");

/// Flag that opts a gated command back in as an explicitly labelled simulation.
pub const allow_flag = "--allow-simulated";

/// File (in the CWD) that records every simulation run.
pub const audit_log_name = "simulated_attestations.log";

pub const SimulatedCommand = struct {
    /// Canonical command name, as in `lin <cmd>`.
    cmd: []const u8,
    /// Every alias that must be gated identically.
    aliases: []const []const u8 = &.{},
    /// Claims the command emits that no code path in this repository produces.
    unverified_claims: []const []const u8,
    /// What must be true before this command may publish a verdict again.
    required_evidence: []const u8,
};

/// Commands whose output is (or was) fabricated. Kept in source order of the CLI
/// dispatch so the list can be diffed against `compiler/lin.zig`.
pub const registry = [_]SimulatedCommand{
    .{
        .cmd = "cross-verify",
        .aliases = &.{"multi-verify"},
        .unverified_claims = &.{
            "three \"independent runtimes\" — all three are the same BundleVerifier.verify over three copies of the same bytes",
            "independent_verifier_implementations=3",
        },
        .required_evidence = "Invoke at least two implementations built from different source bases (e.g. the C engine in transpile/c/ next to the Zig verifier) and compare their receipts.",
    },
    .{
        .cmd = "n-version-verify",
        .aliases = &.{"common-mode-verify"},
        .unverified_claims = &.{
            "VERIFIER_B \"LIN Cleanroom / .lin\" — src/lin_cleanroom_verifier.lin does not exist; Verifier A and Verifier B run the identical code path",
            "ED25519 VERIFICATION CONSENSUS (3/3) — Verifier C only checks that the signature field is 128 hex chars",
            "ground-truth oracle digest is a hardcoded constant (OracleExpectation.expected_digest)",
        },
        .required_evidence = "Ship the second implementation, verify the Ed25519 seal in every verifier, and derive the oracle expectation from an artifact outside this binary.",
    },
    .{
        .cmd = "federation-verify",
        .aliases = &.{"federated-attest"},
        .unverified_claims = &.{
            "three \"federated bundles\" from lin-compiler/corpus, phoboslab/qoi and pjreddie/darknet — hardcoded descriptors; those repositories are not present",
            "every bundle printed as [VERIFIED] without opening a bundle file",
        },
        .required_evidence = "Take bundle paths as input and run BundleVerifier.verify on each one; count only real verdicts.",
    },
    .{
        .cmd = "global-ledger-verify",
        .aliases = &.{"scale-ledger-verify"},
        .unverified_claims = &.{
            "N=1000 \"federated bundles\" — synthesised in a loop from an index hash, not read from any ledger",
            "mixed-version / cross-arch heterogeneity of the corpus",
        },
        .required_evidence = "Read a real ledger index from disk and validate its entries; report the number of entries actually validated.",
    },
    .{
        .cmd = "temporal-ledger-verify",
        .aliases = &.{"temporal-verify"},
        .unverified_claims = &.{
            "epoch chain S_0..S_3 built from hardcoded entry tables (object_digest values are literals)",
            "revocation / anti-rollback enforcement over a live log",
        },
        .required_evidence = "Parse an epoch log artifact, recompute the state chain from it and reject a non-monotonic epoch.",
    },
    .{
        .cmd = "roster-transition-verify",
        .aliases = &.{"recovery-verify"},
        .unverified_claims = &.{
            "roster succession \"succession_verified\" — the string is fed into the hash, no signature over the transition is checked",
            "witness pubkeys / quorum authorisation of the new roster",
        },
        .required_evidence = "Require signed transition authorisations from the outgoing roster and verify them with Ed25519 before publishing the transition proof.",
    },
    .{
        .cmd = "verify-all",
        .aliases = &.{"audit"},
        .unverified_claims = &.{
            "ten evidence fields (execution_evidence, hardware_identity, mir_integrity, merkle_supply_chain, temporal_provenance, external_checkpoint, roster_succession, anti_rollback, anti_equivocation, quorum_policy) all printed VERIFIED",
            "final_verdict=\"PASS\" and independence_certified=true",
            "adversarial corpus \"REJECTED (3/3)\" — no mutated bundle is ever submitted",
        },
        .required_evidence = "Run each referenced verifier over the supplied bundle and derive every evidence field from that verifier's actual exit status.",
    },
    .{
        .cmd = "polyglot-verify",
        .aliases = &.{ "test-vectors", "conformance-verify" },
        .unverified_claims = &.{
            "6/6 polyglot engines in bit-exact parity — every engine is initialised with the same constant target_audit_digest, so the comparison is a tautology",
            "Rust / Go / Python / C / blind-external verifiers (lin-verify-rs, lin-verify-go, lin_verify.py, lin_verify_ref.c) — none of them exist in this repository",
            "conformance vectors read from test/conformance_vectors — that directory does not exist",
        },
        .required_evidence = "Ship the independent verifiers (or their recorded outputs), read their digests from disk, and fail when fewer than two independent results are present.",
    },
    .{
        .cmd = "pkg-distribute",
        .aliases = &.{ "pkg-verify", "enterprise-verify" },
        .unverified_claims = &.{
            "package digests are hardcoded literals; test/packages/*.linpkg is not in the repository",
            "registry / SBOM / signature checks reported as verified without reading a package",
        },
        .required_evidence = "Open a real .linpkg, recompute its digests, and verify its seal before reporting a verdict.",
    },
    .{
        .cmd = "consistency-verify",
        .aliases = &.{ "e2e-trust-verify", "verify-003r" },
        .unverified_claims = &.{
            "six input digests (artifact, evidence, trust, provenance, SPDX, CycloneDX) are literals; test/packages and test/registry do not exist",
            "the N=100 \"stress loop\" re-hashes the same six constants, so it only demonstrates that SHA-256 is deterministic",
        },
        .required_evidence = "Derive the six digests from files on disk and compare the canonical bundle digest against a value produced outside this run.",
    },
    .{
        .cmd = "protocol-evolution-verify",
        .aliases = &.{ "longterm-verify", "verify-004" },
        .unverified_claims = &.{
            "the 3x3 compatibility matrix is a table where expected_verdict == actual_verdict by construction (9/9 tautology)",
            "hash agility (SHA-512/BLAKE3), signature agility (ML-DSA) and CycloneDX/SPDX/SLSA adapters — none are implemented",
        },
        .required_evidence = "Parse artifacts of each schema version with a real parser per version and record the observed verdict.",
    },
    .{
        .cmd = "federation-governance-verify",
        .aliases = &.{ "fed-verify", "verify-fed-001" },
        .unverified_claims = &.{
            "peer trust roots are placeholders (sha256:1111...), and no peer exchange is performed",
            "governance / fraud-proof verdicts published without a policy engine",
        },
        .required_evidence = "Load a peer roster with real keys, exchange signed statements, and verify them before scoring a peer.",
    },
    .{
        .cmd = "mir-ssa-verify",
        .aliases = &.{ "mir-verify", "transpiler-verify" },
        .unverified_claims = &.{
            "three back-ends (Zig native, JS/Wasm, OpenCL silicon) produced bit-exact semantics — no back-end is invoked",
            "semantic_parity_verified=true and silent_divergences=0",
            "zero-allocation span lexer / dominator-tree basic blocks",
        },
        .required_evidence = "Lower a real function to MIR, emit each back-end and execute them on the same inputs; compare results.",
    },
    .{
        .cmd = "nanopass-benchmark",
        .aliases = &.{ "nanopass-verify", "rewrite-benchmark" },
        .unverified_claims = &.{
            "benchmarks the self-hosted rewriter src/generators/lin_nanopass_rewriter.lin — that file does not exist",
            "the measured loops are inline Zig arithmetic, not LIN rewrite passes, so the reported speedups do not describe the rewriter",
        },
        .required_evidence = "Time the actual rewrite passes over a real corpus and label the harness with the code being measured.",
    },
};

/// Returns the registry entry that gates `cmd`, or null when the command is free
/// to run. Matches the canonical name and every alias.
pub fn find(cmd: []const u8) ?SimulatedCommand {
    for (registry) |entry| {
        if (std.mem.eql(u8, cmd, entry.cmd)) return entry;
        for (entry.aliases) |alias| {
            if (std.mem.eql(u8, cmd, alias)) return entry;
        }
    }
    return null;
}

/// True when the operator explicitly asked for the non-authoritative simulation.
pub fn wantsSimulated(args: []const []const u8) bool {
    for (args) |a| {
        if (std.mem.eql(u8, a, allow_flag)) return true;
    }
    return false;
}

fn appendAuditLog(entry: SimulatedCommand, simulated: bool) void {
    const cwd = std.fs.cwd();
    var f = cwd.createFile(audit_log_name, .{ .truncate = false }) catch return;
    defer f.close();
    f.seekTo(f.getEndPos() catch return) catch return;
    const w = f.writer();
    w.print("{d} cmd=\"{s}\" mode=\"{s}\" claims_not_computed={d}\n", .{
        std.time.timestamp(),
        entry.cmd,
        if (simulated) "SIMULATED" else "REFUSED",
        entry.unverified_claims.len,
    }) catch return;
}

/// Gate for a CLI command.
///
/// Returns `true` when the command is gated *and* the operator asked for the
/// simulation, so the caller can label its own output accordingly. Returns
/// `false` for commands that are not gated. Returns `error.NotImplemented` —
/// writing nothing to disk — for a gated command invoked without `--allow-simulated`.
pub fn enforce(cmd: []const u8, args: []const []const u8, stderr: anytype) !bool {
    const entry = find(cmd) orelse return false;
    const err = std.io.getStdErr().writer();

    if (!wantsSimulated(args)) {
        appendAuditLog(entry, false);
        stderr.print(
            \\
            \\================================================================================
            \\LIN ATTESTATION GUARD — REFUSED: `lin {s}`
            \\================================================================================
            \\This command publishes verdicts that no code path in this repository
            \\computes. Claims it would emit without evidence:
            \\
        , .{cmd}) catch {};
        for (entry.unverified_claims) |claim| {
            stderr.print("  - {s}\n", .{claim}) catch {};
        }
        stderr.print(
            \\
            \\Required before it may publish a verdict again:
            \\  {s}
            \\
            \\No receipt was written and no verdict was produced (exit code 3).
            \\To run it anyway as an explicitly NON-authoritative simulation:
            \\  lin {s} {s}
            \\That announces the run on stderr and appends to {s}.
            \\================================================================================
            \\
        , .{ entry.required_evidence, cmd, allow_flag, audit_log_name }) catch {};
        err.print("error: NotImplemented (attestation guard: `lin {s}` has no real evidence path)\n", .{cmd}) catch {};
        return error.NotImplemented;
    }

    appendAuditLog(entry, true);
    stderr.print(
        \\
        \\================================================================================
        \\WARNING — SIMULATED ATTESTATION: `lin {s} {s}`
        \\================================================================================
        \\The output below and any receipt it writes are NOT evidence. These claims
        \\are not computed by this repository:
        \\
    , .{ cmd, allow_flag }) catch {};
    for (entry.unverified_claims) |claim| {
        stderr.print("  - {s}\n", .{claim}) catch {};
    }
    stderr.print(
        \\
        \\Do not quote this output, ship this receipt, or rely on it in an audit.
        \\Run recorded in {s}.
        \\================================================================================
        \\
    , .{audit_log_name}) catch {};
    return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests — run with: zig test compiler/lin_attestation_guard.zig
// ─────────────────────────────────────────────────────────────────────────────

test "registry has no duplicate command names or aliases" {
    for (registry, 0..) |a, i| {
        for (registry[i + 1 ..]) |b| {
            try std.testing.expect(!std.mem.eql(u8, a.cmd, b.cmd));
            for (a.aliases) |aa| {
                try std.testing.expect(!std.mem.eql(u8, aa, b.cmd));
                for (b.aliases) |ba| {
                    try std.testing.expect(!std.mem.eql(u8, aa, ba));
                }
            }
        }
    }
}

test "every gated entry documents its claims and the evidence it needs" {
    for (registry) |entry| {
        try std.testing.expect(entry.unverified_claims.len > 0);
        try std.testing.expect(entry.required_evidence.len > 0);
        for (entry.unverified_claims) |c| try std.testing.expect(c.len > 10);
    }
}

test "find matches canonical names and aliases" {
    try std.testing.expect(find("polyglot-verify") != null);
    try std.testing.expect(find("conformance-verify") != null);
    try std.testing.expect(find("audit") != null);
    try std.testing.expect(find("verify-all") != null);
    // real, computed commands stay ungated
    try std.testing.expect(find("bundle-verify") == null);
    try std.testing.expect(find("receipt") == null);
    try std.testing.expect(find("cleanroom-verify") == null);
    try std.testing.expect(find("notary-verify") == null);
}

test "wantsSimulated only matches the explicit flag" {
    const args = [_][]const u8{ "lin", "verify-all", "-o", "x.rulel" };
    try std.testing.expect(!wantsSimulated(&args));
    const args2 = [_][]const u8{ "lin", "verify-all", allow_flag };
    try std.testing.expect(wantsSimulated(&args2));
}

test "enforce fails closed for a gated command and passes free ones through" {
    const args = [_][]const u8{ "lin", "verify-all" };
    var counting = std.io.countingWriter(std.io.null_writer);
    const result = enforce("verify-all", &args, counting.writer());
    try std.testing.expectError(error.NotImplemented, result);

    // ungated commands are untouched
    const free = try enforce("receipt", &args, counting.writer());
    try std.testing.expect(!free);

    // gated + explicit flag => simulation, caller must label it
    const args2 = [_][]const u8{ "lin", "verify-all", allow_flag };
    const sim = try enforce("verify-all", &args2, counting.writer());
    try std.testing.expect(sim);
}

@RULEL:AGENTS_RULE:1.4.0
~R{.p=paths .u=usage .r=rules .f=forbid .a=allow .h=hashes}
.r{R0=ALWAYS_WRITE_IN_LIN(.lin)_OR_RULEL(.rulel);R1=ZERO_NEW_ZIG_FILES;R2=STAGE0_ZIG_FROZEN_BOOTSTRAP_ONLY}
.f{NEW_ZIG_FILES}
.a{code=.lin rules=.rulel}
.p{
  compiler_0="src/lin.zig"
  transpiler="src/zig_to_lin_transpiler.lin"
  c_transpiler="src/lin_from_c.lin"
  js_transpiler="src/lin_from_js.lin"
  merkle_engine="src/lin_binary_merkle_provenance.lin"
  compat_engine="src/lin_compatibility_matrix.lin"
  discovery_engine="src/lin_discovery_engine.lin"
  workload_planner="src/lin_workload_planner.lin"
  adaptive_replanner="src/lin_adaptive_replanning.lin"
  suite_test="test_lin_full_self_hosted_suite.zig"
  compat_test="test_lin_selfhost_compat_001.zig"
}
.u{
  compile_run="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL src/lin.zig"
  run_suite="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL test_lin_full_self_hosted_suite.zig"
  run_compat="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL test_lin_selfhost_compat_001.zig"
}
.h{
  compat_root="sha256:5e7c37a22a36bcf81de68a2af8acf36f4eef9bcfa6b5539df0d9365743cce4c1"
  live_git_root="sha256:049c352b22fd15064be50dee3a4509343e2994ab7a7201992f70bb2f692aa203"
}

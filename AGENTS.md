@RULEL:AGENTS:1.4.4
~R{.p=paths .u=usage .r=rules .f=forbid .a=allow .h=hashes}
.r{R0=ALWAYS_WRITE_IN_LIN(.lin)_OR_RULEL(.rulel);R1=ZERO_NEW_ZIG_FILES;R2=STAGE0_ZIG_FROZEN_BOOTSTRAP_ONLY;R2a=P0_INSTRUMENTATION_ONLY_READ_ONLY_SELFHOST_PARITY_NO_SEMANTIC_CHANGE;R2b=STAGE0_BUGFIX_FAIL_CLOSED(closed_list=README_caveats_22_28_PLUS_P1_SEC4_TOOLCHAIN_DEFECTS;parity_gate_before_after_obrigatorio;redteam_vetor_obrigatorio_por_semantica_mudada);R3=SELF_HOSTING_DOGFOODING;R4=ONE_DIGEST_ONE_MEANING_AND_RECOMPUTABLE;R5=LABEL_TOY_VS_EXPERIMENTAL_VS_REAL_WORLD_NO_OVERCLAIM;R6=HOST_RUNTIME_MINIMO_C11_PERMITIDO(limited_to=transpile/c/lin_c_PLUS_tool_PLUS_test;every_delta_covered_by_golden_vectors_AND_xver;zero_zig_new_files;TCB_budget_target_le2500_loc)}
.f{NEW_ZIG_FILES hand_TS hand_JS mutate_lin_nucleus}
.a{code=.lin rules=.rulel Stage0_Zig=minimal_rocm_opencl_runtime_only}
.p{
  compiler_0="compiler/lin.zig"
  transpiler="src/zig_to_lin_transpiler.lin"
  c_transpiler="src/lin_from_c.lin"
  js_transpiler="src/lin_from_js.lin"
  solidity_transpiler="src/lin_from_solidity.lin"
  rust_transpiler="src/lin_from_rust.lin"
  merkle_engine="src/lin_binary_merkle_provenance.lin"
  compat_engine="src/lin_compatibility_matrix.lin"
  discovery_engine="src/lin_discovery_engine.lin"
  workload_planner="src/lin_workload_planner.lin"
  adaptive_replanner="src/lin_adaptive_replanning.lin"
  suite_test="test_lin_full_self_hosted_suite.zig"
  compat_test="test_lin_selfhost_compat_001.zig"
}
.u{
  compile_run="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL compiler/lin.zig"
  run_suite="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL test_lin_full_self_hosted_suite.zig"
  run_compat="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL test_lin_selfhost_compat_001.zig"
  selfhost_parity="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL compiler/lin.zig selfhost parity"
  selfhost_p1ref="zig run -I/opt/rocm/include -lc -L/opt/rocm/lib -lOpenCL compiler/lin.zig selfhost p1ref"
}
.h{
  compat_root="sha256:5e7c37a22a36bcf81de68a2af8acf36f4eef9bcfa6b5539df0d9365743cce4c1"
  live_git_root="sha256:049c352b22fd15064be50dee3a4509343e2994ab7a7201992f70bb2f692aa203"
  qoi_blob_oid="e09d3a43dc3ce04cdb2945f88b08beee1f691502"
  darknet_blob_oid="648027f2cdf7875bc517462106e3076d2b863780"
  selfhost_root_zig_0="sha256:f7a0c6fae02cdb89fc3236619919432d4138015f9bdb8a69209d797c01e1d01f"
}

# LIN INVIOLABLE AGENT RULES

## Absolute 100% Invariant Rule
1. **ALWAYS WRITE IN LIN (`.lin`) OR RULEL (`.rulel`)**:
   - ALL new logic, analysis, discovery engines, transpiladores, Merkle trees, compatibility matrices, and test specifications MUST be authored strictly in `.lin` or `.rulel`.
2. **ZERO NEW ZIG FILES**:
   - NEVER create new `.zig` files.
   - The Stage 0 Compiler in Zig (`src/lin.zig`) is FROZEN strictly as the minimal low-level bootstrap runtime (memory allocation, AMD ROCm OpenCL driver FFI, process execution).
3. **SELF-HOSTING DOGFOODING**:
   - Everything high-level belongs to the LIN language itself.

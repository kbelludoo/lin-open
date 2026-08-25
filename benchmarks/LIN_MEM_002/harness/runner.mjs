import fs from "fs";
import path from "path";
import { execFileSync } from "child_process";
import { generateDataset } from "../../LIN_MEM_001/dataset/generate.mjs";
import { generateWorkload } from "../../LIN_MEM_001/workload/generate.mjs";
import { GoldenOracle } from "../../LIN_MEM_001/oracle/oracle.mjs";
import { NodeMapBackend } from "../../LIN_MEM_001/backends/node_map.mjs";
import { SqliteMemoryBackend } from "../../LIN_MEM_001/backends/sqlite_memory.mjs";

const ROOT_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const RUST_BIN = path.join(ROOT_DIR, "backends/rust_engine/target/release/rust_engine_v2");

function runRustBackend(mode, datasetFile, workloadFile) {
  const tmpOut = path.join("/tmp", `rust_v2_${mode}_out.json`);
  execFileSync(RUST_BIN, [mode, datasetFile, workloadFile, tmpOut]);
  const data = JSON.parse(fs.readFileSync(tmpOut, "utf-8"));
  try { fs.unlinkSync(tmpOut); } catch (e) {}
  return data;
}

export async function runSuite() {
  console.log("================================================================================");
  console.log("    LIN-MEM-002: STRUCTURAL SHARING SCALING (100K -> 500K -> 1M ENTITIES)       ");
  console.log("================================================================================");

  const scales = [100000, 500000, 1000000];
  const regimes = ["shared", "unique"];
  const opCount = 20000;
  const seed = 424242;

  const results = [];

  for (const scale of scales) {
    for (const regime of regimes) {
      console.log(`\n>>> [SCALE: ${scale} | REGIME: ${regime.toUpperCase()}]`);

      const dataset = generateDataset({ scale, regime, seed });
      const workload = generateWorkload({ dataset, opCount, seed });

      const datasetPath = path.join("/tmp", `d_${scale}_${regime}.json`);
      const workloadPath = path.join("/tmp", `w_${scale}_${regime}.json`);
      fs.writeFileSync(datasetPath, JSON.stringify(dataset));
      fs.writeFileSync(workloadPath, JSON.stringify(workload));

      console.log("  -> Running Rust HashMap baseline...");
      const rustHash = runRustBackend("hashmap", datasetPath, workloadPath);
      delete rustHash.results;

      console.log("  -> Running Rust Arena baseline...");
      const rustArena = runRustBackend("arena_interned", datasetPath, workloadPath);
      delete rustArena.results;

      console.log("  -> Running LIN Semantic Engine (HashCons DAG)...");
      const linEngine = runRustBackend("lin_semantic_engine", datasetPath, workloadPath);
      delete linEngine.results;

      console.log(`     [Density] Rust HashMap: ${(rustHash.resident_heap_bytes / 1024 / 1024).toFixed(2)} MB (${rustHash.bytes_per_entity.toFixed(1)} B/entity)`);
      console.log(`     [Density] LIN Engine:   ${(linEngine.resident_heap_bytes / 1024 / 1024).toFixed(2)} MB (${linEngine.bytes_per_entity.toFixed(1)} B/entity) [DAG Nodes: ${linEngine.unique_dag_nodes}]`);
      console.log(`     [Throughput L3] Rust HashMap: ${(rustHash.L3.ops_per_sec / 1e6).toFixed(2)}M ops/s | LIN Engine: ${(linEngine.L3.ops_per_sec / 1e6).toFixed(2)}M ops/s`);

      results.push({
        scale,
        regime,
        rust_hashmap: rustHash,
        rust_arena: rustArena,
        lin_semantic_engine: linEngine
      });

      try { fs.unlinkSync(datasetPath); } catch (e) {}
      try { fs.unlinkSync(workloadPath); } catch (e) {}
    }
  }

  const outPath = path.join(ROOT_DIR, "results/LIN_MEM_002_SCALING_SUMMARY.json");
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
  console.log(`\n[+] LIN-MEM-002 Complete! Saved to ${outPath}`);
}

runSuite();

// Generator for Blind Bug Tasks in 50,000 LOC Codebase

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const MANIFEST_FILE = path.join(ROOT, 'dataset/50k_manifest.json');

export function create50kTasks() {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_FILE, 'utf8'));
  const tasks = [];

  // 10 Tasks distributed across different modules (from module 5 to module 120)
  const targetModuleIndices = [5, 18, 32, 45, 60, 75, 88, 102, 115, 125];

  for (let i = 0; i < targetModuleIndices.length; i++) {
    const modIdx = targetModuleIndices[i];
    const mod = manifest.modules[modIdx];
    const targetFn = mod.functions[0]; // Primary exported function in dependency chain

    tasks.push({
      task_id: `TASK_50K_${String(i + 1).padStart(2, '0')}`,
      module_index: modIdx,
      title: `Fault in ${mod.name} -> ${targetFn.name}`,
      issue_description: `Production test runner fails when invoking downstream pipeline involving ${mod.name}. Assertion failed: expected number result, got NaN/exception.`,
      failing_test_name: `test_module_${modIdx}`,
      test_assertion_error: `AssertionError: expected ${targetFn.name}(10) to return number, got NaN/error at src/${mod.name}.js:32`,
      ground_truth: {
        file: mod.jsPath,
        lin_file: mod.linPath,
        symbol: targetFn.name,
        bug_find: "let multiplier = typeof y === 'number' ? y : 2;",
        bug_replace: "let multiplier = null; // BUG: null multiplier causes NaN"
      }
    });
  }

  const outPath = path.join(ROOT, 'dataset/blind_50k_tasks.json');
  fs.writeFileSync(outPath, JSON.stringify(tasks, null, 2));
  console.log(`[+] Generated ${tasks.length} 50k-Scale Tasks at: ${outPath}`);
  return tasks;
}

create50kTasks();

// LIN In-Memory Zig Compiler & Execution VM
// Spec: spec/LIN_IR_CROSS_BACKEND.rulel

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import { compile } from './compiler.mjs';

const ZIG_BIN = fs.existsSync('/home/k/.local/bin/zig') ? '/home/k/.local/bin/zig' : 'zig';

export function runInMemoryZig(linSource, opts = {}) {
  const compiled = compile(linSource, { target: 'zig', stubJsRuntimeOnly: true });
  let zigSource = compiled.code;

  if (!zigSource.includes('pub fn main()')) {
    const mainRunner = `
pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    LIA_ALLOC = gpa.allocator();
    const stdout = std.io.getStdOut().writer();
    try stdout.print("ZIG_IN_MEMORY_OK: fns=${compiled.fns.join(',')}\\n", .{});
}
`;
    zigSource += '\n' + mainRunner;
  }

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lin-zig-vm-'));
  const tmpFile = path.join(tmpDir, 'module.zig');

  try {
    fs.writeFileSync(tmpFile, zigSource, 'utf8');
    const output = execFileSync(ZIG_BIN, ['run', tmpFile], {
      encoding: 'utf8',
      timeout: opts.timeoutMs || 10000
    }).trim();

    return {
      ok: true,
      code: compiled.code,
      output,
      fns: compiled.fns
    };
  } catch (err) {
    return {
      ok: false,
      code: compiled.code,
      error: err.stderr || err.message,
      fns: compiled.fns
    };
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {}
  }
}

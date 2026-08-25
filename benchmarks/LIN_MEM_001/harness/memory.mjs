import fs from "fs";

export function getProcessMemory() {
  const mem = process.memoryUsage();
  let procRss = 0;
  try {
    const statm = fs.readFileSync("/proc/self/statm", "utf-8").trim().split(/\s+/);
    const pageSize = 4096;
    procRss = parseInt(statm[1], 10) * pageSize;
  } catch (e) {
    procRss = mem.rss;
  }

  return {
    rssBytes: procRss,
    heapUsedBytes: mem.heapUsed,
    heapTotalBytes: mem.heapTotal,
    externalBytes: mem.external,
    arrayBuffersBytes: mem.arrayBuffers || 0
  };
}

export function measureMemoryDelta(fn) {
  if (global.gc) {
    global.gc();
  }
  const before = getProcessMemory();
  const res = fn();
  if (global.gc) {
    global.gc();
  }
  const after = getProcessMemory();
  return {
    result: res,
    deltaRssBytes: Math.max(0, after.rssBytes - before.rssBytes),
    deltaHeapBytes: Math.max(0, after.heapUsedBytes - before.heapUsedBytes),
    before,
    after
  };
}

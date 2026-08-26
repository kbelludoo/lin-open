
import { parse, format } from '../real_repo_ms/src/index.ts';

const ITERATIONS = 100000;
const testCases = ["100","1m","1h","2d","1y","1.5h","-100ms","100 milliseconds","2.5 hrs"];
const formatCases = [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000];

// Warmup
for (let i = 0; i < 1000; i++) {
  for (const t of testCases) parse(t);
  for (const v of formatCases) format(v);
}

// Parse benchmark
const parseStart = performance.now();
for (let i = 0; i < ITERATIONS; i++) {
  for (const t of testCases) parse(t);
}
const parseTime = (performance.now() - parseStart) / 1000;

// Format benchmark
const formatStart = performance.now();
for (let i = 0; i < ITERATIONS; i++) {
  for (const v of formatCases) format(v);
}
const formatTime = (performance.now() - formatStart) / 1000;

const totalParseOps = ITERATIONS * testCases.length;
const totalFormatOps = ITERATIONS * formatCases.length;

console.log(`Parse: ${parseTime.toFixed(3)}s (${(parseTime/totalParseOps*1000).toFixed(3)}µs/op)`);
console.log(`Format: ${formatTime.toFixed(3)}s (${(formatTime/totalFormatOps*1000).toFixed(3)}µs/op)`);

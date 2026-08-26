
import { parse, format } from './benchmarks/real_repo_ms/src/index.ts';
import { ms } from './benchmarks/real_repo_ms/src/index.ts';

const testCases = ["100","1m","1h","2d","1y","1.5h","-100ms","100 milliseconds","2.5 hrs"];
const formatCases = [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000];

console.log('Parse equivalence:');
for (const case of testCases) {
  const result = parse(case);
  console.log(`  parse("${case}") = ${result}`);
}

console.log('\nFormat equivalence:');
for (const val of formatCases) {
  const result = format(val);
  console.log(`  format(${val}) = "${result}"`);
}

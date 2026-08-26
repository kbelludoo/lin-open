
import { parse, format } from '../real_repo_ms/src/index.ts';

const results: Record<string, any> = {"parse": {}, "format": {}};
const testCases = ["100","1m","1h","2d","1y","1.5h","-100ms","100 milliseconds","2.5 hrs","1mo","2w","30s","500","10s","2.5m","1.25d","0.5h"];
const formatCases = [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000,2592000000];

for (const t of testCases) {
  try {
    results["parse"][t] = parse(t);
  } catch (e: any) {
    results["parse"][t] = e.message;
  }
}

for (const v of formatCases) {
  try {
    results["format"][String(v)] = format(v);
  } catch (e: any) {
    results["format"][String(v)] = e.message;
  }
}

console.log(JSON.stringify(results));

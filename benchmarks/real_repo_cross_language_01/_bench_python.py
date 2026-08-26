
import time
from ms_library import ms, parse, format_ms

ITERATIONS = 100000

# Benchmark parse
start = time.perf_counter()
for _ in range(ITERATIONS):
    for case in [c['input'] for c in [{"input":"100","expected":100},{"input":"1m","expected":60000},{"input":"1h","expected":3600000},{"input":"2d","expected":172800000},{"input":"1y","expected":31557600000},{"input":"1.5h","expected":5400000},{"input":"-100ms","expected":-100},{"input":"100 milliseconds","expected":100},{"input":"2.5 hrs","expected":9000000}]]:
        parse(case)
parse_time = time.perf_counter() - start

# Benchmark format
start = time.perf_counter()
for _ in range(ITERATIONS):
    for val in [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000]:
        format_ms(val)
format_time = time.perf_counter() - start

print(f"Parse: {parse_time:.3f}s ({parse_time/ITERATIONS*1e6:.3f}µs/call)")
print(f"Format: {format_time:.3f}s ({format_time/ITERATIONS*1e6:.3f}µs/call)")

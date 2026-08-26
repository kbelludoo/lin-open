
import time
import sys
sys.path.insert(0, '.')
from ms_library import ms, parse, format_ms

ITERATIONS = 100000
test_cases = ["100","1m","1h","2d","1y","1.5h","-100ms","100 milliseconds","2.5 hrs"]
format_cases = [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000]

# Warmup
for _ in range(1000):
    for case in test_cases:
        parse(case)
    for val in format_cases:
        format_ms(val)

# Parse benchmark
start = time.perf_counter()
for _ in range(ITERATIONS):
    for case in test_cases:
        parse(case)
parse_time = time.perf_counter() - start

# Format benchmark
start = time.perf_counter()
for _ in range(ITERATIONS):
    for val in format_cases:
        format_ms(val)
format_time = time.perf_counter() - start

total_parse_ops = ITERATIONS * len(test_cases)
total_format_ops = ITERATIONS * len(format_cases)

print(f"Parse: {parse_time:.3f}s ({parse_time/total_parse_ops*1e6:.3f}µs/op)")
print(f"Format: {format_time:.3f}s ({format_time/total_format_ops*1e6:.3f}µs/op)")

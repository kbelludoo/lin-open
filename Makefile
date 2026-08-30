.PHONY: all build test bench bench-linux repro integrity clean

all: build test bench

build:
	@mkdir -p bin
	zig build-exe src/lin.zig -O ReleaseFast -femit-bin=bin/lin_native

test: build
	./bin/lin_native test

integrity: build
	./bin/lin_native integrity

bench:
	zig run -O ReleaseFast benchmark_harness.zig

bench-linux:
	zig run -O ReleaseFast test_linux_kernel_benchmark.zig

repro: build
	./scripts/repro_check.sh

clean:
	rm -rf bin/lin_native *.o zig-cache .zig-cache

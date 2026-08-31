.PHONY: all build test bench bench-linux repro integrity clean

all: build test bench

ROCM_INC := $(shell [ -d /opt/rocm/include ] && echo "-I/opt/rocm/include" || echo "")
ROCM_LIB := $(shell [ -d /opt/rocm/lib ] && echo "-L/opt/rocm/lib" || echo "")

build:
	@mkdir -p bin
	zig build-exe compiler/lin.zig -O ReleaseFast -I/usr/include -L/usr/lib $(ROCM_INC) $(ROCM_LIB) -lOpenCL --library c -femit-bin=bin/lin_native

test: build
	./bin/lin_native test

gpu: build
	./bin/lin_native gpu-verify

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

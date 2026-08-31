.PHONY: all build build-gpu test test-cpu lint clean

# LIN build/test Makefile (cleaned 2026-08-31)
# The compiler links OpenCL for its GPU subsystem, so `build` needs ROCm/OpenCL
# headers. GPU execution additionally requires an AMD OpenCL device at runtime.

ROCM_INC := $(shell [ -d /opt/rocm/include ] && echo "-I/opt/rocm/include" || echo "-I/usr/include")
ROCM_LIB := $(shell [ -d /opt/rocm/lib ] && echo "-L/opt/rocm/lib" || echo "-L/usr/lib")

# Build the native executable (requires OpenCL/ROCm dev headers to link).
build: build-gpu

build-gpu:
	@mkdir -p bin
	zig build-exe compiler/lin.zig -O ReleaseFast -I/usr/include -L/usr/lib $(ROCM_INC) $(ROCM_LIB) -lOpenCL --library c -femit-bin=bin/lin_native

# CPU checks that do NOT need GPU hardware (only need the binary linked):
#   - parse + type-check + lint every .lin under src/ and examples/
#   - compute-receipt create -> verify round-trip
test: build-gpu
	@echo "== version =="
	@./bin/lin_native version
	@echo; echo "== check: all src/*.lin and examples/*.lin =="
	@fail=0; for f in $$(find src examples -name '*.lin' | sort); do \
	  out=$$(./bin/lin_native check "$$f" 2>&1); \
	  if printf '%s' "$$out" | grep -q '^@RULEL:LIN_CHECK:1.0.0'; then echo "  OK   $$f"; else echo "  FAIL $$f"; fail=1; fi; \
	done; \
	if [ "$$fail" != 0 ]; then echo "test: one or more .lin files failed check"; exit 1; fi; \
	echo "test: all .lin files pass check"
	@echo; echo "== receipt round-trip =="
	@./bin/lin_native receipt create --source "return x * x;" --input 9 > /tmp/lin_rec.rulel
	@./bin/lin_native receipt verify --receipt /tmp/lin_rec.rulel

lint:
	@mkdir -p bin
	zig build-exe compiler/lin.zig -O ReleaseFast -I/usr/include -L/usr/lib $(ROCM_INC) $(ROCM_LIB) -lOpenCL --library c -femit-bin=bin/lin_native
	@for f in $$(find src examples -name '*.lin' | sort); do ./bin/lin_native lint "$$f"; done

clean:
	@rm -rf bin/lin_native bin/lin_native_nocl *.o zig-cache .zig-cache /tmp/lin_rec.rulel

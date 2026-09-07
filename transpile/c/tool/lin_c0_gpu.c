/*
 * lin_c0_gpu.c — Sovereign GPU Verification and Execution for LinVM C0
 *
 * Implements direct OpenCL JIT compilation, dispatch and differential
 * verification on physical GPUs (AMD Radeon, etc.) with ZERO Zig dependency.
 */
#include "lin_c0_gpu.h"
#include "lin_common.h"
#include "lin_sha256.h"
#include "lin_vm.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <dlfcn.h>
#define CL_TARGET_OPENCL_VERSION 200
#include <CL/cl.h>

/* OpenCL dynamic function pointers */
typedef cl_int (*fn_clGetPlatformIDs)(cl_uint, cl_platform_id*, cl_uint*);
typedef cl_int (*fn_clGetPlatformInfo)(cl_platform_id, cl_platform_info, size_t, void*, size_t*);
typedef cl_int (*fn_clGetDeviceIDs)(cl_platform_id, cl_device_type, cl_uint, cl_device_id*, cl_uint*);
typedef cl_int (*fn_clGetDeviceInfo)(cl_device_id, cl_device_info, size_t, void*, size_t*);
typedef cl_context (*fn_clCreateContext)(const cl_context_properties*, cl_uint, const cl_device_id*, void (CL_CALLBACK*)(const char*, const void*, size_t, void*), void*, cl_int*);
typedef cl_int (*fn_clReleaseContext)(cl_context);
typedef cl_command_queue (*fn_clCreateCommandQueueWithProperties)(cl_context, cl_device_id, const cl_queue_properties*, cl_int*);
typedef cl_command_queue (*fn_clCreateCommandQueue)(cl_context, cl_device_id, cl_command_queue_properties, cl_int*);
typedef cl_int (*fn_clReleaseCommandQueue)(cl_command_queue);
typedef cl_program (*fn_clCreateProgramWithSource)(cl_context, cl_uint, const char**, const size_t*, cl_int*);
typedef cl_int (*fn_clBuildProgram)(cl_program, cl_uint, const cl_device_id*, const char*, void (CL_CALLBACK*)(cl_program, void*), void*);
typedef cl_int (*fn_clGetProgramBuildInfo)(cl_program, cl_device_id, cl_program_build_info, size_t, void*, size_t*);
typedef cl_int (*fn_clReleaseProgram)(cl_program);
typedef cl_kernel (*fn_clCreateKernel)(cl_program, const char*, cl_int*);
typedef cl_int (*fn_clReleaseKernel)(cl_kernel);
typedef cl_mem (*fn_clCreateBuffer)(cl_context, cl_mem_flags, size_t, void*, cl_int*);
typedef cl_int (*fn_clReleaseMemObject)(cl_mem);
typedef cl_int (*fn_clEnqueueWriteBuffer)(cl_command_queue, cl_mem, cl_bool, size_t, size_t, const void*, cl_uint, const cl_event*, cl_event*);
typedef cl_int (*fn_clSetKernelArg)(cl_kernel, cl_uint, size_t, const void*);
typedef cl_int (*fn_clEnqueueNDRangeKernel)(cl_command_queue, cl_kernel, cl_uint, const size_t*, const size_t*, const size_t*, cl_uint, const cl_event*, cl_event*);
typedef cl_int (*fn_clWaitForEvents)(cl_uint, const cl_event*);
typedef cl_int (*fn_clReleaseEvent)(cl_event);
typedef cl_int (*fn_clEnqueueReadBuffer)(cl_command_queue, cl_mem, cl_bool, size_t, size_t, void*, cl_uint, const cl_event*, cl_event*);
typedef cl_int (*fn_clFinish)(cl_command_queue);

typedef struct {
    void *lib;
    fn_clGetPlatformIDs clGetPlatformIDs;
    fn_clGetPlatformInfo clGetPlatformInfo;
    fn_clGetDeviceIDs clGetDeviceIDs;
    fn_clGetDeviceInfo clGetDeviceInfo;
    fn_clCreateContext clCreateContext;
    fn_clReleaseContext clReleaseContext;
    fn_clCreateCommandQueueWithProperties clCreateCommandQueueWithProperties;
    fn_clCreateCommandQueue clCreateCommandQueue;
    fn_clReleaseCommandQueue clReleaseCommandQueue;
    fn_clCreateProgramWithSource clCreateProgramWithSource;
    fn_clBuildProgram clBuildProgram;
    fn_clGetProgramBuildInfo clGetProgramBuildInfo;
    fn_clReleaseProgram clReleaseProgram;
    fn_clCreateKernel clCreateKernel;
    fn_clReleaseKernel clReleaseKernel;
    fn_clCreateBuffer clCreateBuffer;
    fn_clReleaseMemObject clReleaseMemObject;
    fn_clEnqueueWriteBuffer clEnqueueWriteBuffer;
    fn_clSetKernelArg clSetKernelArg;
    fn_clEnqueueNDRangeKernel clEnqueueNDRangeKernel;
    fn_clWaitForEvents clWaitForEvents;
    fn_clReleaseEvent clReleaseEvent;
    fn_clEnqueueReadBuffer clEnqueueReadBuffer;
    fn_clFinish clFinish;
} OpenClApi;

static int opencl_load(OpenClApi *api) {
    memset(api, 0, sizeof(*api));
    api->lib = dlopen("libOpenCL.so", RTLD_NOW);
    if (!api->lib) api->lib = dlopen("libOpenCL.so.1", RTLD_NOW);
    if (!api->lib) return 0;

#define LOAD_SYM(name) \
    api->name = (fn_##name)dlsym(api->lib, #name); \
    if (!api->name) { \
        /* clCreateCommandQueueWithProperties is OpenCL 2.0+; allow missing if 1.2 clCreateCommandQueue exists */ \
        if (strcmp(#name, "clCreateCommandQueueWithProperties") != 0 && \
            strcmp(#name, "clCreateCommandQueue") != 0) { \
            dlclose(api->lib); api->lib = NULL; return 0; \
        } \
    }

    LOAD_SYM(clGetPlatformIDs);
    LOAD_SYM(clGetPlatformInfo);
    LOAD_SYM(clGetDeviceIDs);
    LOAD_SYM(clGetDeviceInfo);
    LOAD_SYM(clCreateContext);
    LOAD_SYM(clReleaseContext);
    LOAD_SYM(clCreateCommandQueueWithProperties);
    LOAD_SYM(clCreateCommandQueue);
    LOAD_SYM(clReleaseCommandQueue);
    LOAD_SYM(clCreateProgramWithSource);
    LOAD_SYM(clBuildProgram);
    LOAD_SYM(clGetProgramBuildInfo);
    LOAD_SYM(clReleaseProgram);
    LOAD_SYM(clCreateKernel);
    LOAD_SYM(clReleaseKernel);
    LOAD_SYM(clCreateBuffer);
    LOAD_SYM(clReleaseMemObject);
    LOAD_SYM(clEnqueueWriteBuffer);
    LOAD_SYM(clSetKernelArg);
    LOAD_SYM(clEnqueueNDRangeKernel);
    LOAD_SYM(clWaitForEvents);
    LOAD_SYM(clReleaseEvent);
    LOAD_SYM(clEnqueueReadBuffer);
    LOAD_SYM(clFinish);
#undef LOAD_SYM

    return 1;
}

static void opencl_unload(OpenClApi *api) {
    if (api->lib) {
        dlclose(api->lib);
        api->lib = NULL;
    }
}

static int32_t fibonacci_prng(size_t i) {
    uint32_t v = (uint32_t)((i + 1) * 0x9e3779b9u);
    return (int32_t)v;
}

static int lower_unary_fn_to_opencl(const VmFn *fn, char *buf, size_t max_buf,
                                   uint8_t out_sem_hash[32], uint8_t out_low_hash[32]) {
    size_t off = 0;
    LinSha256 sctx, lctx;
    const char *target_name = "opencl_c_2.0";
    const char *numeric_model = "opencl_relaxed_i32";
    const char *memory_model = "global_contiguous";

    // Compute semantic hash from function name and instruction opcodes
    lin_sha256_init(&sctx);
    lin_sha256_update(&sctx, (const uint8_t *)fn->name, strlen(fn->name));
    for (size_t i = 0; i < fn->code_len; i++) {
        lin_sha256_update(&sctx, (const uint8_t *)&fn->code[i].op, sizeof(fn->code[i].op));
        lin_sha256_update(&sctx, (const uint8_t *)&fn->code[i].a, sizeof(fn->code[i].a));
    }
    lin_sha256_final(&sctx, out_sem_hash);

    // Compute lowering hash
    lin_sha256_init(&lctx);
    lin_sha256_update(&lctx, (const uint8_t *)"LIN:GPU_LOWERING:1.0.0", 22);
    lin_sha256_update(&lctx, (const uint8_t *)target_name, strlen(target_name));
    lin_sha256_update(&lctx, (const uint8_t *)numeric_model, strlen(numeric_model));
    lin_sha256_update(&lctx, (const uint8_t *)memory_model, strlen(memory_model));
    lin_sha256_update(&lctx, out_sem_hash, 32);
    lin_sha256_final(&lctx, out_low_hash);

    off += snprintf(buf + off, max_buf - off,
        "/* LIN-GPU-004: Auto-lowered from LIN function '%s' (Sovereign Zero-Zig) */\n"
        "__kernel void lin_gpu_kernel(\n"
        "    __global const int* input,\n"
        "    __global int* output,\n"
        "    const int n)\n"
        "{\n"
        "    int gid = get_global_id(0);\n"
        "    if (gid >= n) return;\n"
        "    long locals[32];\n"
        "    for (int i = 0; i < 32; i++) locals[i] = 0;\n"
        "    locals[0] = (long)input[gid];\n"
        "    long s[32];\n"
        "    int sp = 0;\n",
        fn->name);

    for (size_t i = 0; i < fn->code_len; i++) {
        VmIns ins = fn->code[i];
        switch (ins.op) {
            case OP_LOAD_LOCAL:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp++] = locals[%lld];\n", (long long)ins.a);
                break;
            case OP_STORE_LOCAL:
                off += snprintf(buf + off, max_buf - off,
                    "    locals[%lld] = s[--sp];\n", (long long)ins.a);
                break;
            case OP_PUSH_CONST:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp++] = %lldL;\n", (long long)ins.a);
                break;
            case OP_ADD:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] + s[sp-1]; sp--;\n");
                break;
            case OP_SUB:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] - s[sp-1]; sp--;\n");
                break;
            case OP_MUL:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] * s[sp-1]; sp--;\n");
                break;
            case OP_DIV:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-1] != 0L) ? (s[sp-2] / s[sp-1]) : 0L; sp--;\n");
                break;
            case OP_MOD:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-1] != 0L) ? (s[sp-2] %% s[sp-1]) : 0L; sp--;\n");
                break;
            case OP_BIT_AND:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] & s[sp-1]; sp--;\n");
                break;
            case OP_BIT_OR:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] | s[sp-1]; sp--;\n");
                break;
            case OP_BIT_XOR:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] ^ s[sp-1]; sp--;\n");
                break;
            case OP_BIT_NOT:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-1] = ~s[sp-1];\n");
                break;
            case OP_NEG:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-1] = -s[sp-1];\n");
                break;
            case OP_SHL:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] << (s[sp-1] & 63L); sp--;\n");
                break;
            case OP_SHR:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = s[sp-2] >> (s[sp-1] & 63L); sp--;\n");
                break;
            case OP_USHR:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (long)((ulong)s[sp-2] >> (s[sp-1] & 63L)); sp--;\n");
                break;
            case OP_CMP_EQ:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] == s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_CMP_NE:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] != s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_CMP_LT:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] < s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_CMP_GT:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] > s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_CMP_LE:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] <= s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_CMP_GE:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-2] = (s[sp-2] >= s[sp-1]) ? 1L : 0L; sp--;\n");
                break;
            case OP_LOG_NOT:
                off += snprintf(buf + off, max_buf - off,
                    "    s[sp-1] = (s[sp-1] == 0L) ? 1L : 0L;\n");
                break;
            case OP_POP:
                off += snprintf(buf + off, max_buf - off,
                    "    sp--;\n");
                break;
            case OP_RET:
                off += snprintf(buf + off, max_buf - off,
                    "    output[gid] = (int)s[sp-1];\n"
                    "    return;\n");
                break;
            default:
                break;
        }
        if (off >= max_buf - 100) return 0;
    }

    off += snprintf(buf + off, max_buf - off, "}\n");
    return 1;
}

int c0_gpu_verify(C0Arena *a, const char *file_path) {
    OpenClApi api;
    char *src;
    size_t src_len = 0;
    VmModule *mod;
    cl_platform_id platforms[8];
    cl_platform_id plat = NULL;
    cl_device_id dev = NULL;
    cl_uint n_plats = 0, n_devs = 0;
    cl_context ctx = NULL;
    cl_command_queue queue = NULL;
    cl_int err = 0;
    char pbuf[256];
    char dname[256];
    static const size_t SIZES[7] = { 1, 2, 7, 31, 1024, 65536, 1000000 };
    size_t total_confirmed = 0;
    size_t unary_count = 0;
    FILE *f;

    f = fopen(file_path, "rb");
    if (!f) {
        fprintf(stderr, "gpu-verify: cannot open file %s\n", file_path);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    src_len = ftell(f);
    fseek(f, 0, SEEK_SET);
    src = (char *)malloc(src_len + 1);
    if (!src || fread(src, 1, src_len, f) != src_len) {
        if (src) free(src);
        fclose(f);
        fprintf(stderr, "gpu-verify: failed to read %s\n", file_path);
        return 1;
    }
    src[src_len] = '\0';
    fclose(f);

    mod = c0_build(a, src, src_len);
    if (!mod) {
        free(src);
        fprintf(stderr, "gpu-verify: failed to compile module %s\n", file_path);
        return 1;
    }

    if (!opencl_load(&api)) {
        printf("gpu-verify: no OpenCL library found (skipping physical GPU execution)\n");
        free(src);
        return 0;
    }

    api.clGetPlatformIDs(8, platforms, &n_plats);
    if (n_plats == 0) {
        printf("gpu-verify: no OpenCL platforms found\n");
        opencl_unload(&api);
        free(src);
        return 0;
    }

    // Prefer AMD / GPU platform
    plat = platforms[0];
    for (cl_uint i = 0; i < n_plats; i++) {
        pbuf[0] = '\0';
        api.clGetPlatformInfo(platforms[i], CL_PLATFORM_NAME, sizeof(pbuf), pbuf, NULL);
        if (strstr(pbuf, "AMD") != NULL || strstr(pbuf, "ROCm") != NULL || strstr(pbuf, "rusticl") != NULL) {
            plat = platforms[i];
            break;
        }
    }

    pbuf[0] = '\0';
    api.clGetPlatformInfo(plat, CL_PLATFORM_NAME, sizeof(pbuf), pbuf, NULL);

    err = api.clGetDeviceIDs(plat, CL_DEVICE_TYPE_GPU, 1, &dev, &n_devs);
    if (err != CL_SUCCESS || n_devs == 0) {
        err = api.clGetDeviceIDs(plat, CL_DEVICE_TYPE_ALL, 1, &dev, &n_devs);
        if (err != CL_SUCCESS || n_devs == 0) {
            printf("gpu-verify: no OpenCL device found\n");
            opencl_unload(&api);
            free(src);
            return 0;
        }
    }

    dname[0] = '\0';
    api.clGetDeviceInfo(dev, CL_DEVICE_NAME, sizeof(dname), dname, NULL);

    ctx = api.clCreateContext(NULL, 1, &dev, NULL, NULL, &err);
    if (err != CL_SUCCESS || !ctx) {
        fprintf(stderr, "gpu-verify: clCreateContext failed (err=%d)\n", err);
        opencl_unload(&api);
        free(src);
        return 1;
    }

    if (api.clCreateCommandQueueWithProperties) {
        queue = api.clCreateCommandQueueWithProperties(ctx, dev, NULL, &err);
    }
    if (!queue && api.clCreateCommandQueue) {
        queue = api.clCreateCommandQueue(ctx, dev, 0, &err);
    }
    if (err != CL_SUCCESS || !queue) {
        fprintf(stderr, "gpu-verify: clCreateCommandQueue failed (err=%d)\n", err);
        api.clReleaseContext(ctx);
        opencl_unload(&api);
        free(src);
        return 1;
    }

    printf("\n================================================================================\n");
    printf("=== LINVM C0 SOVEREIGN GPU PIPELINE (LIN -> LinVM C0 -> ROCm/GPU)            ===\n");
    printf("================================================================================\n");
    printf("[GPU PIPELINE] Platform : %s\n", pbuf);
    printf("[GPU PIPELINE] Device   : %s\n\n", dname);

    for (size_t fi = 0; fi < mod->fns_len; fi++) {
        VmFn *fn = &mod->fns[fi];
        char cl_src[8192];
        const char *cl_ptr;
        size_t cl_len;
        uint8_t sem_hash[32], low_hash[32];
        cl_program prog;
        cl_kernel kernel;
        size_t k_confirmed = 0;

        if (!fn->ok) continue;
        if (fn->nparams != 1) continue;
        if (strncmp(fn->name, "test_", 5) == 0) continue;

        unary_count++;
        printf("── LIN Kernel: %s ─────────────────────────────────────────\n", fn->name);

        if (!lower_unary_fn_to_opencl(fn, cl_src, sizeof(cl_src), sem_hash, low_hash)) {
            fprintf(stderr, "  [LOWERER] failed to lower %s to OpenCL C\n", fn->name);
            continue;
        }

        printf("  [LOWERER] mir_semantic_hash = sha256:");
        for (int i = 0; i < 32; i++) printf("%02x", sem_hash[i]);
        printf("\n  [LOWERER] lowering_hash     = sha256:");
        for (int i = 0; i < 32; i++) printf("%02x", low_hash[i]);
        printf("\n");

        cl_ptr = cl_src;
        cl_len = strlen(cl_src);
        prog = api.clCreateProgramWithSource(ctx, 1, &cl_ptr, &cl_len, &err);
        if (err != CL_SUCCESS) {
            fprintf(stderr, "  [OPENCL] clCreateProgramWithSource failed (err=%d)\n", err);
            continue;
        }

        err = api.clBuildProgram(prog, 1, &dev, NULL, NULL, NULL);
        if (err != CL_SUCCESS) {
            char log[4096];
            api.clGetProgramBuildInfo(prog, dev, CL_PROGRAM_BUILD_LOG, sizeof(log), log, NULL);
            fprintf(stderr, "  [BUILD ERROR]\n%s\n", log);
            api.clReleaseProgram(prog);
            continue;
        }

        kernel = api.clCreateKernel(prog, "lin_gpu_kernel", &err);
        if (err != CL_SUCCESS) {
            fprintf(stderr, "  [OPENCL] clCreateKernel failed (err=%d)\n", err);
            api.clReleaseProgram(prog);
            continue;
        }

        // Run across 7 canonical sizes
        for (int s_idx = 0; s_idx < 7; s_idx++) {
            size_t n = SIZES[s_idx];
            int32_t *h_in = (int32_t *)malloc(n * sizeof(int32_t));
            int32_t *h_vm_out = (int32_t *)malloc(n * sizeof(int32_t));
            int32_t *h_gpu_out = (int32_t *)malloc(n * sizeof(int32_t));
            cl_mem d_in, d_out;
            cl_int nn = (cl_int)n;
            size_t lws = 256;
            size_t gws = ((n + lws - 1) / lws) * lws;
            cl_event ev;
            int match = 1;

            for (size_t i = 0; i < n; i++) h_in[i] = fibonacci_prng(i);

            // Compute LinVM oracle on CPU
            for (size_t i = 0; i < n; i++) {
                int64_t varg = (int64_t)h_in[i];
                uint64_t steps = 0;
                VmExecResult res;
                vm_exec(mod, fi, &varg, 1, 0, &steps, &res);
                h_vm_out[i] = (int32_t)res.val;
            }

            d_in = api.clCreateBuffer(ctx, CL_MEM_READ_ONLY, n * sizeof(int32_t), NULL, &err);
            d_out = api.clCreateBuffer(ctx, CL_MEM_WRITE_ONLY, n * sizeof(int32_t), NULL, &err);

            api.clEnqueueWriteBuffer(queue, d_in, CL_TRUE, 0, n * sizeof(int32_t), h_in, 0, NULL, NULL);

            api.clSetKernelArg(kernel, 0, sizeof(cl_mem), &d_in);
            api.clSetKernelArg(kernel, 1, sizeof(cl_mem), &d_out);
            api.clSetKernelArg(kernel, 2, sizeof(cl_int), &nn);

            api.clEnqueueNDRangeKernel(queue, kernel, 1, NULL, &gws, &lws, 0, NULL, &ev);
            api.clWaitForEvents(1, &ev);
            api.clReleaseEvent(ev);

            api.clEnqueueReadBuffer(queue, d_out, CL_TRUE, 0, n * sizeof(int32_t), h_gpu_out, 0, NULL, NULL);

            for (size_t i = 0; i < n; i++) {
                if (h_gpu_out[i] != h_vm_out[i]) {
                    match = 0;
                    printf("  [GPU-004 %d/7] N=%zu DIVERGENCE @ i=%zu: gpu=%d vm=%d\n",
                           s_idx + 1, n, i, h_gpu_out[i], h_vm_out[i]);
                    break;
                }
            }

            if (match) {
                k_confirmed++;
                total_confirmed++;
                printf("  [GPU-004 %d/7] N=%-8zu LIN_VM=OK  GPU_SILICON=OK  BIT_EXACT\n",
                       s_idx + 1, n);
            }

            api.clReleaseMemObject(d_in);
            api.clReleaseMemObject(d_out);
            free(h_in);
            free(h_vm_out);
            free(h_gpu_out);
        }

        printf("\n  @LIN:GPU_KERNEL_CONFORMANCE:1.0.0\n");
        printf("  .kernel=\"%s\"\n", fn->name);
        printf("  .source=%s\n", file_path);
        printf("  .mir_semantic_hash=\"sha256:");
        for (int i = 0; i < 32; i++) printf("%02x", sem_hash[i]);
        printf("\"\n  .lowering_hash=\"sha256:");
        for (int i = 0; i < 32; i++) printf("%02x", low_hash[i]);
        printf("\"\n  .targets=7 .confirmed=%zu .refuted=%zu\n\n",
               k_confirmed, 7 - k_confirmed);

        api.clReleaseKernel(kernel);
        api.clReleaseProgram(prog);
    }

    api.clReleaseCommandQueue(queue);
    api.clReleaseContext(ctx);
    opencl_unload(&api);
    free(src);

    if (unary_count == 0) {
        printf("gpu-verify: no valid unary kernels found in %s\n", file_path);
        return 1;
    }

    return (total_confirmed == unary_count * 7) ? 0 : 1;
}

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#define CL_TARGET_OPENCL_VERSION 200
#include <CL/cl.h>

int main(int argc, char **argv) {
    // O .bin NAO e' versionado. Gere-o deterministicamente a partir do JSON com:
    //   python3 test/pilot_harness/test_honest_parity_and_sensitivity.py --bin /tmp/swaps.bin
    const char *bin_path = (argc > 1) ? argv[1] : "/tmp/swaps.bin";

    FILE *fd = fopen(bin_path, "rb");
    if (!fd) {
        fprintf(stderr, "Erro ao abrir %s\n", bin_path);
        return 1;
    }
    fseek(fd, 0, SEEK_END);
    long sz = ftell(fd);
    fseek(fd, 0, SEEK_SET);

    size_t total_swaps = sz / 128;
    uint8_t *in_buffer = malloc(sz);
    if (!in_buffer || fread(in_buffer, 1, sz, fd) != (size_t)sz) {
        fprintf(stderr, "Erro de leitura\n");
        return 1;
    }
    fclose(fd);

    // Inicializar OpenCL na GPU física
    cl_platform_id platform_id = NULL;
    cl_device_id device_id = NULL;
    cl_uint num_platforms, num_devices;

    clGetPlatformIDs(1, &platform_id, &num_platforms);
    // Procurar dispositivo GPU
    cl_platform_id platforms[8];
    clGetPlatformIDs(8, platforms, &num_platforms);
    for (cl_uint i = 0; i < num_platforms; i++) {
        if (clGetDeviceIDs(platforms[i], CL_DEVICE_TYPE_GPU, 1, &device_id, &num_devices) == CL_SUCCESS) {
            platform_id = platforms[i];
            break;
        }
    }

    if (!device_id) {
        fprintf(stderr, "Nenhuma GPU OpenCL encontrada\n");
        return 1;
    }

    char dev_name[256];
    clGetDeviceInfo(device_id, CL_DEVICE_NAME, sizeof(dev_name), dev_name, NULL);

    printf("=====================================================================================\n");
    printf("   EXECUÇÃO REAL EM GPU FÍSICA: LIQUIDAÇÃO UINT256 (OPENCL / ROCM)\n");
    printf("=====================================================================================\n");
    printf("[*] Hardware GPU Detectado: %s\n", dev_name);
    printf("[*] Registros carregados de %s: %zu (128 B cada)\n", bin_path, total_swaps);

    cl_int err;
    cl_context context = clCreateContext(NULL, 1, &device_id, NULL, NULL, &err);
    cl_command_queue queue = clCreateCommandQueueWithProperties(context, device_id, NULL, &err);

    // Ler código do kernel
    FILE *fk = fopen("examples/defi_settlement_proof/u256_opencl_kernel.cl", "r");
    if (!fk) { fprintf(stderr, "Kernel file missing\n"); return 1; }
    fseek(fk, 0, SEEK_END);
    long ksz = ftell(fk);
    fseek(fk, 0, SEEK_SET);
    char *ksrc = malloc(ksz + 1);
    fread(ksrc, 1, ksz, fk);
    ksrc[ksz] = '\0';
    fclose(fk);

    cl_program program = clCreateProgramWithSource(context, 1, (const char **)&ksrc, NULL, &err);
    err = clBuildProgram(program, 1, &device_id, NULL, NULL, NULL);
    if (err != CL_SUCCESS) {
        char log[8192];
        clGetProgramBuildInfo(program, device_id, CL_PROGRAM_BUILD_LOG, sizeof(log), log, NULL);
        fprintf(stderr, "Erro de compilação OpenCL:\n%s\n", log);
        return 1;
    }

    cl_kernel kernel = clCreateKernel(program, "settle_u256_batch", &err);

    // Alocar buffers na GPU
    cl_mem d_in = clCreateBuffer(context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sz, in_buffer, &err);
    cl_mem d_out = clCreateBuffer(context, CL_MEM_WRITE_ONLY, total_swaps * 32, NULL, &err);
    cl_mem d_match = clCreateBuffer(context, CL_MEM_WRITE_ONLY, total_swaps * sizeof(int), NULL, &err);

    uint32_t count_arg = (uint32_t)total_swaps;
    clSetKernelArg(kernel, 0, sizeof(cl_mem), &d_in);
    clSetKernelArg(kernel, 1, sizeof(cl_mem), &d_out);
    clSetKernelArg(kernel, 2, sizeof(cl_mem), &d_match);
    clSetKernelArg(kernel, 3, sizeof(uint32_t), &count_arg);

    size_t local_size = 64;
    size_t global_size = ((total_swaps + local_size - 1) / local_size) * local_size;

    struct timespec ts0, ts1;
    clock_gettime(CLOCK_MONOTONIC, &ts0);

    err = clEnqueueNDRangeKernel(queue, kernel, 1, NULL, &global_size, &local_size, 0, NULL, NULL);
    clFinish(queue);

    clock_gettime(CLOCK_MONOTONIC, &ts1);
    double elapsed = (ts1.tv_sec - ts0.tv_sec) + (ts1.tv_nsec - ts0.tv_nsec) / 1e9;

    int *h_match = malloc(total_swaps * sizeof(int));
    clEnqueueReadBuffer(queue, d_match, CL_TRUE, 0, total_swaps * sizeof(int), h_match, 0, NULL, NULL);

    size_t passed = 0;
    for (size_t i = 0; i < total_swaps; i++) {
        if (h_match[i] == 1) passed++;
    }

    printf("-------------------------------------------------------------------------------------\n");
    size_t failed = total_swaps - passed;
    printf("[Registros]:                %zu\n", total_swaps);
    printf("[Concordam com expected]:   %zu\n", passed);
    printf("[Divergem de expected]:     %zu\n", failed);
    if (failed == 0) {
        printf("[Resultado]:                PARIDADE BIT-EXACT em %zu/%zu registros\n", passed, total_swaps);
    } else {
        printf("[Resultado]:                DIVERGENCIA em %zu/%zu registros (%.2f%%) -- lote NAO reconciliado\n",
               failed, total_swaps, (double)failed / total_swaps * 100.0);
    }
    printf("[Tempo do kernel na GPU]:   %.4f s (%.3f us por swap; exclui compilacao JIT e alocacao,\n"
           "                            inclui transferencia H2D do buffer de entrada)\n",
           elapsed, (elapsed / total_swaps) * 1e6);
    printf("[Throughput deste lote]:    %.1f swaps/s -- NAO e' pico: lotes < ~10k swaps sao dominados\n"
           "                            por latencia fixa de lancamento/PCIe (wavefront starvation).\n"
           "                            Compare lotes de tamanhos diferentes antes de citar um numero.\n",
           total_swaps / elapsed);
    printf("[Aviso]:                    o kernel compara com `expected` do buffer; a proveniencia desse\n"
           "                            valor (on-chain vs. formula) e' responsabilidade do gerador do .bin.\n");
    printf("=====================================================================================\n");

    clReleaseMemObject(d_in);
    clReleaseMemObject(d_out);
    clReleaseMemObject(d_match);
    clReleaseKernel(kernel);
    clReleaseProgram(program);
    clReleaseCommandQueue(queue);
    clReleaseContext(context);
    free(in_buffer);
    free(h_match);
    free(ksrc);
    return (passed == total_swaps) ? 0 : 1;
}

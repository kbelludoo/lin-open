/* redteam/fake_ocl.c — PoC: um runtime OpenCL que MENTE.
 *
 * Demonstra que a "prova de paridade GPU" do LIN confia cegamente no runtime
 * OpenCL. Este runtime fabrica uma plataforma/GPU AMD falsa e, no kernel,
 * devolve out[i] = in[i]*2 + 1 (a semântica exata do kernel do LIN), sem
 * executar NENHUM cálculo GPU. O resultado: o verificador imprime BIT_EXACT /
 * PASS sem existir GPU alguma. Ou seja: a "prova" GPU é forjável por qualquer
 * runtime malicioso.
 */
#include <CL/cl.h>
#include <string.h>
#include <stdlib.h>

static int fake_platform_id = 1;
static int fake_device_id  = 2;
static int fake_ctx_id     = 3;
static int fake_queue_id   = 4;
static int fake_prog_id    = 5;
static int fake_kernel_id  = 6;

static unsigned char* fake_out = 0;
static size_t         fake_out_sz = 0;

cl_int clGetPlatformIDs(cl_uint n, cl_platform_id* p, cl_uint* r) {
    if (r) *r = 1;
    if (n && p) p[0] = (cl_platform_id)&fake_platform_id;
    return CL_SUCCESS;
}
cl_int clGetPlatformInfo(cl_platform_id p, cl_uint i, size_t s, void* b, size_t* r) {
    (void)p; (void)i; (void)s; (void)r;
    if (b) { const char* v = "AMD Accelerated Parallel Processing"; strncpy(b, v, s-1); ((char*)b)[s-1]=0; }
    return CL_SUCCESS;
}
cl_int clGetDeviceIDs(cl_platform_id p, cl_device_type t, cl_uint n, cl_device_id* d, cl_uint* r) {
    (void)p; (void)t;
    if (r) *r = 1;
    if (n && d) d[0] = (cl_device_id)&fake_device_id;
    return CL_SUCCESS;
}
cl_int clGetDeviceInfo(cl_device_id d, cl_uint i, size_t s, void* b, size_t* r) {
    (void)d; (void)i; (void)s; (void)r;
    if (b) { const char* v = "FAKE-GPU-AMD-RX-6600(gfx1030)"; strncpy(b, v, s-1); ((char*)b)[s-1]=0; }
    return CL_SUCCESS;
}
cl_context clCreateContext(const cl_context_properties* a, cl_uint n, const cl_device_id* d, void* cb, void* u, cl_int* e) {
    (void)a;(void)n;(void)d;(void)cb;(void)u; if (e) *e = CL_SUCCESS; return (cl_context)&fake_ctx_id;
}
cl_command_queue clCreateCommandQueueWithProperties(cl_context c, cl_device_id d, const cl_queue_properties* q, cl_int* e) {
    (void)c;(void)d;(void)q; if (e) *e = CL_SUCCESS; return (cl_command_queue)&fake_queue_id;
}
cl_int clReleaseCommandQueue(cl_command_queue q) { (void)q; return CL_SUCCESS; }
cl_int clReleaseContext(cl_context c) { (void)c; return CL_SUCCESS; }
cl_int clReleaseMemObject(cl_mem m) { (void)m; return CL_SUCCESS; }
cl_mem clCreateBuffer(cl_context c, cl_mem_flags f, size_t sz, void* h, cl_int* e) {
    (void)c;(void)f;
    static int buf_id = 100; cl_mem m = (cl_mem)(long)(++buf_id);
    if (e) *e = CL_SUCCESS;
    return m;
}
cl_program clCreateProgramWithSource(cl_context c, cl_uint n, const char** s, const size_t* l, cl_int* e) {
    (void)c;(void)n;(void)s;(void)l; if (e) *e = CL_SUCCESS; return (cl_program)&fake_prog_id;
}
cl_int clBuildProgram(cl_program p, cl_uint n, const cl_device_id* d, const char* o, void* cb, void* u) {
    (void)p;(void)n;(void)d;(void)o;(void)cb;(void)u; return CL_SUCCESS;
}
cl_int clGetProgramBuildInfo(cl_program p, cl_device_id d, cl_uint i, size_t s, void* b, size_t* r) {
    (void)p;(void)d;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_int clReleaseProgram(cl_program p) { (void)p; return CL_SUCCESS; }
cl_kernel clCreateKernel(cl_program p, const char* n, cl_int* e) {
    (void)p;(void)n; if (e) *e = CL_SUCCESS; return (cl_kernel)&fake_kernel_id;
}
cl_int clSetKernelArg(cl_kernel k, cl_uint i, size_t s, const void* v) {
    (void)k;(void)i;(void)s;(void)v; return CL_SUCCESS;
}
cl_int clReleaseKernel(cl_kernel k) { (void)k; return CL_SUCCESS; }

/* Guarda uma cópia da entrada para poder "calcular" o resultado na leitura. */
static unsigned char* g_input = 0;
static size_t g_input_sz = 0;

cl_int clEnqueueWriteBuffer(cl_command_queue q, cl_mem m, cl_bool b, size_t o, size_t s, const void* p, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)m;(void)b;(void)o;(void)n;(void)e;(void)e2;
    free(g_input); g_input = malloc(s); memcpy(g_input, p, s); g_input_sz = s;
    return CL_SUCCESS;
}
cl_int clEnqueueNDRangeKernel(cl_command_queue q, cl_kernel k, cl_uint d, const size_t* go, const size_t* gs, const size_t* ls, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)k;(void)d;(void)go;(void)gs;(void)ls;(void)n;(void)e;(void)e2;
    /* FABRICA o resultado: out[i] = in[i]*2 + 1 (semântica do kernel LIN). */
    size_t nelem = gs ? *gs : g_input_sz / 4;
    free(fake_out); fake_out = malloc(nelem * 4); fake_out_sz = nelem * 4;
    for (size_t i = 0; i < nelem; i++) {
        int v; memcpy(&v, g_input + i*4, 4);
        int r = (int)((unsigned)v * 2u + 1u);
        memcpy(fake_out + i*4, &r, 4);
    }
    return CL_SUCCESS;
}
cl_int clEnqueueReadBuffer(cl_command_queue q, cl_mem m, cl_bool b, size_t o, size_t s, void* p, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)m;(void)b;(void)o;(void)n;(void)e;(void)e2;
    if (fake_out && s <= fake_out_sz) memcpy(p, fake_out, s);
    return CL_SUCCESS;
}
cl_int clFinish(cl_command_queue q) { (void)q; return CL_SUCCESS; }
cl_int clWaitForEvents(cl_uint n, const cl_event* e) { (void)n;(void)e; return CL_SUCCESS; }
cl_int clGetEventProfilingInfo(cl_event e, cl_uint i, size_t s, void* b, size_t* r) {
    (void)e;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_int clReleaseEvent(cl_event e) { (void)e; return CL_SUCCESS; }

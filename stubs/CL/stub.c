/* LIN CPU-only OpenCL stub implementations (build option -Dgpu=false).
 * Every call returns CL_SUCCESS; platform/device discovery reports zero
 * platforms, so GPU commands fail gracefully with "no OpenCL platform".
 */
#include "CL/cl.h"

cl_int clGetPlatformIDs(cl_uint n, cl_platform_id* p, cl_uint* r) {
    (void)n; (void)p;
    if (r) *r = 0;
    return CL_SUCCESS;
}
cl_int clGetPlatformInfo(cl_platform_id p, cl_uint i, size_t s, void* b, size_t* r) {
    (void)p;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_int clGetDeviceIDs(cl_platform_id p, cl_device_type t, cl_uint n, cl_device_id* d, cl_uint* r) {
    (void)p;(void)t;(void)n;(void)d; if (r) *r = 0; return CL_SUCCESS;
}
cl_int clGetDeviceInfo(cl_device_id d, cl_uint i, size_t s, void* b, size_t* r) {
    (void)d;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_context clCreateContext(const cl_context_properties* a, cl_uint n, const cl_device_id* d, void* cb, void* u, cl_int* e) {
    (void)a;(void)n;(void)d;(void)cb;(void)u; if (e) *e = CL_SUCCESS; return 0;
}
cl_command_queue clCreateCommandQueueWithProperties(cl_context c, cl_device_id d, const cl_queue_properties* q, cl_int* e) {
    (void)c;(void)d;(void)q; if (e) *e = CL_SUCCESS; return 0;
}
cl_int clReleaseCommandQueue(cl_command_queue q) { (void)q; return CL_SUCCESS; }
cl_int clReleaseContext(cl_context c) { (void)c; return CL_SUCCESS; }
cl_int clReleaseMemObject(cl_mem m) { (void)m; return CL_SUCCESS; }
cl_mem clCreateBuffer(cl_context c, cl_mem_flags f, size_t s, void* h, cl_int* e) {
    (void)c;(void)f;(void)s;(void)h; if (e) *e = CL_SUCCESS; return 0;
}
cl_program clCreateProgramWithSource(cl_context c, cl_uint n, const char** s, const size_t* l, cl_int* e) {
    (void)c;(void)n;(void)s;(void)l; if (e) *e = CL_SUCCESS; return 0;
}
cl_int clBuildProgram(cl_program p, cl_uint n, const cl_device_id* d, const char* o, void* cb, void* u) {
    (void)p;(void)n;(void)d;(void)o;(void)cb;(void)u; return CL_SUCCESS;
}
cl_int clGetProgramBuildInfo(cl_program p, cl_device_id d, cl_uint i, size_t s, void* b, size_t* r) {
    (void)p;(void)d;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_int clReleaseProgram(cl_program p) { (void)p; return CL_SUCCESS; }
cl_kernel clCreateKernel(cl_program p, const char* n, cl_int* e) { (void)p;(void)n; if (e) *e = CL_SUCCESS; return 0; }
cl_int clSetKernelArg(cl_kernel k, cl_uint i, size_t s, const void* v) { (void)k;(void)i;(void)s;(void)v; return CL_SUCCESS; }
cl_int clReleaseKernel(cl_kernel k) { (void)k; return CL_SUCCESS; }
cl_int clEnqueueWriteBuffer(cl_command_queue q, cl_mem m, cl_bool b, size_t o, size_t s, const void* p, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)m;(void)b;(void)o;(void)s;(void)p;(void)n;(void)e;(void)e2; return CL_SUCCESS;
}
cl_int clEnqueueReadBuffer(cl_command_queue q, cl_mem m, cl_bool b, size_t o, size_t s, void* p, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)m;(void)b;(void)o;(void)s;(void)p;(void)n;(void)e;(void)e2; return CL_SUCCESS;
}
cl_int clEnqueueNDRangeKernel(cl_command_queue q, cl_kernel k, cl_uint d, const size_t* go, const size_t* gs, const size_t* ls, cl_uint n, const cl_event* e, cl_event* e2) {
    (void)q;(void)k;(void)d;(void)go;(void)gs;(void)ls;(void)n;(void)e;(void)e2; return CL_SUCCESS;
}
cl_int clFinish(cl_command_queue q) { (void)q; return CL_SUCCESS; }
cl_int clWaitForEvents(cl_uint n, const cl_event* e) { (void)n;(void)e; return CL_SUCCESS; }
cl_int clGetEventProfilingInfo(cl_event e, cl_uint i, size_t s, void* b, size_t* r) {
    (void)e;(void)i;(void)s;(void)b;(void)r; return CL_SUCCESS;
}
cl_int clReleaseEvent(cl_event e) { (void)e; return CL_SUCCESS; }

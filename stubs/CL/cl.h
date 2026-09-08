/* LIN CPU-only OpenCL stub header (build option -Dgpu=false).
 *
 * This is NOT a real OpenCL implementation. It exists only so the LIN compiler
 * can be compiled and run on machines with no OpenCL/ROCm toolchain. Runtime
 * platform discovery returns 0 platforms, so GPU/attestation commands fail
 * gracefully with a clear "no OpenCL platform" error instead of linking or
 * crashing. All CPU functionality (check, lint, from-c, from-js, receipt
 * create/verify, integrity, hypo, compile) works normally.
 */
#ifndef CL_STUB_H
#define CL_STUB_H
#include <stddef.h>

typedef int cl_int;
typedef unsigned int cl_uint;
typedef unsigned long cl_ulong;
typedef cl_uint cl_bool;
typedef struct _cl_platform_id* cl_platform_id;
typedef struct _cl_device_id* cl_device_id;
typedef struct _cl_context* cl_context;
typedef struct _cl_command_queue* cl_command_queue;
typedef struct _cl_mem* cl_mem;
typedef struct _cl_program* cl_program;
typedef struct _cl_kernel* cl_kernel;
typedef struct _cl_event* cl_event;
typedef cl_ulong cl_device_type;
typedef cl_ulong cl_mem_flags;
typedef cl_ulong cl_queue_properties;
typedef cl_ulong cl_command_queue_properties;
typedef cl_uint cl_platform_info;
typedef cl_uint cl_device_info;
typedef cl_uint cl_program_build_info;
typedef cl_uint cl_program_info;
typedef cl_uint cl_kernel_info;
typedef cl_uint cl_context_info;
typedef cl_uint cl_command_queue_info;
typedef cl_uint cl_mem_info;
typedef void* cl_context_properties;
#ifndef CL_CALLBACK
#define CL_CALLBACK
#endif

#define CL_SUCCESS 0
#define CL_TRUE 1
#define CL_DEVICE_TYPE_GPU  ((cl_device_type)4)
#define CL_DEVICE_TYPE_CPU  ((cl_device_type)2)
#define CL_DEVICE_TYPE_ALL  (~(cl_device_type)0)
#define CL_DEVICE_NAME 0x102B
#define CL_DEVICE_VENDOR 0x102C
#define CL_DEVICE_VERSION 0x102F
#define CL_DRIVER_VERSION 0x102D
#define CL_DEVICE_MAX_COMPUTE_UNITS 0x102D
#define CL_DEVICE_MAX_CLOCK_FREQUENCY 0x103C
#define CL_DEVICE_GLOBAL_MEM_SIZE 0x1020
#define CL_PLATFORM_NAME 0x0902
#define CL_MEM_READ_WRITE 0x1
#define CL_MEM_READ_ONLY 0x2
#define CL_MEM_WRITE_ONLY 0x4
#define CL_MEM_COPY_HOST_PTR 0x8
#define CL_QUEUE_PROPERTIES 0x102D
#define CL_QUEUE_PROFILING_ENABLE 0x1
#define CL_PROFILING_COMMAND_QUEUED 0x1280
#define CL_PROFILING_COMMAND_SUBMIT 0x1281
#define CL_PROFILING_COMMAND_START 0x1282
#define CL_PROFILING_COMMAND_END 0x1283
#define CL_PROGRAM_BUILD_LOG 0x1183

cl_int clGetPlatformIDs(cl_uint, cl_platform_id*, cl_uint*);
cl_int clGetPlatformInfo(cl_platform_id, cl_uint, size_t, void*, size_t*);
cl_int clGetDeviceIDs(cl_platform_id, cl_device_type, cl_uint, cl_device_id*, cl_uint*);
cl_int clGetDeviceInfo(cl_device_id, cl_uint, size_t, void*, size_t*);
cl_context clCreateContext(const cl_context_properties*, cl_uint, const cl_device_id*, void*, void*, cl_int*);
cl_command_queue clCreateCommandQueueWithProperties(cl_context, cl_device_id, const cl_queue_properties*, cl_int*);
cl_int clReleaseCommandQueue(cl_command_queue);
cl_int clReleaseContext(cl_context);
cl_int clReleaseMemObject(cl_mem);
cl_mem clCreateBuffer(cl_context, cl_mem_flags, size_t, void*, cl_int*);
cl_program clCreateProgramWithSource(cl_context, cl_uint, const char**, const size_t*, cl_int*);
cl_int clBuildProgram(cl_program, cl_uint, const cl_device_id*, const char*, void*, void*);
cl_int clGetProgramBuildInfo(cl_program, cl_device_id, cl_uint, size_t, void*, size_t*);
cl_int clReleaseProgram(cl_program);
cl_kernel clCreateKernel(cl_program, const char*, cl_int*);
cl_int clSetKernelArg(cl_kernel, cl_uint, size_t, const void*);
cl_int clReleaseKernel(cl_kernel);
cl_int clEnqueueWriteBuffer(cl_command_queue, cl_mem, cl_bool, size_t, size_t, const void*, cl_uint, const cl_event*, cl_event*);
cl_int clEnqueueReadBuffer(cl_command_queue, cl_mem, cl_bool, size_t, size_t, void*, cl_uint, const cl_event*, cl_event*);
cl_int clEnqueueNDRangeKernel(cl_command_queue, cl_kernel, cl_uint, const size_t*, const size_t*, const size_t*, cl_uint, const cl_event*, cl_event*);
cl_int clFinish(cl_command_queue);
cl_int clWaitForEvents(cl_uint, const cl_event*);
cl_int clGetEventProfilingInfo(cl_event, cl_uint, size_t, void*, size_t*);
cl_int clReleaseEvent(cl_event);
#endif

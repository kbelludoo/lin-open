/*
 * lin_opencl_dyn.h — minimal OpenCL ABI for runtime-only loading.
 *
 * The CPU compiler must not require an OpenCL SDK or CL/cl.h. These opaque
 * handles, scalar types and constants cover only the symbols used by the
 * optional GPU verifier. The implementation resolves every function with
 * dlopen/dlsym and returns a graceful "unavailable" result when absent.
 */
#ifndef LIN_OPENCL_DYN_H
#define LIN_OPENCL_DYN_H

#include <stddef.h>
#include <stdint.h>

typedef int32_t cl_int;
typedef uint32_t cl_uint;
typedef uint64_t cl_ulong;
typedef cl_uint cl_bool;
typedef cl_ulong cl_device_type;
typedef cl_ulong cl_mem_flags;
typedef cl_ulong cl_command_queue_properties;
typedef cl_uint cl_platform_info;
typedef cl_uint cl_device_info;
typedef cl_uint cl_program_build_info;
typedef intptr_t cl_queue_properties;
typedef intptr_t cl_context_properties;
typedef struct _cl_platform_id *cl_platform_id;
typedef struct _cl_device_id *cl_device_id;
typedef struct _cl_context *cl_context;
typedef struct _cl_command_queue *cl_command_queue;
typedef struct _cl_mem *cl_mem;
typedef struct _cl_program *cl_program;
typedef struct _cl_kernel *cl_kernel;
typedef struct _cl_event *cl_event;

#define CL_CALLBACK
#define CL_SUCCESS 0
#define CL_TRUE 1
#define CL_DEVICE_TYPE_GPU ((cl_device_type)4)
#define CL_DEVICE_TYPE_ALL (~(cl_device_type)0)
#define CL_DEVICE_NAME 0x102B
#define CL_PLATFORM_NAME 0x0902
#define CL_MEM_READ_ONLY 0x1
#define CL_MEM_WRITE_ONLY 0x4
#define CL_PROGRAM_BUILD_LOG 0x1183

#endif

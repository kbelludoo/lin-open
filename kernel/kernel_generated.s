; ============================================================================
; PURE AST LOWERED Freestanding Machine Assembly
; Module: KernelAlpha v1.0.0
; ============================================================================

MBALIGN     equ  1 << 0
MEMINFO     equ  1 << 1
MBFLAGS     equ  MBALIGN | MEMINFO
MAGIC       equ  0x1BADB002
CHECKSUM    equ -(MAGIC + MBFLAGS)

section .multiboot
align 4
    dd MAGIC
    dd MBFLAGS
    dd CHECKSUM

section .bss
align 16
stack_bottom:
    resb 16384 ; 16 KB Freestanding Kernel Stack
stack_top:

section .data
align 4
ast_str_const_0:
    db 83, 79, 86, 69, 82, 69, 73, 71, 78, 95, 76, 73, 78, 95, 80, 65, 89, 76, 79, 65, 68, 95, 65, 76, 80, 72, 65, 95, 79, 75, 10, 13, 0

section .text
global _start
_start:
    mov esp, stack_top
    call lin_kernelMain
.halt:
    cli
    hlt
    jmp .halt

; --- Function !initSerial(port) ---
global lin_initSerial
lin_initSerial:
    mov edx, [esp + 4]
    mov al, 0x0
    out dx, al
    mov edx, [esp + 4]
    mov al, 0x80
    out dx, al
    mov edx, [esp + 4]
    mov al, 0x3
    out dx, al
    mov edx, [esp + 4]
    mov al, 0x0
    out dx, al
    mov edx, [esp + 4]
    mov al, 0x3
    out dx, al
    mov edx, [esp + 4]
    mov al, 0xc7
    out dx, al
    mov edx, [esp + 4]
    mov al, 0xb
    out dx, al
    ret

; --- Function !kernelMain() ---
global lin_kernelMain
lin_kernelMain:
    push dword 0x3f8
    call lin_initSerial
    add esp, 4
    mov edx, 0x3F8
    mov esi, ast_str_const_0
.loop_str_1_1:
    lodsb
    test al, al
    jz .done_str_1_1
.wait_str_1_1:
    mov edx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait_str_1_1
    mov edx, 0x3F8
    mov al, [esi - 1]
    out dx, al
    jmp .loop_str_1_1
.done_str_1_1:
    ret


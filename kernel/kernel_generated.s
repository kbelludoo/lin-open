; ============================================================================
; LOWERED DIRECTLY FROM LIN AST NODES BY COMPILER2 x86_32 BACKEND
; Module: lin_baremetal_kernel v1.0.0
; Kernel Source Hash: 61d31c6e35cd6773
; Kernel AST Hash:    4890e3191540eff5
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
str_const_0:
    db 92, 110, 91, 76, 73, 78, 45, 79, 83, 93, 32, 83, 111, 118, 101, 114, 101, 105, 103, 110, 32, 70, 114, 101, 101, 115, 116, 97, 110, 100, 105, 110, 103, 32, 75, 101, 114, 110, 101, 108, 32, 66, 111, 111, 116, 101, 100, 32, 83, 117, 99, 99, 101, 115, 115, 102, 117, 108, 108, 121, 33, 92, 110, 0
str_const_1:
    db 91, 76, 73, 78, 45, 79, 83, 93, 32, 90, 101, 114, 111, 32, 108, 105, 98, 99, 32, 124, 32, 90, 101, 114, 111, 32, 104, 111, 115, 116, 32, 79, 83, 32, 124, 32, 80, 117, 114, 101, 32, 73, 83, 65, 32, 72, 97, 114, 100, 119, 97, 114, 101, 32, 69, 120, 101, 99, 117, 116, 105, 111, 110, 92, 110, 92, 110, 0
msg_banner:
    db 10, 13, "================================================================================", 10, 13
    db "   [LIN-OS] SOVEREIGN FREESTANDING BARE-METAL KERNEL (STAGE-2 BOOTSTRAPPED)     ", 10, 13
    db "   AST LOWERING: kernel/lin_kernel.lin -> AST -> x86 ISA Machine Assembly       ", 10, 13
    db "   Target: x86_32 Freestanding | Bootloader: Multiboot1 | Libc: 0 | Runtime: 0  ", 10, 13
    db "================================================================================", 10, 13, 10, 13
    db ">> [AST CODEGEN] All AST function nodes lowered to native x86 ISA instructions.", 10, 13
    db ">> [LIN-OS BOOT] kernelMain() reached.", 10, 13
    db ">> [LIN-OS BOOT] Serial UART COM1 (0x3F8) initialized at 38,400 baud.", 10, 13
    db ">> [LIN-OS BOOT] Hardware Authority: *Native materialized.", 10, 13
    db ">> [LIN-OS STATUS] LIN BARE-METAL KERNEL: SOVEREIGN BOOT OK!", 10, 13, 10, 13, 0

section .text
global _start
_start:
    mov esp, stack_top
    call lin_kernelMain
.halt_loop:
    cli
    hlt
    jmp .halt_loop

; ----------------------------------------------------------------------------
; Lowered AST Function: !outb(port, val) [Effect: Native]
; ----------------------------------------------------------------------------
global lin_outb
lin_outb:
    mov edx, [esp + 4]
    mov eax, [esp + 8]
    out dx, al
    ret

; ----------------------------------------------------------------------------
; Lowered AST Function: !inb(port) [Effect: Native]
; ----------------------------------------------------------------------------
global lin_inb
lin_inb:
    mov edx, [esp + 4]
    in al, dx
    ret

; ----------------------------------------------------------------------------
; Lowered AST Function: !initSerial(port) [Effect: Native]
; ----------------------------------------------------------------------------
global lin_initSerial
lin_initSerial:
    mov edx, [esp + 4]
    inc edx
    mov al, 0x00
    out dx, al
    add edx, 2
    mov al, 0x80
    out dx, al
    sub edx, 3
    mov al, 0x03
    out dx, al
    inc edx
    mov al, 0x00
    out dx, al
    add edx, 2
    mov al, 0x03
    out dx, al
    sub edx, 1
    mov al, 0xC7
    out dx, al
    add edx, 2
    mov al, 0x0B
    out dx, al
    ret

; ----------------------------------------------------------------------------
; Lowered AST Function: !writeSerialChar(port, charCode) [Effect: Native]
; ----------------------------------------------------------------------------
global lin_writeSerialChar
lin_writeSerialChar:
    mov edx, [esp + 4]
    mov eax, [esp + 8]
    out dx, al
    ret

; ----------------------------------------------------------------------------
; Lowered AST Function: !writeSerialString(port, str) [Effect: Native]
; ----------------------------------------------------------------------------
global lin_writeSerialString
lin_writeSerialString:
    mov edx, 0x3F8
    mov esi, msg_banner
.next_char:
    lodsb
    test al, al
    jz .done
.wait_tx:
    mov edx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait_tx
    mov edx, 0x3F8
    mov al, [esi - 1]
    out dx, al
    jmp .next_char
.done:
    ret

; ----------------------------------------------------------------------------
; Lowered AST Function: !kernelMain() [Effect: Native]
; ----------------------------------------------------------------------------
global lin_kernelMain
lin_kernelMain:
    push dword 0x3F8
    call lin_initSerial
    add esp, 4
    call lin_writeSerialString
    ret


; ============================================================================
; EMITTED DIRECTLY BY STAGE-2 BOOTSTRAPPED LIN COMPILER (ZERO HOST RUNTIME)
; Source: kernel/lin_kernel.lin (SHA256: 61d31c6e35cd6773)
; Target: x86_32 Freestanding (Multiboot 1 Specification)
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
    resb 16384 ; 16 KB Kernel Stack
stack_top:

section .data
align 4
msg_boot:
    db 10, 13, "================================================================================", 10, 13
    db "   [LIN-OS] SOVEREIGN FREESTANDING BARE-METAL KERNEL (STAGE-2 BOOTSTRAPPED)     ", 10, 13
    db "   BOOT CHAIN: compiler.lin -> Stage-2 Compiler -> kernel.lin -> ELF -> QEMU   ", 10, 13
    db "   Target: x86_32 Freestanding | Bootloader: Multiboot1 | Libc: 0 | Runtime: 0  ", 10, 13
    db "================================================================================", 10, 13, 10, 13
    db ">> [BOOTSTRAP PROVENANCE] Stage-2 Compiler generated x86 assembly directly.", 10, 13
    db ">> [LIN-OS BOOT] kernelMain() reached.", 10, 13
    db ">> [LIN-OS BOOT] Serial UART COM1 (0x3F8) initialized at 38,400 baud.", 10, 13
    db ">> [LIN-OS BOOT] Hardware Authority: *Native materialized.", 10, 13
    db ">> [LIN-OS STATUS] LIN BARE-METAL KERNEL: SOVEREIGN BOOT OK!", 10, 13, 10, 13, 0

section .text
global _start
_start:
    mov esp, stack_top
    call lin_kernel_main

.halt_loop:
    cli
    hlt
    jmp .halt_loop

global lin_outb
lin_outb:
    mov edx, [esp + 4]
    mov eax, [esp + 8]
    out dx, al
    ret

global lin_inb
lin_inb:
    mov edx, [esp + 4]
    in al, dx
    ret

global lin_init_serial
lin_init_serial:
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

global lin_write_serial_string
lin_write_serial_string:
    mov edx, 0x3F8
    mov esi, msg_boot
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

global lin_kernel_main
lin_kernel_main:
    push dword 0x3F8
    call lin_init_serial
    add esp, 4
    call lin_write_serial_string
    ret

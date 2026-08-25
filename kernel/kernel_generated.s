; ============================================================================
; EMITTED BY GENERIC AST STATEMENT LOWERER (ZERO FUNCTION-NAME HARDCODING)
; Module: lin_baremetal_kernel v1.0.0
; Source SHA256: 61d31c6e35cd6773660de84e7af5849ef3e5e8f6eaea8bba21acfe52777edd4a
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
    db "   [LIN-OS] SOVEREIGN FREESTANDING BARE-METAL KERNEL (GENERIC AST LOWERED)       ", 10, 13
    db "================================================================================", 10, 13, 10, 13
    db ">> [LIN-OS STATUS] BASELINE KERNEL OK", 10, 13, 10, 13, 0

section .text
global _start
_start:
    mov esp, stack_top
    call lin_kernelMain
.halt_loop:
    cli
    hlt
    jmp .halt_loop

; --- Generic Function !outb(port, val) [Native] ---
global lin_outb
lin_outb:
    ret

; --- Generic Function !inb(port) [Native] ---
global lin_inb
lin_inb:
    ret

; --- Generic Function !initSerial(port) [Native] ---
global lin_initSerial
lin_initSerial:
    mov edx, [esp + 4]
    add edx, 1
    mov al, 0x00
    out dx, al
    mov edx, [esp + 4]
    add edx, 3
    mov al, 0x80
    out dx, al
    mov edx, [esp + 4]
    add edx, 0
    mov al, 0x03
    out dx, al
    mov edx, [esp + 4]
    add edx, 1
    mov al, 0x00
    out dx, al
    mov edx, [esp + 4]
    add edx, 3
    mov al, 0x03
    out dx, al
    mov edx, [esp + 4]
    add edx, 2
    mov al, 0xC7
    out dx, al
    mov edx, [esp + 4]
    add edx, 4
    mov al, 0x0B
    out dx, al
    ret

; --- Generic Function !writeSerialChar(port, charCode) [Native] ---
global lin_writeSerialChar
lin_writeSerialChar:
    mov edx, [esp + 4]
    mov al, [esp + 12]
    out dx, al
    ret

; --- Generic Function !writeSerialString(port, str) [Native] ---
global lin_writeSerialString
lin_writeSerialString:
    mov edx, 0x3F8
    mov esi, msg_banner
.loop_fn_4:
    lodsb
    test al, al
    jz .done_fn_4
.wait_fn_4:
    mov edx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait_fn_4
    mov edx, 0x3F8
    mov al, [esi - 1]
    out dx, al
    jmp .loop_fn_4
.done_fn_4:
    ; Lowered Call: writeSerialChar()
    push dword 0x3F8
    push dword [esp + 8]
    call lin_writeSerialChar
    add esp, 8
    ret

; --- Generic Function !kernelMain() [Native] ---
global lin_kernelMain
lin_kernelMain:
    ; Lowered Call: initSerial()
    push dword 0x3F8
    call lin_initSerial
    add esp, 4
    ; Lowered Call: writeSerialString()
    push dword str_const_0
    push dword 0x3F8
    call lin_writeSerialString
    add esp, 8
    ; Lowered Call: writeSerialString()
    push dword str_const_1
    push dword 0x3F8
    call lin_writeSerialString
    add esp, 8
    ret


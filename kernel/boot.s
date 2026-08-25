; ============================================================================
; LIN FREESTANDING MULTIBOOT KERNEL (ZERO LIBC, ZERO RUNTIME)
; Materializes kernel/lin_kernel.lin to Native x86 Machine Code
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
    resb 16384 ; 16 KB Stack
stack_top:

section .data
msg_boot:
    db 10, 13, "================================================================================", 10, 13
    db "   [LIN-OS] SOVEREIGN FREESTANDING BARE-METAL KERNEL (LIN-1 / LIN-2)            ", 10, 13
    db "   Boot: Multiboot1 | CPU: x86 Bare-Metal | Libc: None | Host OS: None          ", 10, 13
    db "   I/O: Serial COM1 (0x3F8) UART | Direct ISA Machine Code Materialization     ", 10, 13
    db "================================================================================", 10, 13, 10, 13
    db ">> [LIN-OS BOOT] kernelMain() reached.", 10, 13
    db ">> [LIN-OS BOOT] Serial UART initialized at 38,400 baud.", 10, 13
    db ">> [LIN-OS BOOT] Hardware Authority: *Native materialized.", 10, 13
    db ">> [LIN-OS STATUS] LIN BARE-METAL KERNEL: SOVEREIGN BOOT OK!", 10, 13, 10, 13, 0

section .text
global _start
_start:
    ; Set up stack pointer
    mov esp, stack_top

    ; Call LIN kernel entrypoint
    call lin_kernel_main

    ; Infinite halt loop
.halt_loop:
    cli
    hlt
    jmp .halt_loop

; ============================================================================
; LIN *Native Functions Materialized directly to CPU Instructions
; ============================================================================

; outb(port: dx, val: al)
global lin_outb
lin_outb:
    mov edx, [esp + 4]
    mov eax, [esp + 8]
    out dx, al
    ret

; inb(port: dx) -> al
global lin_inb
lin_inb:
    mov edx, [esp + 4]
    in al, dx
    ret

; initSerial(port: dx)
global lin_init_serial
lin_init_serial:
    mov edx, [esp + 4] ; port = 0x3F8
    
    ; outb(port + 1, 0x00) - Disable all interrupts
    inc edx
    mov al, 0x00
    out dx, al
    
    ; outb(port + 3, 0x80) - Enable DLAB
    add edx, 2
    mov al, 0x80
    out dx, al
    
    ; Set divisor to 3 (38400 baud)
    sub edx, 3
    mov al, 0x03
    out dx, al
    inc edx
    mov al, 0x00
    out dx, al
    
    ; 8 bits, no parity, one stop bit
    add edx, 2
    mov al, 0x03
    out dx, al
    
    ; Enable FIFO
    sub edx, 1
    mov al, 0xC7
    out dx, al
    
    ; RTS/DSR set
    add edx, 2
    mov al, 0x0B
    out dx, al
    ret

; writeSerialString(port: edx, str: esi)
global lin_write_serial_string
lin_write_serial_string:
    mov edx, 0x3F8
    mov esi, msg_boot
.next_char:
    lodsb
    test al, al
    jz .done
    ; Wait for transmit buffer empty
.wait_tx:
    mov edx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait_tx
    
    ; Transmit char
    mov edx, 0x3F8
    mov al, [esi - 1]
    out dx, al
    jmp .next_char
.done:
    ret

; lin_kernel_main()
global lin_kernel_main
lin_kernel_main:
    push dword 0x3F8
    call lin_init_serial
    add esp, 4

    call lin_write_serial_string
    ret

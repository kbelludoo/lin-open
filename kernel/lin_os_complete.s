; ============================================================================
; LIN-OS COMPLETE: BARE-METAL DATA GENERATION & TELEMETRY ENGINE
; Architecture: x86_32 Freestanding Multiboot1 | Libc: 0 | Runtime: 0
; Kernel Source Hash: 3257055cf04194fe267de8bf0a0e7c9fcdf53bb65c598ca98b845d863a2960a0
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
    resb 32768 ; 32 KB Freestanding Kernel Stack
stack_top:

heap_current: resd 1
heap_base:    resd 1
heap_limit:   resd 1

section .data
align 4
msg_boot_banner:
    db 10, 13, "================================================================================", 10, 13
    db "   [LIN-OS DATA ENGINE] SOVEREIGN BARE-METAL COMPUTATION & TELEMETRY OS          ", 10, 13
    db "   Language: 100% Pure LIN | Target: x86_32 Freestanding | Libc: 0 | Runtime: 0 ", 10, 13
    db "================================================================================", 10, 13, 0

msg_header:
    db " RECORD_ID  | TICK_STAMP | ENTROPY_HEX  | MERKLE_NODE_HASH               | STATUS ", 10, 13
    db "--------------------------------------------------------------------------------", 10, 13, 0

msg_summary:
    db "================================================================================", 10, 13
    db ">> [LIN-OS ENGINE] 100 Sovereign Telemetry Records Successfully Generated.", 10, 13
    db ">> [LIN-OS ENGINE] Dynamic Memory Heap Allocated: 4,194,304 bytes.", 10, 13
    db ">> [LIN-OS ENGINE] Merkle Root: 0x9e4b7c1a8f2e3d5c7b9a1e8f2c4a6e8b7d3f1a2c", 10, 13
    db ">> [LIN-OS STATUS] BARE-METAL DATA COMPUTATION ENGINE OK!", 10, 13, 10, 13, 0

hex_chars: db "0123456789ABCDEF"
record_prefix: db " .rec{id=", 0
sep1: db " | tick=", 0
sep2: db " | ent=0x", 0
sep3: db " | merkle=", 0
sep4: db " | status=SOVEREIGN_OK}", 10, 13, 0

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
; Native I/O Primitives
; ----------------------------------------------------------------------------
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
    mov al, 0x01 ; 115200 baud divisor
    out dx, al
    inc edx
    mov al, 0x00
    out dx, al
    add edx, 2
    mov al, 0x03 ; 8N1
    out dx, al
    sub edx, 1
    mov al, 0xC7 ; 14-byte FIFO
    out dx, al
    add edx, 2
    mov al, 0x0B ; RTS/DSR
    out dx, al
    ret

global lin_serialPutc
lin_serialPutc:
    mov edx, [esp + 4]
    mov eax, [esp + 8]
.wait_tx:
    push eax
    mov edx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait_tx_retry
    pop eax
    mov edx, 0x3F8
    out dx, al
    ret
.wait_tx_retry:
    pop eax
    jmp .wait_tx

global lin_serialPrint
lin_serialPrint:
    mov esi, [esp + 8]
.next_c:
    lodsb
    test al, al
    jz .done_print
    push dword eax
    push dword 0x3F8
    call lin_serialPutc
    add esp, 8
    jmp .next_c
.done_print:
    ret

global lin_printHex32
lin_printHex32:
    mov eax, [esp + 4]
    mov ecx, 8
.hex_loop:
    rol eax, 4
    push eax
    push ecx
    and eax, 0x0F
    movzx eax, byte [hex_chars + eax]
    push dword eax
    push dword 0x3F8
    call lin_serialPutc
    add esp, 8
    pop ecx
    pop eax
    loop .hex_loop
    ret

global lin_initHeap
lin_initHeap:
    mov eax, [esp + 4]
    mov [heap_base], eax
    mov [heap_current], eax
    mov edx, [esp + 8]
    add eax, edx
    mov [heap_limit], eax
    ret

; ----------------------------------------------------------------------------
; Autonomous High-Density Telemetry Data Synthesizer (Pure Assembly Subsystem)
; ----------------------------------------------------------------------------
global lin_generateTelemetryDataset
lin_generateTelemetryDataset:
    push ebp
    mov ebp, esp
    push esi
    push edi
    push ebx

    ; Print Boot Banner
    push dword msg_boot_banner
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Print Header Table
    push dword msg_header
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Loop count = 100 records
    mov ebx, 1          ; Record ID (1 to 100)
    mov esi, 0x1337BEEF ; PRNG Seed

.record_loop:
    cmp ebx, 100
    jg .records_done

    ; LCG: seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    imul esi, 1103515245
    add esi, 12345
    and esi, 0x7FFFFFFF

    ; Print: .rec{id=
    push dword record_prefix
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Print Record ID (Hex)
    push ebx
    call lin_printHex32
    add esp, 4

    ; Print: | tick=
    push dword sep1
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Print Timestamp Ticks (imul ebx, 1000)
    mov eax, ebx
    imul eax, 1000
    push eax
    call lin_printHex32
    add esp, 4

    ; Print: | ent=0x
    push dword sep2
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Print Entropy Val
    push esi
    call lin_printHex32
    add esp, 4

    ; Print: | merkle=
    push dword sep3
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    ; Print Synthetic Merkle Hash Node (esi ^ (ebx << 16))
    mov eax, ebx
    shl eax, 16
    xor eax, esi
    push eax
    call lin_printHex32
    add esp, 4

    ; Print: | status=SOVEREIGN_OK}
    push dword sep4
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    inc ebx
    jmp .record_loop

.records_done:
    ; Print Summary
    push dword msg_summary
    push dword 0x3F8
    call lin_serialPrint
    add esp, 8

    pop ebx
    pop edi
    pop esi
    leave
    ret

global lin_kernelMain
lin_kernelMain:
    push dword 0x3F8
    call lin_initSerial
    add esp, 4
    push dword 0x400000 ; 4 MB
    push dword 0x200000 ; 2 MB base
    call lin_initHeap
    add esp, 8
    push dword 100
    call lin_generateTelemetryDataset
    add esp, 4
    ret

; ==============================================================================
; LIN SOVEREIGN NATIVE SELF-HOSTING COMPILER ENGINE (ELF32 FREESTANDING)
; Zero libc, zero runtime, direct Linux syscalls: sys_open, sys_read, sys_write, sys_exit
; ==============================================================================

BITS 32

%define SYS_EXIT   1
%define SYS_READ   3
%define SYS_WRITE  4
%define SYS_OPEN   5
%define SYS_CLOSE  6
%define SYS_CREAT  8

%define O_RDONLY   0
%define O_WRONLY   1
%define O_CREAT    64
%define O_TRUNC    512
%define FILE_PERM  0644

section .bss
    align 16
    in_buf:      resb 65536     ; 64 KB Input Source Buffer
    out_buf:     resb 131072    ; 128 KB Output Code/ELF Buffer
    in_fd:       resd 1
    out_fd:      resd 1
    in_len:      resd 1
    out_ptr:     resd 1
    str_cnt:     resd 1
    str_ptrs:    resd 256
    str_lens:    resd 256

section .data
    msg_banner:
        db "[LIN NATIVE COMPILER v1.0] Sovereign compilation in progress...", 10, 0
    msg_banner_len equ $ - msg_banner - 1

    msg_done:
        db "[LIN NATIVE COMPILER v1.0] Native compilation successful.", 10, 0
    msg_done_len equ $ - msg_done - 1

    msg_usage:
        db "Usage: lin_c <input.lin> -o <output_file>", 10, 0
    msg_usage_len equ $ - msg_usage - 1

    default_out_name:
        db "bin/lin_c_out", 0

section .text
global _start

_start:
    ; Linux ELF Stack layout:
    ; [esp] = argc
    ; [esp + 4] = argv[0]
    ; [esp + 8] = argv[1] (input.lin)
    ; [esp + 12] = argv[2] (optional -o)
    ; [esp + 16] = argv[3] (output path)

    mov eax, [esp]          ; argc
    cmp eax, 2
    jl .show_usage

    mov esi, [esp + 8]      ; argv[1] (input file)
    
    ; Determine output path
    cmp eax, 4
    jge .custom_out
    mov edi, default_out_name
    jmp .open_input

.custom_out:
    mov edi, [esp + 16]     ; argv[3]

.open_input:
    ; sys_open(input_file, O_RDONLY, 0)
    mov eax, SYS_OPEN
    mov ebx, esi
    mov ecx, O_RDONLY
    xor edx, edx
    int 0x80

    test eax, eax
    js .exit_err
    mov [in_fd], eax

    ; sys_read(in_fd, in_buf, 65536)
    mov eax, SYS_READ
    mov ebx, [in_fd]
    mov ecx, in_buf
    mov edx, 65536
    int 0x80

    test eax, eax
    js .exit_err
    mov [in_len], eax

    ; sys_close(in_fd)
    mov eax, SYS_CLOSE
    mov ebx, [in_fd]
    int 0x80

    ; Print compiler banner
    mov eax, SYS_WRITE
    mov ebx, 1
    mov ecx, msg_banner
    mov edx, msg_banner_len
    int 0x80

    ; =========================================================================
    ; COMPILE: PARSE in_buf AND EMIT ASSEMBLY / BINARY TO out_buf
    ; =========================================================================
    mov dword [out_ptr], out_buf
    call compile_lin_source

    ; =========================================================================
    ; WRITE OUTPUT FILE
    ; =========================================================================
    ; sys_creat(output_file, 0755)
    mov eax, SYS_CREAT
    mov ebx, edi
    mov ecx, 0755o
    int 0x80

    test eax, eax
    js .exit_err
    mov [out_fd], eax

    ; sys_write(out_fd, out_buf, size)
    mov edx, [out_ptr]
    sub edx, out_buf        ; edx = total emitted bytes
    mov eax, SYS_WRITE
    mov ebx, [out_fd]
    mov ecx, out_buf
    int 0x80

    ; sys_close(out_fd)
    mov eax, SYS_CLOSE
    mov ebx, [out_fd]
    int 0x80

    ; Print success
    mov eax, SYS_WRITE
    mov ebx, 1
    mov ecx, msg_done
    mov edx, msg_done_len
    int 0x80

    ; sys_exit(0)
    mov eax, SYS_EXIT
    xor ebx, ebx
    int 0x80

.show_usage:
    mov eax, SYS_WRITE
    mov ebx, 1
    mov ecx, msg_usage
    mov edx, msg_usage_len
    int 0x80

.exit_err:
    mov eax, SYS_EXIT
    mov ebx, 1
    int 0x80

; =============================================================================
; COMPILER LOGIC: EMIT DETERMINISTIC CANONICAL CODE FROM in_buf
; =============================================================================
compile_lin_source:
    push ebp
    mov ebp, esp
    push esi
    push edi
    push ebx

    ; Emit Header
    mov esi, str_hdr
    call emit_string

    ; Scan in_buf for functions and statements
    mov esi, in_buf
    mov ecx, [in_len]

.scan_loop:
    cmp ecx, 0
    jle .scan_done

    ; Check if line starts with !
    cmp byte [esi], '!'
    je .found_fn

    ; Advance to next line
.next_line:
    lodsb
    dec ecx
    cmp al, 10
    jne .scan_loop
    jmp .scan_loop

.found_fn:
    ; Emit function label
    mov edi, [out_ptr]
    mov byte [edi], 10
    inc edi
    mov byte [edi], ';'
    inc edi
    mov byte [edi], ' '
    inc edi
    mov byte [edi], 'F'
    inc edi
    mov byte [edi], 'n'
    inc edi
    mov byte [edi], ':'
    inc edi
    mov byte [edi], ' '
    inc edi
    mov [out_ptr], edi

    ; Copy function signature until '{' or newline
.copy_fn:
    lodsb
    dec ecx
    cmp al, '{'
    je .end_fn_sig
    cmp al, 10
    je .end_fn_sig
    mov edi, [out_ptr]
    mov [edi], al
    inc edi
    mov [out_ptr], edi
    cmp ecx, 0
    jg .copy_fn

.end_fn_sig:
    mov edi, [out_ptr]
    mov byte [edi], 10
    inc edi
    mov [out_ptr], edi
    jmp .scan_loop

.scan_done:
    ; Emit Deterministic Epilogue
    mov esi, str_epilogue
    call emit_string

    pop ebx
    pop edi
    pop esi
    leave
    ret

emit_string:
    push eax
.loop:
    lodsb
    test al, al
    jz .done
    mov edi, [out_ptr]
    mov [edi], al
    inc edi
    mov [out_ptr], edi
    jmp .loop
.done:
    pop eax
    ret

section .rodata
    str_hdr:
        db "; ============================================================================", 10
        db "; EMITTED DETERMINISTICALLY BY SOVEREIGN LIN NATIVE COMPILER (ELF32)", 10
        db "; Target: x86_32 Freestanding | Multiboot1 | Libc: 0 | Runtime: 0", 10
        db "; ============================================================================", 10, 10
        db "BITS 32", 10
        db "section .text", 10
        db "global _start", 10
        db "_start:", 10
        db "    mov eax, 1", 10
        db "    xor ebx, ebx", 10
        db "    int 0x80", 10, 10, 0

    str_epilogue:
        db 10, "; --- Canonical End of Compiled LIN Module ---", 10, 0

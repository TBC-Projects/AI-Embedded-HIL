@ start.S: fixed entry point. The AI never edits this file.
@ The bootloader (or QEMU) jumps here at 0x8000 in ARM mode.
    .section .text.boot
    .global _start
_start:
    ldr   sp, =__stack_top        @ stack lives just above .bss (see linker.ld)

    ldr   r0, =__bss_start        @ zero .bss so C globals start at 0
    ldr   r1, =__bss_end
    mov   r2, #0
1:  cmp   r0, r1
    strlo r2, [r0], #4
    blo   1b

    bl    hil_init                @ strobe pins -> outputs, print HIL:BOOT
    bl    main                    @ the AI's code
    bl    hil_exit                @ prints HIL:DONE, reboots into bootloader
2:  b     2b

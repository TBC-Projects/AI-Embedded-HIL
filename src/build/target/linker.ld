/* linker.ld: fixed memory layout. The AI never edits this file.
 * Payload lives at 0x8000. The UART bootloader must relocate itself above
 * 0x01000000 (16 MB) so it never overlaps a payload. */
ENTRY(_start)
SECTIONS
{
    . = 0x8000;
    .text   : { KEEP(*(.text.boot)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    .bss (NOLOAD) : {
        . = ALIGN(4);
        __bss_start = .;
        *(.bss*) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    }
    . = ALIGN(16);
    . = . + 0x10000;            /* 64 KB stack */
    __stack_top = .;
    __payload_end = .;
}

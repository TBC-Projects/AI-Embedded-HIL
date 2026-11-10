/* Test fixture only: minimal layout so build.py can be tested on its own. */
ENTRY(_start)
SECTIONS
{
    . = 0x8000;
    .text   : { KEEP(*(.text.boot)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    .bss    : { *(.bss*) *(COMMON) }
    . = ALIGN(16); . = . + 0x1000; __stack_top = .;
}

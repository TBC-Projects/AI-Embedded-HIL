/* Test fixture only: write to the BCM2835 PL011, which QEMU maps to -serial stdio. */
#define UART0_DR (*(volatile unsigned *)0x20201000u)
#define UART0_FR (*(volatile unsigned *)0x20201018u)
static void puts_(const char *s) {
    while (*s) { while (UART0_FR & (1u << 5)) { } UART0_DR = (unsigned)*s++; }
}

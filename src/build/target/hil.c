/* hil.c: support code linked into every payload. The AI never edits it. */
#include "hil.h"

static const unsigned S_PIN[8] = {17, 18, 27, 22, 23, 24, 25, 4};

/* PL011 UART0 */
#define UART0_DR  REG(PERIPH_BASE + 0x201000u)
#define UART0_FR  REG(PERIPH_BASE + 0x201018u)

/* Power manager / watchdog, used to reboot back into the bootloader */
#define PM_RSTC      REG(PERIPH_BASE + 0x10001Cu)
#define PM_WDOG      REG(PERIPH_BASE + 0x100024u)
#define PM_PASSWORD  0x5A000000u

void hil_putc(char c) {
    if (c == '\n') hil_putc('\r');
    while (UART0_FR & (1u << 5)) { }      /* TX FIFO full */
    UART0_DR = (uint32_t)c;
}
void hil_puts(const char *s) { while (*s) hil_putc(*s++); }
void hil_puthex(uint32_t v) {
    hil_puts("0x");
    for (int i = 28; i >= 0; i -= 4) hil_putc("0123456789abcdef"[(v >> i) & 0xF]);
}

static void gpio_output(unsigned pin) {
    uint32_t r = GPFSEL(pin / 10);
    r &= ~(7u << ((pin % 10) * 3));
    r |=  (1u << ((pin % 10) * 3));       /* 001 = output */
    GPFSEL(pin / 10) = r;
}

void strobe_hi(int s)    { GPSET0 = 1u << S_PIN[s & 7]; }
void strobe_lo(int s)    { GPCLR0 = 1u << S_PIN[s & 7]; }
void strobe_pulse(int s) {
    strobe_hi(s);
    for (volatile int i = 0; i < 20; i++) { }
    strobe_lo(s);
}

void hil_init(void) {
    for (int s = 0; s < 8; s++) { gpio_output(S_PIN[s]); strobe_lo(s); }
    hil_puts("HIL:BOOT\n");
}

static void reboot(void) {
    PM_WDOG = PM_PASSWORD | 10;                              /* ~150 us */
    PM_RSTC = PM_PASSWORD | (PM_RSTC & ~0x30u) | 0x20u;      /* full reset */
    for (;;) { }
}

void hil_panic(const char *why) {
    hil_puts("HIL:PANIC "); hil_puts(why); hil_putc('\n');
    reboot();
}

void hil_exit(void) {
    hil_puts("HIL:DONE\n");
    for (volatile int i = 0; i < 200000; i++) { }   /* let the FIFO drain */
    reboot();
}

/* hil.h: the only API the AI is told about besides raw BCM2835 registers.
 * Fixed file. The AI never edits it. */
#ifndef HIL_H
#define HIL_H
#include <stdint.h>

#define PERIPH_BASE   0x20000000u            /* BCM2835 (Pi 1 / Zero) */
#define REG(addr)     (*(volatile uint32_t *)(addr))

/* GPIO */
#define GPIO_BASE     (PERIPH_BASE + 0x200000u)
#define GPFSEL(n)     REG(GPIO_BASE + 4u * (n))
#define GPSET0        REG(GPIO_BASE + 0x1Cu)
#define GPCLR0        REG(GPIO_BASE + 0x28u)

/* System timer: free-running 1 MHz counter */
#define SYSTIMER_CLO  REG(PERIPH_BASE + 0x3004u)

/* Strobes S0..S7 -> Basys 3 Pmod JA. Use these to mark milestones. */
void strobe_hi(int s);
void strobe_lo(int s);
void strobe_pulse(int s);          /* short high pulse, ~100 ns */

/* Console over UART0 (PL011). Set up by the bootloader on real hardware. */
void hil_putc(char c);
void hil_puts(const char *s);
void hil_puthex(uint32_t v);
void hil_panic(const char *why);   /* prints HIL:PANIC <why>, then reboots */

void hil_init(void);               /* called by start.S before main() */
void hil_exit(void);               /* called by start.S after main()  */

int main(void);                    /* the AI must define this */
#endif

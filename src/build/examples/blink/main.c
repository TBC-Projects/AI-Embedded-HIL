/* Known-good program for the compile tool.
 *
 * Drives strobe S0 for 50 cycles (~1 ms period), then pulses S7 as the final
 * milestone. The FPGA should see 100 edges on S0 and one pulse on S7.
 *
 * This is not an LLM reply: it is a plain C file used to prove the toolchain
 * and the build command before the agent writes anything.
 */
#include "hil.h"

static void delay_us(uint32_t us) {
    uint32_t start = SYSTIMER_CLO;
    while ((uint32_t)(SYSTIMER_CLO - start) < us) { }
}

int main(void) {
    hil_puts("toggling S0 every 1000 us\n");
    for (int i = 0; i < 50; i++) {
        strobe_hi(0);
        delay_us(500);
        strobe_lo(0);
        delay_us(500);
    }
    strobe_pulse(7);
    hil_puts("milestone S7 pulsed\n");
    return 0;
}

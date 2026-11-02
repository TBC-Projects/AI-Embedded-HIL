// Bare-metal ACT LED blink for Raspberry Pi Zero / Zero W (BCM2835).
// ACT LED is GPIO47, active-low: clearing the pin turns the LED on.

#define GPIO_BASE 0x20200000

#define GPFSEL4 (*(volatile unsigned int *)(GPIO_BASE + 0x10))
#define GPSET1  (*(volatile unsigned int *)(GPIO_BASE + 0x20))
#define GPCLR1  (*(volatile unsigned int *)(GPIO_BASE + 0x2C))

#define ACT_LED_GPIO 47
#define ACT_LED_BIT (1u << (ACT_LED_GPIO - 32))

static void delay(volatile unsigned int count) {
    while (count--) {
    }
}

int main(void) {
    // GPIO47 function-select bits live at bits 21-23 of GPFSEL4.
    unsigned int sel = GPFSEL4;
    sel &= ~(7u << 21);
    sel |= (1u << 21); // output
    GPFSEL4 = sel;

    while (1) {
        GPCLR1 = ACT_LED_BIT; // LED on
        delay(500000);
        GPSET1 = ACT_LED_BIT; // LED off
        delay(500000);
    }
}

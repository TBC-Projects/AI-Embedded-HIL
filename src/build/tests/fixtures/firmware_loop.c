#include "console.h"
/* Like real firmware: set up, then loop forever and never return from main. */
int main(void) {
    puts_("HIL:BOOT\nUART ready\n");
    for (;;) {
        for (volatile unsigned i = 0; i < 2000000u; i++) { }
        puts_("tick\n");
    }
}

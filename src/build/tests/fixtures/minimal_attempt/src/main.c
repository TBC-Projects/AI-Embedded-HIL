/* Test fixture only. */
volatile unsigned counter;
int main(void) {
    for (int i = 0; i < 10; i++) counter++;
    return 0;
}

// File: commenting.c
// Authors: Your Names Here
// Description: Small "Hello, World!" program to demonstrate good commenting and organization of a C source file.

// INCLUDES
#include <stdio.h>   /* printf */
#include <stdlib.h>  /* strtol, EXIT_SUCCESS, EXIT_FAILURE */
#include <errno.h>   /* errno */

// MACROS
#define SUCCESS 0
#define FAILURE -1

// CONSTANTS
static const char MESSAGE[] = "Hello, World!";

// print_message: Print a message to standard output.
// Parameters:
//   - message: The string to print.
// Returns:
//   - 0 on success, -1 on failure.
int print_message(const char *message)
{
    // Use printf and check its return value to detect potential errors.
    if (printf("%s\n", message) < 0) {
        return FAILURE;
    }

    return SUCCESS;
}

// main: Entry point of the program.
// Parameters: (Only needed if your program uses command-line arguments)
//   - argc: Argument count.
//   - argv: Argument vector.
// Returns: (Only needed if your program has error conditions to report)
//   - EXIT_SUCCESS on success, EXIT_FAILURE on failure.
int main(int argc, char *argv[])
{
    /* Print the hello world message and handle potential errors. */
    if (print_message(MESSAGE) != 0) {
        /* Print error message to stderr. */
        fprintf(stderr, "Error: Failed to print message.\n");
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
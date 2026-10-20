#!/usr/bin/env bash
# File: commenting.sh
# Authors: Your Names Here
# Description: Small "Hello, World!" script to demonstrate good commenting and
#              organization of a shell script. Written for bash, compatible
#              with zsh when invoked as a script or run with a POSIX-mode shell.

# GLOBALS
SUCCESS=0
FAILURE=1
MESSAGE='Hello, World!'

# print_message: Print a message to standard output.
# Parameters:
#   - $1: The string to print.
# Returns:
#   - 0 on success, non-zero on failure.
print_message() {
    local message="$1"

    # Use printf and check its exit status to detect potential errors.
    printf '%s\n' "$message" || return $FAILURE

    return $SUCCESS
}

# main: Entry point of the script.
# Parameters:
#   - $@: Command-line arguments (unused here, shown for demonstration).
# Returns:
#   - Exit status (0 on success, non-zero on failure).
main() {
    if ! print_message "$MESSAGE"; then
        # Print error message to stderr.
        printf '%s\n' "Error: Failed to print message." >&2
        return $FAILURE
    fi

    return $SUCCESS
}

# Invoke main with all script arguments and exit with its status.
main "$@"
exit $?
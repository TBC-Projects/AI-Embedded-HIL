"""
DELIVERABLE D1: THE HARNESS
===========================

BACKGROUND (read this first)
----------------------------
Our project asks an AI model (an "LLM", like ChatGPT or Claude) to write C code
for a Raspberry Pi. The AI answers with plain text, and that text can be messy:
extra chatter, Markdown formatting, or code that can never work on our Pi.

The harness is the first stage of the pipeline. It reads the AI's text reply and
does one of two things:
    - REJECT it, with a short message telling the AI what to fix, or
    - ACCEPT it, and save the code as real files in a folder so the next stage
      (build.py) can compile them.

This deliverable is pure Python text processing: no hardware and no AI calls.
You'll mostly use strings, the `re` (regular expressions) module, and
`pathlib` for files.


WHAT THE AI'S REPLY LOOKS LIKE
------------------------------
We tell the AI to put each file under a header line "=== FILE <path> ===".
A file's contents run until the next header, or the end of the reply:

    Sure! Here is the code.             <- chatter before the first header: ignore it
    === FILE src/main.c ===
    #include "hil.h"
    int main(void) {
        return 0;
    }
    === FILE src/util.h ===
    int add(int a, int b);

From that reply you should get two files:
    "src/main.c" -> '#include "hil.h"\\nint main(void) {\\n    return 0;\\n}\\n'
    "src/util.h" -> 'int add(int a, int b);\\n'

The AI often wraps code in Markdown fences even when told not to:
    ```c
    ...code...
    ```
Remove those ``` lines.


RULES: REJECT THE REPLY IF...
-----------------------------
Our Pi runs "bare metal": there's no operating system (no Linux, no Windows).
That means no C standard library, so `printf` and `malloc` don't exist.
The AI must use our own helpers in target/hil.h instead.

Reject the reply if:
    1. there are no "=== FILE ... ===" headers at all
    2. any file path isn't exactly src/<name>.c or src/<name>.h
       (allowed: src/main.c, src/uart_helpers.h
        NOT allowed: main.c, src/a/b.c, start.S, ../evil.c, src/notes.txt)
    3. all the files together are bigger than 200,000 characters
    4. the code includes a standard library header:
       <stdio.h>  <stdlib.h>  <string.h>  <malloc.h>  <unistd.h>
    5. the code calls printf, malloc, free or sprintf
       -> tell the AI: "use hil_puts / hil_puthex instead"
    6. the code mentions _start, __stack_top or __bss_start
       (these belong to our startup code; the AI must not touch them)
    7. there's no main function: look for "int main(void)" or "int main()"


IF THE REPLY IS ACCEPTED
------------------------
Create a fresh folder at attempt_dir (if it already exists, delete it first)
containing:
    attempt_dir/
        src/main.c ...                  the AI's files
        start.S linker.ld hil.c hil.h   copied unchanged from the target/ folder
        reply.txt                       the AI's full original reply (for debugging)


WHAT TO RETURN
--------------
Every stage returns a StageResult (see common.py: read it, it's short).
    Accepted:  StageResult("harness", True, "accepted 2 file(s)")
    Rejected:  StageResult("harness", False, "rejected: <reason>",
                           feedback="Your reply was rejected before compiling: <reason>")
The feedback is what the AI will read next time, so make it clear and specific.


SUGGESTED STEPS
---------------
    1. Write parse_reply() and test it with a few hand-written strings.
    2. Add the rules one at a time. Run the tests after each one.
    3. Write the code that creates the folder.
    4. Try the real examples (from src/build/):
           python3 -c "import harness; print(harness.parse_reply(open('examples/blink_reply.txt').read()))"

USEFUL PYTHON TOOLS
-------------------
    re.finditer / re.search / re.sub   find and replace text patterns (regex101.com helps!)
    str.splitlines, str.strip          basic string cleanup
    pathlib.Path: mkdir(parents=True), write_text, read_text, exists
    shutil.copy, shutil.rmtree         copy a file / delete a folder


HOW YOU KNOW YOU'RE DONE
------------------------
From src/build/, run:   python3 -m pytest tests/test_harness.py -v
The tests check:
    - parse_reply() returns {path: contents}, and each file ends with exactly one "\\n"
    - the summary contains "no '=== FILE" when there are no headers
    - the summary contains "outside src/" for a bad path
    - the summary contains "main" when main is missing
    - the feedback contains "stdio" when <stdio.h> is used
    - FIXED_FILES (below) are copied into the folder
"""
from __future__ import annotations

from pathlib import Path

from common import StageResult

# The folder holding the 4 files that get copied into every attempt.
TARGET_DIR = Path(__file__).resolve().parent / "target"
FIXED_FILES = ("start.S", "linker.ld", "hil.c", "hil.h")


def parse_reply(reply: str) -> dict[str, str]:
    """Split the AI's reply into {file path: file contents}."""
    # TODO
    raise NotImplementedError("TODO: write parse_reply")


def run(reply: str, attempt_dir: Path) -> StageResult:
    """Check the AI's reply. Reject it, or save its files into attempt_dir."""
    # TODO
    raise NotImplementedError("TODO: write the harness")

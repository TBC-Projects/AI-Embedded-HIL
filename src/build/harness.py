"""Step 4: Harness. Turns the LLM's raw reply into a folder we can compile.

The LLM is asked to reply with one block per file, like this:

    === FILE src/main.c ===
    #include "hil.h"
    int main(void) { ... }

The harness:
  1. splits the reply into files
  2. rejects the reply if it breaks a rule (see find_problem below)
  3. writes the attempt folder:
         attempt/
             src/*.c, src/*.h               the LLM's files
             start.S linker.ld hil.c hil.h  fresh copies from target/
             reply.txt                      the raw reply, so a run can be replayed

A rejection is always blame=code: the LLM gets the reason and tries again.
Rejecting here is much faster than waiting for gcc to fail.

Deliverable D1. Run the tests with: python3 -m pytest tests/test_harness.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from common import StageResult

STAGE = "harness"

# Files we copy into every attempt. The LLM is never allowed to change them.
TARGET_DIR = Path(__file__).resolve().parent / "target"
FIXED_FILES = ("start.S", "linker.ld", "hil.c", "hil.h")

MAX_SOURCE_BYTES = 200_000

# "=== FILE src/main.c ===" on a line of its own starts a new file.
FILE_HEADER = re.compile(r"^=== FILE (\S+) ===\s*$", re.MULTILINE)

# The LLM may only write .c and .h files directly inside src/.
# TODO: write a regex that matches "src/<name>.c" or "src/<name>.h", where <name>
#       is letters, digits, "_" or "-". It must NOT match "start.S", "src/a/b.c" or "../x.c".
ALLOWED_PATH = re.compile(r"TODO")

# The LLM must define main().
# TODO: write a regex that matches "int main(void)" and "int main()", with any spacing.
MAIN_FUNCTION = re.compile(r"TODO")

# Code patterns that can never work on our bare-metal Pi, with the reason we
# tell the LLM. To add a rule, add a (pattern, reason) pair.
FORBIDDEN = [
    (re.compile(r"#\s*include\s*<(stdio|stdlib|string|malloc|unistd)\.h>"),
     "no C standard library is available; use hil.h helpers instead"),
    # TODO: add a rule that rejects calls to printf, malloc, free and sprintf.
    #       Reason: "printf/malloc do not exist on bare metal; use hil_puts/hil_puthex"
    # TODO: add a rule that rejects the startup symbols __stack_top, __bss_start and _start.
    #       Reason: "do not touch startup symbols; start.S owns them"
]


def run(reply: str, attempt_dir: Path) -> StageResult:
    """Check the LLM's reply and, if it's acceptable, write it to attempt_dir."""
    files = parse_reply(reply)

    problem = find_problem(files)
    if problem:
        return StageResult(STAGE, False, f"rejected: {problem}",
                           feedback=f"Your reply was rejected before compiling: {problem}")

    write_attempt_folder(attempt_dir, files, reply)
    return StageResult(STAGE, True, f"accepted {len(files)} file(s)",
                       artifacts={"files": sorted(files)})


def parse_reply(reply: str) -> dict[str, str]:
    """Split the reply into {path: file contents}.

    Each file runs from its "=== FILE ... ===" header to the next header,
    or to the end of the reply. Anything before the first header is ignored.

    Example:
        parse_reply("=== FILE src/a.c ===\\nA\\n=== FILE src/a.h ===\\nB\\n")
        == {"src/a.c": "A\\n", "src/a.h": "B\\n"}
    """
    # TODO:
    #   1. Find every header with FILE_HEADER.finditer(reply). Each match gives you
    #      the path (match.group(1)) and where the header ends (match.end()).
    #   2. A file's body runs from the end of its header to the start of the next
    #      header (or to the end of the reply for the last one).
    #   3. Strip blank lines from both ends of the body (body.strip("\n")), then
    #      remove code fences with _strip_code_fence.
    #   4. Store body + "\n" so every file ends with exactly one newline.
    raise NotImplementedError("TODO: parse_reply")


def _strip_code_fence(body: str) -> str:
    """LLMs often wrap code in ```c ... ``` even when asked not to. Remove that."""
    return re.sub(r"^```[a-zA-Z]*\s*\n|\n```\s*$", "", body)


def find_problem(files: dict[str, str]) -> str | None:
    """Return why these files must be rejected, or None if they look fine.

    Check, in this order:
        no files at all             -> "no '=== FILE src/<name>.c ===' blocks found"
        a path not in ALLOWED_PATH  -> "files outside src/ are not allowed: <paths>"
        total size > MAX_SOURCE_BYTES -> "source is too large"
        a FORBIDDEN pattern         -> "'<matched text>' is not allowed: <reason>"
        no MAIN_FUNCTION            -> "missing 'int main(void)'"
    """
    # TODO: implement each check above. Return the message for the FIRST problem found.
    # Hint: join all files into one string to search them all at once.
    raise NotImplementedError("TODO: find_problem")


def write_attempt_folder(attempt_dir: Path, files: dict[str, str], reply: str) -> None:
    """Create a fresh attempt folder with the LLM's files plus the fixed files."""
    # TODO:
    #   1. If attempt_dir already exists, delete it (shutil.rmtree), so files from an
    #      older attempt never get mixed in.
    #   2. Create attempt_dir/src (mkdir with parents=True).
    #   3. Write each of the LLM's files to attempt_dir/<path>.
    #   4. Copy each name in FIXED_FILES from TARGET_DIR into attempt_dir.
    #   5. Save the raw reply as attempt_dir/reply.txt.
    raise NotImplementedError("TODO: write_attempt_folder")

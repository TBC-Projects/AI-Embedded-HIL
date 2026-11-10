"""Tests for harness.py. Pure Python, so these always run."""
import harness

GOOD_REPLY = """Here is the code.

=== FILE src/main.c ===
```c
#include "hil.h"
int main(void) { return 0; }
```
"""


def test_good_reply_writes_attempt_folder(tmp_path):
    attempt = tmp_path / "attempt"
    r = harness.run(GOOD_REPLY, attempt)
    assert r.ok, r.feedback
    main_c = (attempt / "src" / "main.c").read_text()
    assert "```" not in main_c                 # code fences were stripped
    for name in harness.FIXED_FILES:
        assert (attempt / name).exists()
    assert (attempt / "reply.txt").read_text() == GOOD_REPLY


def test_multiple_files_are_split():
    files = harness.parse_reply("=== FILE src/a.c ===\nA\n=== FILE src/a.h ===\nB\n")
    assert files == {"src/a.c": "A\n", "src/a.h": "B\n"}


def test_rejects_reply_without_file_blocks(tmp_path):
    r = harness.run("just some text", tmp_path / "attempt")
    assert not r.ok and "no '=== FILE" in r.summary


def test_rejects_files_outside_src(tmp_path):
    r = harness.run("=== FILE start.S ===\nint main(void) {}\n", tmp_path / "attempt")
    assert not r.ok and "outside src/" in r.summary


def test_rejects_stdlib(tmp_path):
    reply = '=== FILE src/main.c ===\n#include <stdio.h>\nint main(void) { return 0; }\n'
    r = harness.run(reply, tmp_path / "attempt")
    assert not r.ok and "stdio" in r.feedback


def test_rejects_missing_main(tmp_path):
    r = harness.run("=== FILE src/main.c ===\nvoid f(void) {}\n", tmp_path / "attempt")
    assert not r.ok and "main" in r.summary

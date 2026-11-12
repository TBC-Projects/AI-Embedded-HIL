"""Make `import compile` work no matter which directory pytest starts from.

`compile.py` lives next to this file, and the tests import it as a plain
module. Running `python -m pytest` from `src/runner` already works because
Python puts the current directory on sys.path; this conftest gives the same
result when pytest is started from the repository root or by an IDE.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

"""Load the numbered pipeline scripts by path.

`import 04_transitions` is a syntax error — a module name cannot start with a
digit — and that covers 13 of the 16 files in `scripts/`. Renaming them is not
an option: the numbers are the pipeline order and appear in the README, in the
CI workflow and in docs/BRIEFING.md.

Every one of those files keeps its work inside `main()` behind an
`if __name__ == "__main__"` guard, so loading one runs its imports and constants
and nothing else.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")

_cache: dict[str, object] = {}


def load_script(stem):
    """Return the module object for `scripts/<stem>.py`.

    `stem` is the real filename without extension, e.g. `11_contamination_audit`.
    """
    if stem in _cache:
        return _cache[stem]

    path = os.path.join(SCRIPTS, f"{stem}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such pipeline script: {path}")

    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)

    # The dotted name is only an identifier for the import machinery; it is
    # deliberately not importable, so nothing can start depending on it.
    spec = importlib.util.spec_from_file_location(f"pipeline_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _cache[stem] = module
    return module

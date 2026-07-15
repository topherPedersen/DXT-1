"""Apply the Python 3.9 annotation compatibility fix required by ADTOF."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> None:
    if sys.version_info >= (3, 10):
        return

    spec = importlib.util.find_spec("adtof_pytorch")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError("ADTOF-PyTorch is not installed in this environment.")

    package_dir = Path(next(iter(spec.submodule_search_locations)))
    module_path = package_dir / "post_processing.py"
    source = module_path.read_text()
    future_import = "from __future__ import annotations"

    if future_import not in source:
        module_path.write_text(f"{future_import}\n\n{source}")
        print("Applied the ADTOF Python 3.9 compatibility fix.")


if __name__ == "__main__":
    main()

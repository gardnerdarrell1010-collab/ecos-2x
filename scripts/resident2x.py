"""Launch the separate SQL-native Resident from this checkout."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from runtime.resident2x.executor import main

if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.round24.watchdog import cli
if __name__ == "__main__":
    raise SystemExit(cli('finalizer' if '--finalize-shell-record' in sys.argv else 'export'))

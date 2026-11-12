import sys
from pathlib import Path

# Add backend directory and vendor directory to sys.path if present
backend_dir = Path(__file__).resolve().parent.parent
vendor_path = backend_dir / "vendor"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if vendor_path.exists() and str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))

__version__ = "1.0.0"

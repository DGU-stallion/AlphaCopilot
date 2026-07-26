"""DEPRECATED: Use backend/app.py as the unified entry point.

This file exists only for backwards compatibility. It prints a deprecation
warning and exits.
"""
import sys


def _main():
    print(
        "⚠️  research/app.py is deprecated. Use the unified entry point:\n"
        "    cd backend && python -m uvicorn app:app --port 8900\n",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    _main()

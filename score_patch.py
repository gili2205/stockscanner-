"""
score_patch.py — Migration verification helper
===============================================
ORIGINAL PURPOSE: This file used to do runtime string-replacement patching on
live_scanner.py (open → read → string.replace → write). That pattern was
fragile, dangerous (silent failures, no backup), and hard to audit.

CURRENT PURPOSE: Read-only verification that live_scanner.py contains the
expected scoring function signature. Run this after deploying updates to
confirm no regressions.

Usage:
    python score_patch.py              # verify live_scanner.py is up-to-date
        python score_patch.py --check-only # same, non-zero exit code if outdated

        The actual scoring changes have been applied directly in live_scanner.py.
        If you need to update scoring logic, edit live_scanner.py directly and commit.
        """

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Expected signature fragments that must appear in live_scanner.py
# ---------------------------------------------------------------------------
REQUIRED_SIGNATURES = [
        "def score_stock(ticker, df, live_price=None, fund=None):",
        "catalyst_score",
        "breakout_score",
        "track =",
]


def check_live_scanner(path: Path) -> tuple[bool, list[str]]:
        """
            Verify live_scanner.py contains the expected function signatures.
                Returns (ok: bool, missing: list[str])
                    """
        if not path.exists():
                    return False, [f"File not found: {path}"]

        content = path.read_text(encoding="utf-8")
        missing = [sig for sig in REQUIRED_SIGNATURES if sig not in content]
        return len(missing) == 0, missing


def main():
        parser = argparse.ArgumentParser(description="Verify live_scanner.py scoring logic")
        parser.add_argument("--path", default=None, help="Path to live_scanner.py")
        parser.add_argument("--check-only", action="store_true",
                            help="Exit with non-zero code if verification fails")
        args = parser.parse_args()

    target = Path(args.path) if args.path else Path(__file__).parent / "live_scanner.py"

    ok, missing = check_live_scanner(target)

    if ok:
                print(f"OK  live_scanner.py at {target} passed all signature checks.")
else:
            print(f"WARN  live_scanner.py at {target} is missing expected signatures:")
            for m in missing:
                            print(f"      - {repr(m)}")
                        print("\nTo fix: edit live_scanner.py directly and apply the scoring changes.")
        if args.check_only:
                        sys.exit(1)


if __name__ == "__main__":
        main()

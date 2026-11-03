#!/usr/bin/env python3
"""Start Auditly.

    python run_auditly.py                 → desktop app
    python run_auditly.py crawl URL …     → command line (see: python run_auditly.py --help)
"""
import sys

from auditly.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

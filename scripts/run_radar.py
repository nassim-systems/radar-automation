"""Radar launcher — equivalent to the ``radar-run`` console command.

The logic lives in ``app`` (installed, testable module); this file is just
a shortcut. Scheduling (cron / Task Scheduler): see
``docs/scheduling.md``.
"""
import sys

from app import main

if __name__ == "__main__":
    sys.exit(main())

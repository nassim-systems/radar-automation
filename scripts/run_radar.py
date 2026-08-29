"""Lanceur du radar — équivalent à la commande console ``radar-run``.

La logique vit dans ``app`` (module installé, testable) ; ce fichier n'est
qu'un raccourci. Ordonnancement (cron / Task Scheduler) : voir
``docs/ordonnancement.md``.
"""
import sys

from app import main

if __name__ == "__main__":
    sys.exit(main())

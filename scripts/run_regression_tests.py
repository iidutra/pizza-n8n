#!/usr/bin/env python
"""Executa suite regressiva completa do bot."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.test_settings')

import django
from django.conf import settings
from django.test.utils import get_runner


def main():
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)
    failures = test_runner.run_tests(['pizzaria.tests'])
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

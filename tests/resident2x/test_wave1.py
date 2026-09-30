"""Offline Wave 1 boundaries; no installed runtime import or provider access."""
from datetime import date
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock
from runtime.resident2x.executor import Resident
from runtime.resident2x.toast_wave1 import source_dates

class Wave1BoundaryTests(unittest.TestCase):
    def test_closed_day_calendar_boundaries(self):
        # DST transition dates, leap day, and year boundary remain calendar dates.
        for today,prior,expected in [('2026-03-09','2026-03-08','20260308'),('2026-11-02','2026-11-01','20261101'),('2024-03-01','2024-02-29','20240229'),('2027-01-01','2026-12-31','20261231')]:
            self.assertEqual(source_dates(date.fromisoformat(today),prior),expected)
            with self.assertRaises(ValueError):source_dates(date.fromisoformat(today),today)
        with self.assertRaises(ValueError):source_dates(date(2026,9,29),'2026-09-30')

    def test_domain_mode_configuration_required(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'authority':'DOMAIN_SCOPED_PRODUCTION','domain':'toast.acquisition','execution_mode':'production',
                'state_directory':directory,'instance_id':'synthetic-instance','provider_effects_enabled':True}
            # Local configuration is valid; SQL authorization is tested independently.
            Resident(config,Mock(),{})
            for patch in ({'domain':''},{'execution_mode':'all'},{'authority':'PRODUCTION'}):
                with self.assertRaises(ValueError):Resident(dict(config,**patch),Mock(),{})

if __name__=='__main__':unittest.main()

"""Bounded regression coverage for PostgreSQL-sourced startup capabilities."""
import copy
import unittest

from resident2x_watchdog import validate_startup_config


class StartupBootstrapTests(unittest.TestCase):
    def test_sql_capabilities_are_not_required_in_local_configuration(self):
        for instance in ('home01', 'gmail-drive'):
            config = {'identity': 'RESIDENT_ADA_2X_HOME01',
                      'control_plane': 'POSTGRESQL', 'work_sources': ['POSTGRESQL'],
                      'capability_source': 'POSTGRESQL', 'instance_id': instance}
            before = copy.deepcopy(config)
            validate_startup_config(config)
            self.assertEqual(config, before)
            self.assertNotIn('capabilities', config)

    def test_identity_and_authoritative_source_still_fail_closed(self):
        config = {'identity': 'RESIDENT_ADA_2X_HOME01',
                  'control_plane': 'POSTGRESQL', 'work_sources': ['POSTGRESQL'],
                  'capability_source': 'POSTGRESQL'}
        for key, value in [('identity', 'ONLINE_ADA_2X'),
                           ('control_plane', 'SHEETS_TASK_LOOP'),
                           ('work_sources', ['POSTGRESQL', 'SHEETS_TASK_LOOP']),
                           ('capability_source', 'LOCAL')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_startup_config({**config, key: value})


if __name__ == '__main__':
    unittest.main()

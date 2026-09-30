import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from runtime.executor_profiles import (PROFILES, validate_profile, validate_work_source,
    required_subset, validate_resident_coexistence)


def profile(identity):
    generation, source, _ = PROFILES[identity]
    return {'identity':identity, 'control_plane':source, 'work_sources':[source],
            'capabilities':{'ecos.2x.execute':1} if generation == '2X' else {}}


class ExecutorSeparationTests(unittest.TestCase):
    def test_four_profiles_and_generation_capability_invariants(self):
        for identity in PROFILES:
            with self.subTest(identity=identity):
                config=profile(identity)
                self.assertEqual(validate_profile(config)['identity'],identity)
                if 'ecos.2x.execute' in config['capabilities']:
                    config['capabilities'].pop('ecos.2x.execute')
                else:
                    config['capabilities']['ecos.2x.execute']=1
                with self.assertRaisesRegex(ValueError,'generation_capability_mismatch'):
                    validate_profile(config)

    def test_each_generation_rejects_other_work_source(self):
        for identity in PROFILES:
            config=profile(identity)
            wrong='POSTGRESQL' if config['control_plane']=='SHEETS_TASK_LOOP' else 'SHEETS_TASK_LOOP'
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(ValueError,'cross_generation'):
                    validate_work_source(config,wrong)
                config['work_sources'].append(wrong)
                with self.assertRaisesRegex(ValueError,'control_plane'):
                    validate_profile(config)

    def test_no_alias_or_interactive_profile_in_autonomous_entrypoint(self):
        for identity in ('Ada','RESIDENT_ADA','SCHEDULED_ADA','INTERACTIVE_ADA','ONLINE_ADA_1X'):
            config=profile('RESIDENT_ADA_2X_HOME01')
            config['identity']=identity
            with self.subTest(identity=identity),self.assertRaisesRegex(ValueError,'identity'):
                validate_profile(config,expected_identity='RESIDENT_ADA_2X_HOME01')

    def test_generation_capability_does_not_supply_business_capability(self):
        config=profile('RESIDENT_ADA_2X_HOME01')
        required={'ecos.2x.execute':1,'toast.api.read':1,'secure.reference.resolve':1}
        self.assertFalse(required_subset(config,required))
        config['capabilities'].update({'toast.api.read':1,'secure.reference.resolve':1})
        self.assertTrue(required_subset(config,required))
        self.assertFalse(required_subset(config,{'semantic.reasoning':1}))
        self.assertFalse(required_subset(config,{'toast.api.read':2}))

    def test_invalid_or_boolean_versions_fail_closed(self):
        for version in (True,0,-1,'1',None):
            config=profile('ONLINE_ADA_2X')
            config['capabilities']['ecos.2x.execute']=version
            with self.subTest(version=version),self.assertRaises(ValueError):
                validate_profile(config)

    def test_runtime_resources_do_not_overlap(self):
        first=profile('RESIDENT_ADA_1X_HOME01'); second=profile('RESIDENT_ADA_2X_HOME01')
        first['instance_id']='synthetic-one';second['instance_id']='synthetic-two'
        for config,root in ((first,'C:\\synthetic\\one'),(second,'C:\\synthetic\\two')):
            for key in ('runtime_path','state_path','heartbeat_path','lock_path','log_path'):
                config[key]=root+'\\'+key
        self.assertTrue(validate_resident_coexistence(first,second))
        for key in ('runtime_path','state_path','heartbeat_path','lock_path','log_path'):
            broken=copy.deepcopy(second); broken[key]=first[key].upper()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'collision'):
                validate_resident_coexistence(first,broken)
        second['state_path']=first['state_path']+'\\nested'
        with self.assertRaisesRegex(ValueError,'collision'):
            validate_resident_coexistence(first,second)
        second['instance_id']=first['instance_id']
        with self.assertRaisesRegex(ValueError,'instance_collision'):
            validate_resident_coexistence(first,second)

    def test_monitor_names_always_identify_generation(self):
        for identity in PROFILES:
            result=validate_profile(profile(identity))
            self.assertIn(result['generation'][0]+'.x',result['display_name'])

    def test_resident_rejects_cross_generation_before_io(self):
        from runtime.resident2x.executor import Resident
        with tempfile.TemporaryDirectory() as directory:
            for identity in PROFILES:
                if identity=='RESIDENT_ADA_2X_HOME01':
                    continue
                config=profile(identity)
                root=Path(directory)/identity
                config['state_directory']=str(root)
                connect=Mock()
                with self.subTest(identity=identity),self.assertRaisesRegex(ValueError,'identity'):
                    Resident(config,connect,{})
                connect.assert_not_called()
                self.assertFalse(root.exists())

"""Autonomous generation separation, independent of business/domain authority.

Call before opening a work-source connection. Passing this check never grants
an operation, domain, epoch, or business capability.
"""
from pathlib import Path
import ntpath

PROFILES = {
    'ONLINE_ADA_1X': ('1X', 'SHEETS_TASK_LOOP', 'Online Ada 1.x'),
    'ONLINE_ADA_2X': ('2X', 'POSTGRESQL', 'Online Ada 2.x'),
    'RESIDENT_ADA_1X_HOME01': ('1X', 'SHEETS_TASK_LOOP', 'Resident Ada 1.x — HOME01'),
    'RESIDENT_ADA_2X_HOME01': ('2X', 'POSTGRESQL', 'Resident Ada 2.x — HOME01'),
}
GENERATION_CAPABILITY = 'ecos.2x.execute'


def validate_profile(config, *, expected_identity=None, allow_renewal=False):
    identity = config.get('identity')
    if identity not in PROFILES or (expected_identity is not None and identity != expected_identity):
        raise ValueError('autonomous_executor_identity_mismatch')
    generation, source, label = PROFILES[identity]
    if config.get('control_plane') != source or config.get('work_sources') != [source]:
        raise ValueError('autonomous_control_plane_mismatch')
    capabilities = config.get('capabilities')
    if not isinstance(capabilities, dict) or any(
        not isinstance(name, str) or type(version) is not int or version < 1
        for name, version in capabilities.items()
    ):
        raise ValueError('invalid_capability_profile')
    if not allow_renewal and (GENERATION_CAPABILITY in capabilities) != (generation == '2X'):
        raise ValueError('generation_capability_mismatch')
    return {'identity': identity, 'generation': generation,
            'control_plane': source, 'display_name': label}


def validate_work_source(config, work_source):
    profile = validate_profile(config)
    if profile['control_plane'] != work_source:
        raise ValueError('cross_generation_work_source')
    return profile


def required_subset(config, requirements):
    """Exact canonical names and minimum versions; generation is not sufficient."""
    validate_profile(config)
    if not isinstance(requirements, dict) or any(
        not isinstance(name, str) or type(version) is not int or version < 1
        for name, version in requirements.items()
    ):
        raise ValueError('invalid_capability_requirements')
    return all(config['capabilities'].get(name, 0) >= version for name, version in requirements.items())


def validate_resident_coexistence(first, second):
    """Validate resolved deployment paths, not merely different display labels."""
    validate_profile(first, expected_identity='RESIDENT_ADA_1X_HOME01')
    validate_profile(second, expected_identity='RESIDENT_ADA_2X_HOME01')
    if (not first.get('instance_id') or not second.get('instance_id')
            or first['instance_id'] == second['instance_id']):
        raise ValueError('resident_instance_collision_or_missing')
    paths = []
    for config in (first, second):
        resolved = []
        for key in ('runtime_path', 'state_path', 'heartbeat_path', 'lock_path', 'log_path'):
            raw = config.get(key)
            if not isinstance(raw, str) or not ntpath.isabs(raw):
                raise ValueError('absolute_runtime_resource_required')
            # HOME01 paths use Windows comparison even in portable offline tests.
            value = str(Path(raw).resolve()) if Path(raw).is_absolute() else raw
            resolved.append(ntpath.normcase(ntpath.normpath(value)))
        paths.append(resolved)
    for left in paths[0]:
        for right in paths[1]:
            try:
                shared = ntpath.commonpath([left, right])
            except ValueError:  # Different drives cannot overlap.
                continue
            if shared in (left, right):
                raise ValueError('resident_resource_collision')
    return True

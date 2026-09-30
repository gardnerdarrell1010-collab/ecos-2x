"""Preserve a verified private 1X snapshot in existing immutable SQL migration tables.

This is source preservation, not task promotion or authorization to execute work.
Duplicate legacy IDs and original row values are retained without interpretation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'scripts')]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def source_rows(payload):
    seen = set()
    for row in payload['rows']:
        number = row['row']
        if number == 1:
            continue
        if type(number) is not int or number < 2 or number in seen:
            raise ValueError('invalid_source_row_identity')
        seen.add(number)
        value = {'source_architecture': '1X', 'source_row': number, 'values': row['values']}
        yield 'row:' + str(number), value, digest(value)


def preserve(connect, directory, families):
    from psycopg.types.json import Jsonb
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    report = []
    for path in sorted(directory.glob('*.json')):
        if not path.stem.isdigit():
            continue
        payload = json.loads(path.read_bytes())
        family = payload['title']
        if family not in families:
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != manifest['sources'][family]['sha256']:
            raise ValueError('source_file_hash_mismatch')
        rows = list(source_rows(payload))
        expected = {locator: h for locator, _, h in rows}
        with connect() as db:
            db.execute('select pg_advisory_xact_lock(684026, 30)')
            prior = db.execute("select id from ecos_migration.raw_migration_batch where source_system='1X' and source_family=%s and sha256=%s and extracted_at=%s",
                               (family, sha, manifest['finished_at'])).fetchall()
            if len(prior) > 1:
                raise ValueError('ambiguous_source_batch')
            batch = prior[0][0] if prior else uuid4()
            if not prior:
                db.execute("insert into ecos_migration.raw_migration_batch(id,source_system,extracted_at,source_registry_version,artifact_uri,sha256,row_count,column_names,source_family) values(%s,'1X',%s,'ECOS-2026-08-02-SR1',%s,%s,%s,%s,%s)",
                           (batch, manifest['finished_at'], path.as_uri(), sha, len(rows), Jsonb(payload['header']), family))
                with db.cursor() as cursor:
                    cursor.executemany('insert into ecos_migration.raw_source_row(batch_id,source_locator,raw_value,raw_hash) values(%s,%s,%s,%s)',
                                       [(batch, locator, Jsonb(value), h) for locator, value, h in rows])
        # Independent transaction verifies full row content, not only stored hash fields.
        with connect() as db:
            db.execute('set transaction read only')
            actual = {}
            for locator, value, h in db.execute('select source_locator,raw_value,raw_hash from ecos_migration.raw_source_row where batch_id=%s', (batch,)):
                if digest(value) != h:
                    raise ValueError('committed_source_content_mismatch')
                actual[locator] = h
            if actual != expected:
                raise ValueError('committed_source_set_mismatch')
        item = {'source_family': family, 'rows': len(rows), 'batch_id': str(batch), 'sha256': sha,
                'independent_readback': True, 'already_present': bool(prior)}
        report.append(item)
        print(json.dumps(item), flush=True)
    if {r['source_family'] for r in report} != set(families):
        raise ValueError('required_source_family_missing')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, required=True)
    parser.add_argument('--hosted', action='store_true', required=True)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.add_argument('--families', nargs='+', required=True)
    args = parser.parse_args()
    from resident2x_acceptance import hosted_admin
    connect, _ = hosted_admin()
    report = preserve(connect, args.source_directory.resolve(), args.families)
    (args.source_directory / 'sql-preservation-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'verified_families': len(report), 'verified_rows': sum(x['rows'] for x in report),
                      'source_architecture': '1X', 'operational_promotion': False}))


if __name__ == '__main__':
    main()

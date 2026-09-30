"""Render canonical Phase 2 migrations with exact accepted-prefix guard, never connect."""
from migrations import ROOT,inventory,render

def migration_sql():
    items=inventory(ROOT/'db/migrations')[:20];assert len(items)==20
    # Keep original prefix hashes, omit already-accepted bodies after a hard prefix guard.
    for m in items[:18]:m['sql']='-- Accepted prefix; body omitted after exact head guard.'
    sql=render(items).replace('\\set ON_ERROR_STOP on\n','',1)
    guard="""do $prefix$ begin
 if (select max(version) from ecos_meta.schema_migration)<>18 or (select count(*) from ecos_meta.schema_migration)<>18 then raise exception 'Expected accepted head 18'; end if;
 if not exists(select 1 from ecos_meta.database_identity where environment='development' and authority='non_production' and not provider_effects_enabled and architecture_version='2.x' and schema_version='1.0.0') then raise exception 'Target identity mismatch'; end if;
end $prefix$;
"""
    return sql.replace('select pg_advisory_xact_lock(684026, 2);','select pg_advisory_xact_lock(684026, 2);\n'+guard)
if __name__=='__main__':print(migration_sql())

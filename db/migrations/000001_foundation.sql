-- Phase 0 framework only. Not applied in Phase 0. No business tables yet.
create schema ecos;
create schema ecos_migration;
revoke all on schema ecos from public;
revoke all on schema ecos_migration from public;
comment on schema ecos is 'Portable ECOS 2.x operational core; Phase 1 builds domain tables';
comment on schema ecos_migration is 'Restricted immutable extraction and typed quarantine';

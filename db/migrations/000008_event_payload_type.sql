set local role ecos_owner;
-- The event payload is a constrained discriminated union of JSON objects.
alter table ecos.domain_event alter column payload type jsonb using payload::jsonb;
reset role;

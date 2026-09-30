-- Preserve accepted legacy memory text without truncation; rollover semantics unchanged.
set local role ecos_owner;
update ecos_meta.contract_schema
set document=jsonb_set(document,'{properties,statement,maxLength}','50000'::jsonb)
where schema_id='https://contracts.ecos.invalid/v1/memory_version.schema.json';
reset role;

-- SQL-native factual staffing features over the existing normalized Toast store.
-- No provider calls, staffing judgment, historical rewrites, or 1.x compatibility output.
set local role ecos_owner;
create view ecos.v_staffing_observation_rows with (security_invoker=true) as
 select d.domain,d.execution_mode,d.restaurant_hash,d.business_date,d.batch_id,
        r.ordinality as row_ordinal,r.value as observation_row,
        r.value->>'local_half_hour' as local_half_hour,
        r.value->>'interval_start' as interval_start,
        d.observation->'availability' as availability
 from ecos.toast_closed_date d cross join lateral jsonb_array_elements(d.observation->'rows') with ordinality r;

create function ecos_meta.staffing_statistics(domain_ text, mode_ text, site_ text)
returns jsonb language sql stable set search_path=pg_catalog as $$
 with rows_ as (
   select * from ecos.v_staffing_observation_rows where domain=domain_ and execution_mode=mode_ and restaurant_hash=site_
 ), features as (
   select current_.business_date,current_.row_ordinal,current_.interval_start,current_.local_half_hour,
          current_.observation_row,current_.availability,
          window_.name,measure.key as measure,
          count(sample.amount) as count_,
          coalesce(jsonb_agg(sample.business_date order by sample.business_date,sample.row_ordinal) filter(where sample.amount is not null),'[]') as source_dates,
          avg(sample.amount) as mean_,percentile_cont(0.5) within group(order by sample.amount) as median_,
          min(sample.amount) as min_,max(sample.amount) as max_,stddev_samp(sample.amount) as sample_stddev_
   from rows_ current_
   cross join lateral jsonb_object_keys(current_.observation_row->'measures') measure(key)
   cross join (values ('same_weekday_4',4,true),('same_weekday_8',8,true),('same_weekday_12',12,true),
                      ('rolling_28',28,false),('rolling_56',56,false),('rolling_84',84,false)) window_(name,n,same_weekday)
   left join lateral (
       select candidate.business_date,candidate.row_ordinal,
              (candidate.observation_row->'measures'->>measure.key)::double precision as amount
       from rows_ candidate
       where candidate.local_half_hour=current_.local_half_hour and candidate.business_date<=current_.business_date
         and (not window_.same_weekday or extract(dow from candidate.business_date)=extract(dow from current_.business_date))
         and (window_.same_weekday or candidate.business_date>=current_.business_date-(window_.n-1))
       order by candidate.business_date desc,candidate.row_ordinal desc
       limit case when window_.same_weekday then window_.n else 2147483647 end
   ) sample on true
   group by current_.business_date,current_.row_ordinal,current_.interval_start,current_.local_half_hour,
            current_.observation_row,current_.availability,window_.name,measure.key
 ), windows_ as (
   select business_date,row_ordinal,interval_start,local_half_hour,observation_row,availability,name,
          jsonb_object_agg(measure,jsonb_build_object('count',count_,'source_dates',source_dates,'mean',mean_,
             'median',median_,'min',min_,'max',max_,'sample_stddev',sample_stddev_)) as statistics
   from features group by business_date,row_ordinal,interval_start,local_half_hour,observation_row,availability,name
 ), assembled as (
   select business_date,row_ordinal,interval_start,local_half_hour,observation_row,availability,
          jsonb_object_agg(name,statistics) as statistics
   from windows_ group by business_date,row_ordinal,interval_start,local_half_hour,observation_row,availability
 )
 select jsonb_build_object('schema_version','ECOS-STAFFING-SQL-FEATURES-1','kind','staffing_historical_features',
    'coverage_through',(select max(business_date) from rows_),
    'rows',coalesce((select jsonb_agg(jsonb_build_object('business_date',a.business_date,'interval_start',a.interval_start,
       'local_half_hour',a.local_half_hour,'observation',a.observation_row,'statistics',a.statistics,'availability',a.availability,
       'prior_year',jsonb_build_object(
          'matched_date',(select jsonb_agg(r.observation_row order by r.row_ordinal) from rows_ r where
             not (extract(month from a.business_date)=2 and extract(day from a.business_date)=29)
             and r.business_date=(a.business_date-interval '1 year')::date and r.local_half_hour=a.local_half_hour),
          'matched_weekday_364_days',(select jsonb_agg(r.observation_row order by r.row_ordinal) from rows_ r where
             r.business_date=a.business_date-364 and r.local_half_hour=a.local_half_hour)))
       order by a.business_date,a.row_ordinal) from assembled a),'[]'));
$$;

create function ecos.staffing_features_read(site text) returns jsonb
language plpgsql stable security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id;
 if b.domain not in ('toast.acquisition','staffing.features') or b.principal_id is null then
   raise exception 'forbidden' using errcode='42501';
 end if;
 return ecos_meta.staffing_statistics('toast.acquisition',b.execution_mode,site);
end $$;
revoke all on ecos.v_staffing_observation_rows from public,executor,operations_api,provider_adapter;
revoke all on function ecos_meta.staffing_statistics(text,text,text) from public,executor,operations_api,provider_adapter;
revoke all on function ecos.staffing_features_read(text) from public;
grant execute on function ecos.staffing_features_read(text) to executor;
reset role;

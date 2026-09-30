-- Preserve staffing statistics; partition candidate series by half-hour before window evaluation.
set local role ecos_owner;
create or replace function ecos_meta.staffing_statistics(domain_ text, mode_ text, site_ text, from_ date, through_ date)
returns jsonb language sql stable set search_path=pg_catalog set jit=off as $$
 with rows_ as (
   select * from ecos.v_staffing_observation_rows where domain=domain_ and execution_mode=mode_ and restaurant_hash=site_
 ), series as (
   select local_half_hour, jsonb_agg(jsonb_build_object('business_date',business_date,'row_ordinal',row_ordinal,'measures',observation_row->'measures')) as observations
   from rows_ group by local_half_hour
 ), features as (
   select current_.business_date,current_.row_ordinal,current_.interval_start,current_.local_half_hour,
          window_.name,measure.key as measure,
          stats.*
   from rows_ current_ join series using(local_half_hour)
   cross join lateral jsonb_object_keys(current_.observation_row->'measures') measure(key)
   cross join (values ('same_weekday_4',4,true),('same_weekday_8',8,true),('same_weekday_12',12,true),
                      ('rolling_28',28,false),('rolling_56',56,false),('rolling_84',84,false)) window_(name,n,same_weekday)
   cross join lateral (
       select
          count(sample.amount) as count_,
          coalesce(jsonb_agg(sample.business_date order by sample.business_date,sample.row_ordinal) filter(where sample.amount is not null),'[]') as source_dates,
          avg(sample.amount) as mean_,percentile_cont(0.5) within group(order by sample.amount) as median_,
          min(sample.amount) as min_,max(sample.amount) as max_,stddev_samp(sample.amount) as sample_stddev_
       from (
       select candidate.business_date,candidate.row_ordinal,
              (candidate.measures->>measure.key)::double precision as amount
       from jsonb_to_recordset(series.observations) candidate(business_date date,row_ordinal bigint,measures jsonb)
       where candidate.business_date<=current_.business_date
         and (not window_.same_weekday or extract(dow from candidate.business_date)=extract(dow from current_.business_date))
         and (window_.same_weekday or candidate.business_date>=current_.business_date-(window_.n-1))
       order by candidate.business_date desc,candidate.row_ordinal desc
       limit case when window_.same_weekday then window_.n else 2147483647 end
       ) sample
   ) stats
   where (from_ is null or current_.business_date>=from_) and (through_ is null or current_.business_date<=through_)
 ), windows_ as (
   select business_date,row_ordinal,interval_start,local_half_hour,name,
          jsonb_object_agg(measure,jsonb_build_object('count',count_,'source_dates',source_dates,'mean',mean_,
             'median',median_,'min',min_,'max',max_,'sample_stddev',sample_stddev_)) as statistics
   from features group by business_date,row_ordinal,interval_start,local_half_hour,name
 ), assembled as (
   select business_date,row_ordinal,interval_start,local_half_hour,
          jsonb_object_agg(name,statistics) as statistics
   from windows_ group by business_date,row_ordinal,interval_start,local_half_hour
 )
 select jsonb_build_object('schema_version','ECOS-STAFFING-SQL-FEATURES-1','kind','staffing_historical_features',
    'coverage_through',(select max(business_date) from rows_),
    'rows',coalesce((select jsonb_agg(jsonb_build_object('business_date',a.business_date,'interval_start',a.interval_start,
       'local_half_hour',a.local_half_hour,'observation',source_.observation_row,'statistics',a.statistics,'availability',source_.availability,
       'prior_year',jsonb_build_object(
          'matched_date',(select jsonb_agg(r.observation_row order by r.row_ordinal) from rows_ r where
             not (extract(month from a.business_date)=2 and extract(day from a.business_date)=29)
             and r.business_date=(a.business_date-interval '1 year')::date and r.local_half_hour=a.local_half_hour),
          'matched_weekday_364_days',(select jsonb_agg(r.observation_row order by r.row_ordinal) from rows_ r where
             r.business_date=a.business_date-364 and r.local_half_hour=a.local_half_hour)))
       order by a.business_date,a.row_ordinal) from assembled a join rows_ source_ on source_.business_date=a.business_date and source_.row_ordinal=a.row_ordinal),'[]'));
$$;


create or replace function ecos_meta.staffing_statistics(domain_ text, mode_ text, site_ text)
returns jsonb language sql stable set search_path=pg_catalog set jit=off as $$
 select ecos_meta.staffing_statistics(domain_,mode_,site_,null,null);
$$;
create function ecos.staffing_features_read(site text, from_date date, through_date date) returns jsonb
language plpgsql stable security definer set search_path=pg_catalog set jit=off as $$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 if from_date is null or through_date is null or through_date<from_date or through_date-from_date>30 then
  raise exception 'bounded_staffing_date_window_required' using errcode='22023';
 end if;
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id;
 if b.domain not in ('toast.acquisition','staffing.features') or b.principal_id is null then
  raise exception 'forbidden' using errcode='42501';
 end if;
 return ecos_meta.staffing_statistics('toast.acquisition',b.execution_mode,site,from_date,through_date);
end $$;
revoke all on function ecos_meta.staffing_statistics(text,text,text,date,date) from public,executor,operations_api,provider_adapter;
revoke all on function ecos.staffing_features_read(text,date,date) from public;
grant execute on function ecos.staffing_features_read(text,date,date) to executor;
reset role;

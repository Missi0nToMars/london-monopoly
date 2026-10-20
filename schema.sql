-- Run once in the Supabase SQL Editor. All application access is server-only.
create table if not exists public.monopoly_rooms (
  code text primary key check (code ~ '^[A-Z2-9]{6}$'),
  version bigint not null default 0,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists public.monopoly_receipts (
  code text not null references public.monopoly_rooms(code) on delete cascade,
  action text not null,
  primary key(code, action)
);
alter table public.monopoly_rooms enable row level security;
alter table public.monopoly_receipts enable row level security;
revoke all on public.monopoly_rooms, public.monopoly_receipts from anon, authenticated;

create or replace function public.monopoly_create(p_code text,p_payload jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
  insert into public.monopoly_rooms(code,payload) values(p_code,p_payload) on conflict do nothing;
  return found;
end $$;

create or replace function public.monopoly_read(p_code text)
returns jsonb language sql security invoker set search_path='' as $$
 select jsonb_build_object('version',version,'payload',payload)
 from public.monopoly_rooms where code=p_code;
$$;

create or replace function public.monopoly_commit(p_code text,p_expected bigint,p_payload jsonb,p_action text)
returns text language plpgsql security invoker set search_path='' as $$
declare actual bigint;
begin
  select version into actual from public.monopoly_rooms where code=p_code for update;
  if exists(select 1 from public.monopoly_receipts where code=p_code and action=p_action) then
    return 'duplicate';
  end if;
  if actual is null or actual <> p_expected then return 'conflict'; end if;
  update public.monopoly_rooms set payload=p_payload,version=version+1,updated_at=now() where code=p_code;
  insert into public.monopoly_receipts(code,action) values(p_code,p_action);
  return 'ok';
end $$;

revoke all on function public.monopoly_create(text,jsonb) from public,anon,authenticated;
revoke all on function public.monopoly_read(text) from public,anon,authenticated;
revoke all on function public.monopoly_commit(text,bigint,jsonb,text) from public,anon,authenticated;
grant usage on schema public to service_role;
grant all on public.monopoly_rooms, public.monopoly_receipts to service_role;
grant execute on function public.monopoly_create(text,jsonb) to service_role;
grant execute on function public.monopoly_read(text) to service_role;
grant execute on function public.monopoly_commit(text,bigint,jsonb,text) to service_role;

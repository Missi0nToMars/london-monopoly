"""Custom rules, authoritative clocks, concurrency and unfair host powers."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
import engine as e
from store import SQLiteBackend,Service,Conflict
from test_game import game,own,levels,dice

def lobby():
    s=e.new_game()
    s=e.join(s,'0','Alice','🚗');s=e.join(s,'1','Bob','🎩')
    return s

def timed(n=3,now=1000):
    s=game(n);e.sync_clock(s,now);return s

def expire(s,monkeypatch):
    now=s['clock']['deadline']+.1
    monkeypatch.setattr(e.time,'time',lambda:now)
    return e.tick(s,now)

def unlock(s):
    return e.apply(s,'0','admin_mode',enabled=True,unlock_code='676767')

def test_rule_permissions_validation_and_readiness():
    s=lobby();s['players']['0']['ready']=True
    for pid,changes in [('1',{'starting_cash':2000}),('0',{'starting_cash':True}),('0',{'miss_limit':1}),('0',{'unknown':1})]:
        with pytest.raises(e.RuleError):e.apply(s,pid,'configure',rules=changes)
    result=e.apply(s,'0','configure',rules={'starting_cash':2000,'clock_enabled':False})
    assert all(p['money']==2000 and not p['ready'] for p in result['players'].values())
    assert s['players']['0']['money']==1500
    result['status']='playing'
    with pytest.raises(e.RuleError,match='locked'):e.apply(result,'0','configure',rules={'starting_cash':3000})

def test_legacy_games_do_not_acquire_clock():
    s=game();s.pop('rules');before=copy.deepcopy(s)
    assert e.tick(s,10000000000)==before
    assert e.room_rules(s)['clock_enabled'] is False

def test_custom_go_tax_and_parking(monkeypatch):
    s=game();s['rules'].update(go_salary=300,double_go=True,free_parking=True,income_tax=75)
    s['players']['0']['pos']=38;dice(monkeypatch,1,1)
    s=e.apply(s,'0','roll');assert s['players']['0']['money']==2100
    s['queue']=[dict(type='land',pid='0',special=None)];s['players']['0']['pos']=4;e.pump(s)
    assert s['players']['0']['money']==2025 and s['parking_pot']==75
    s['queue']=[dict(type='land',pid='1',special=None)];s['players']['1']['pos']=20;e.pump(s)
    assert s['players']['1']['money']==1575 and s['parking_pot']==0

def test_custom_building_rent_and_declined_purchase():
    s=game();own(s,'0',[1,3]);s['rules'].update(even_build=False,rent_in_jail=False,decline_auction=False)
    s=e.apply(s,'0','build',property=1);s=e.apply(s,'0','build',property=1)
    assert e.deed(s,1)['level']==2
    s['players']['0']['jail']=True;assert e.rent(s,1,7)==0
    s['queue']=[dict(type='purchase',pid='1',property=8)]
    s=e.apply(s,'1','decline');assert not s['auction'] and e.deed(s,8)['owner'] is None

def test_custom_jail_fine(monkeypatch):
    s=game();s['rules']['jail_fine']=10;s['players']['0']['jail']=True
    s=e.apply(s,'0','jail_pay');assert s['players']['0']['money']==1490

def test_clock_roll_purchase_end_and_removal(monkeypatch):
    s=timed();dice(monkeypatch,1,2)
    first=expire(s,monkeypatch)
    assert first['roll_id']==1 and first['players']['0']['missed_decisions']==1
    assert first['queue'][0]['type']=='purchase'
    second=expire(first,monkeypatch)
    assert second['players']['0']['bankrupt'] and e.current(second)=='1'
    assert s['roll_id']==0

def test_expired_human_action_rejected_and_manual_response_resets_misses(monkeypatch):
    s=timed();monkeypatch.setattr(e.time,'time',lambda:s['clock']['deadline']+1)
    with pytest.raises(e.RuleError,match='expired'):e.apply(s,'0','roll')
    monkeypatch.setattr(e.time,'time',lambda:1001);s['players']['0']['missed_decisions']=1
    dice(monkeypatch,1,2);s=e.apply(s,'0','roll')
    assert s['players']['0']['missed_decisions']==0

def test_clock_does_not_reset_for_trade_or_nondecision_action(monkeypatch):
    s=timed();monkeypatch.setattr(e.time,'time',lambda:1010)
    result=e.apply(s,'1','offer',to='2',give_cash=1)
    assert result['clock']['deadline']==s['clock']['deadline']

def test_debt_timeout_grace_then_forfeit_preserves_creditor(monkeypatch):
    s=game(3);s['queue']=[e.pay_task('1',1600,'2','Rent')];e.sync_clock(s,1000)
    first=expire(s,monkeypatch)
    assert not first['players']['1']['bankrupt'] and first['clock']['deadline']>s['clock']['deadline']
    result=expire(first,monkeypatch)
    assert result['players']['1']['bankrupt'] and result['players']['2']['money']==3000

def test_auction_and_building_timeout_default_to_pass(monkeypatch):
    s=game(3);e.auction_start(s,1);e.sync_clock(s,1000)
    first=expire(s,monkeypatch)
    assert '0' in first['auction']['passed'] and first['clock']['pid']=='1'
    s=game(3);s['building_request']=dict(kind='houses',eligible=['0','1'],responses={});e.sync_clock(s,2000)
    result=expire(s,monkeypatch)
    assert result['building_request']['responses']=={'0':None}

def test_clock_extension_permissions_and_limit(monkeypatch):
    s=timed();monkeypatch.setattr(e.time,'time',lambda:1001)
    with pytest.raises(e.RuleError):e.apply(s,'1','extend_clock')
    due=s['clock']['deadline']
    for _ in range(5):s=e.apply(s,'0','extend_clock')
    assert s['clock']['deadline']==due+300
    with pytest.raises(e.RuleError):e.apply(s,'0','extend_clock')

def test_admin_code_and_host_auth_are_both_required():
    s=lobby()
    with pytest.raises(e.RuleError):e.apply(s,'0','admin_mode',enabled=True,unlock_code='000000')
    with pytest.raises(e.RuleError):e.apply(s,'1','admin_mode',enabled=True,unlock_code='676767')
    s['players']['1']['ready']=True
    s=unlock(s);assert s['admin_enabled'] and not s['players']['1']['ready']
    s['status']='playing'
    with pytest.raises(e.RuleError):e.apply(s,'1','admin',power='add_cash',target='1',amount=999)
    s=e.apply(s,'0','admin_mode',enabled=False)
    with pytest.raises(e.RuleError):e.apply(s,'0','admin',power='win',target='0')

@pytest.mark.parametrize('power',['take_property','take_set','free_hotels'])
def test_admin_deeds_keep_supply_and_ownership_valid(power):
    s=unlock(game(3));own(s,'1',[1,3]);levels(s,{1:1,3:1})
    s=e.apply(s,'0','admin',power=power,target='0',property=1)
    e.validate(s);assert e.deed(s,1)['owner']=='0'
    assert 'ADMIN' in s['events'][-1]
    if power=='free_hotels':assert s['hotels']==10 and e.deed(s,3)['level']==5

def test_admin_cash_rigged_dice_jail_move_and_win():
    s=unlock(game(3))
    s=e.apply(s,'0','admin',power='add_cash',target='0',amount=9000);assert s['players']['0']['money']==10500
    s=e.apply(s,'0','admin',power='set_cash',target='1',amount=5);assert s['players']['1']['money']==5
    s=e.apply(s,'0','admin',power='jail',target='1');assert s['players']['1']['jail']
    s=e.apply(s,'0','admin',power='teleport',target='1',destination=39);assert not s['players']['1']['jail']
    s=e.apply(s,'0','admin',power='force_dice',target='0',dice=[2,4])
    s=e.apply(s,'0','roll');assert s['dice']==[2,4] and 'rigged_dice' not in s
    s['queue']=[]
    s=e.apply(s,'0','admin',power='win',target='2');assert s['winner']=='2' and not s.get('clock')

def test_admin_forged_roll_args_and_invalid_power_fail(monkeypatch):
    s=game();dice(monkeypatch,1,2)
    result=e.apply(s,'0','roll',dice=[6,6],automatic=True,clock_now=999999)
    assert result['dice']==[1,2]
    s=unlock(game())
    with pytest.raises(e.RuleError):e.apply(s,'0','admin',power='unsupported',target='0')

def test_two_readers_only_apply_one_expired_decision(tmp_path,monkeypatch):
    backend=SQLiteBackend(tmp_path/'clock.db');service=Service(backend)
    alice=service.create('Alice','🚗');bob=service.join(alice['code'],'Bob','🎩')
    record=backend.read(alice['code']);s=record['payload']['state'];s.update(status='playing',turn=0,stage='end')
    e.sync_clock(s,1000);backend.commit(alice['code'],record['version'],record['payload'],'a'*32)
    monkeypatch.setattr(e.time,'time',lambda:1061)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda c:Service(backend).read(c['code'],c['session']),[alice,bob]))
    final=backend.read(alice['code'])['payload']['state']
    assert final['players'][alice['pid']]['missed_decisions']==1
    assert final['turn']==1
    assert sum('Automatic action' in x for x in final['events'])==1

def test_service_unlock_and_power_use_the_authenticated_host(tmp_path):
    backend=SQLiteBackend(tmp_path/'admin.db');service=Service(backend)
    host=service.create('Host','🚗');guest=service.join(host['code'],'Guest','🎩')
    _,v,_=service.read(host['code'],host['session'])
    with pytest.raises(e.RuleError):
        Service(backend).act(guest['code'],guest['session'],v,'c'*32,'admin_mode',enabled=True,unlock_code='676767')
    service.act(host['code'],host['session'],v,'d'*32,'admin_mode',enabled=True,unlock_code='676767')
    result,_,_=Service(backend).read(host['code'],host['session'])
    assert result['admin_enabled']
    assert not any('676767' in event for event in result['events'])


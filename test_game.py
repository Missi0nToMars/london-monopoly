"""Rules, all spaces/cards, secure sessions, concurrency and six-player simulations."""
import copy
from concurrent.futures import ThreadPoolExecutor
import random
import uuid
import pytest
import engine as e
from data import BOARD, DEEDS, GROUPS, DECKS, TOKENS
from store import Service, SQLiteBackend, Conflict


def game(n=2):
    s=e.new_game()
    for i in range(n):
        s=e.join(s,str(i),"Player "+str(i),TOKENS[i])
    s.update(status="playing",turn=0)
    return s


def own(s,pid,ids):
    for i in ids:
        e.deed(s,i)["owner"]=pid


def levels(s,values):
    for i,n in values.items():
        e.deed(s,i)["level"]=n
    s["houses"]=32-sum(d["level"] for d in s["deeds"].values() if d["level"]<5)
    s["hotels"]=12-sum(d["level"]==5 for d in s["deeds"].values())


def dice(monkeypatch,*values):
    iterator=iter(values)
    monkeypatch.setattr(e.secrets,"randbelow",lambda n:next(iterator)-1)


def test_board_reference():
    assert len(BOARD)==40 and len(DEEDS)==28
    assert [BOARD[i].name for i in [0,10,20,30,39]]==["GO","Jail / Just Visiting","Free Parking","Go to Jail","Mayfair"]
    assert len(GROUPS)==8 and sum(map(len,GROUPS.values()))==22
    assert [b.price for b in BOARD if b.kind=="tax"]==[200,100]


@pytest.mark.parametrize("index",range(40))
def test_all_spaces_resolve(index):
    s=game()
    s["players"]["0"]["pos"]=index
    s["queue"]=[dict(type="land",pid="0",special=None)]
    e.pump(s)
    e.validate(s)
    if index in DEEDS:
        assert s["queue"][0]==dict(type="purchase",pid="0",property=index)
    if index==30:
        assert s["players"]["0"]["jail"]


@pytest.mark.parametrize("deck,index",[(k,i) for k,v in DECKS.items() for i in range(len(v))])
def test_all_cards(deck,index):
    s=game(6)
    s["players"]["0"]["pos"]=36 if deck=="chance" else 33
    s["decks"][deck].remove(index)
    s["decks"][deck].insert(0,index)
    e.draw(s,"0",deck)
    e.pump(s)
    e.validate(s)
    assert any(DECKS[deck][index][0] in text for text in s["events"])


def test_go_salary_and_backwards():
    s=game()
    s["players"]["0"]["pos"]=39
    s["queue"]=[e.move_task("0",0)]
    e.pump(s)
    assert s["players"]["0"]["money"]==1700
    s["queue"]=[e.move_task("0",39,False)]
    e.pump(s)
    assert s["players"]["0"]["money"]==1700


def test_doubles_and_triple_jail(monkeypatch):
    s=game()
    dice(monkeypatch,1,1,3,3,2,2)
    s=e.apply(s,"0","roll")
    assert s["stage"]=="roll"
    s["queue"]=[]
    s=e.apply(s,"0","roll")
    s["queue"]=[]
    s=e.apply(s,"0","roll")
    assert s["players"]["0"]["jail"] and s["stage"]=="end"


def test_jail_double_no_bonus(monkeypatch):
    s=game()
    e.send_jail(s,"0")
    s["stage"]="roll"
    dice(monkeypatch,2,2)
    s=e.apply(s,"0","roll")
    assert not s["players"]["0"]["jail"] and s["stage"]=="end"


def test_jail_third_turn_fine_before_move(monkeypatch):
    s=game()
    e.send_jail(s,"0")
    s["players"]["0"].update(money=0,jail_turns=2)
    own(s,"0",[1])
    s["stage"]="roll"
    dice(monkeypatch,1,2)
    s=e.apply(s,"0","roll")
    assert s["players"]["0"]["pos"]==10 and s["queue"][0]["amount"]==50
    # Cannot raise enough from this mortgage; debt remains, bankruptcy permitted.
    s=e.apply(s,"0","mortgage",property=1)
    assert s["queue"][0]["type"]=="pay"


def test_buy_and_auction_decliner_can_bid():
    s=game(3)
    s["queue"]=[dict(type="purchase",pid="0",property=1)]
    s=e.apply(s,"0","decline")
    s=e.apply(s,"0","bid",amount=1)
    s=e.apply(s,"1","pass")
    s=e.apply(s,"2","pass")
    assert e.deed(s,1)["owner"]=="0" and s["players"]["0"]["money"]==1499


def test_auction_no_bids_and_bid_reservation():
    s=game()
    e.auction_start(s,1)
    s=e.apply(s,"0","bid",amount=1499)
    own(s,"0",[3])
    e.deed(s,3)["mortgaged"]=True
    with pytest.raises(e.RuleError):
        e.apply(s,"0","unmortgage",property=3)
    s=e.apply(s,"1","pass")
    assert not s["auction"]
    e.auction_start(s,5)
    s=e.apply(s,"0","pass")
    s=e.apply(s,"1","pass")
    assert not s["auction"] and e.deed(s,5)["owner"] is None


@pytest.mark.parametrize("i",DEEDS)
def test_purchase_all_deeds(i):
    s=game()
    s["queue"]=[dict(type="purchase",pid="0",property=i)]
    s=e.apply(s,"0","buy")
    assert e.deed(s,i)["owner"]=="0" and s["players"]["0"]["money"]==1500-BOARD[i].price


def test_rents_and_mortgages():
    s=game()
    own(s,"0",[1,3,5,15,25,35,12,28])
    assert e.rent(s,1,7)==4 and e.rent(s,35,7)==200 and e.rent(s,12,7)==70
    s=e.apply(s,"0","mortgage",property=3)
    assert e.rent(s,1,7)==4 and e.rent(s,3,7)==0
    s=e.apply(s,"0","mortgage",property=5)
    assert e.rent(s,15,7)==200 and e.rent(s,5,7)==0
    assert e.rent(s,15,7,"station")==400
    s=e.apply(s,"0","unmortgage",property=3)
    assert s["players"]["0"]["money"]==1597


def test_building_evenness_hotels_supply():
    s=game()
    own(s,"0",[1,3])
    s=e.apply(s,"0","build",property=1)
    with pytest.raises(e.RuleError):
        e.apply(s,"0","build",property=1)
    for i in [3,1,3,1,3,1,3,1,3]:
        s=e.apply(s,"0","build",property=i)
    assert e.deed(s,1)["level"]==5 and e.deed(s,3)["level"]==5
    assert s["houses"]==32 and s["hotels"]==10 and e.rent(s,1,7)==250
    s=e.apply(s,"0","sell",property=1)
    assert s["houses"]==28 and s["hotels"]==11
    with pytest.raises(e.RuleError):
        e.apply(s,"0","mortgage",property=1)
    s=e.apply(s,"0","sell_set",property=3)
    assert s["houses"]==32 and s["hotels"]==12


def test_no_build_if_group_mortgaged():
    s=game()
    own(s,"0",[1,3])
    s=e.apply(s,"0","mortgage",property=3)
    with pytest.raises(e.RuleError):
        e.apply(s,"0","build",property=1)


def test_shortage_building_auction():
    s=game(3)
    own(s,"0",[1,3,6,8,9,11,13,14])
    own(s,"1",[16,18,19])
    levels(s,{1:4,3:4,6:4,8:4,9:4,11:4,13:4,14:3})
    # 31 houses in play, two owners can use the remaining house.
    s=e.apply(s,"0","build",property=14)
    assert s["building_request"]
    s=e.apply(s,"1","building_reply",property=16)
    assert s["auction"]["targets"]=={"0":14,"1":16}
    s=e.apply(s,"1","bid",amount=75)
    s=e.apply(s,"0","pass")
    assert s["houses"]==0 and e.deed(s,16)["level"]==1


def test_trade_and_mortgage_interest():
    s=game()
    own(s,"0",[1])
    own(s,"1",[39])
    s=e.apply(s,"1","mortgage",property=39)
    s=e.apply(s,"0","offer",to="1",give=[1],take=[39],give_cash=100)
    s=e.apply(s,"1","accept",id=s["trades"][0]["id"])
    assert e.deed(s,39)["owner"]=="0" and e.deed(s,39)["mortgaged"]
    assert s["players"]["0"]["money"]==1380
    s=e.apply(s,"0","unmortgage",property=39)
    assert s["players"]["0"]["money"]==1160


def test_trade_redeem_now_and_stale_offer():
    s=game(3)
    own(s,"0",[1])
    s=e.apply(s,"0","mortgage",property=1)
    s=e.apply(s,"0","offer",to="1",give=[1])
    first=s["trades"][0]["id"]
    s=e.apply(s,"0","offer",to="2",give=[1])
    s=e.apply(s,"1","accept",id=first,redeem=[1])
    assert not e.deed(s,1)["mortgaged"] and s["players"]["1"]["money"]==1467
    with pytest.raises(e.RuleError):
        e.apply(s,"2","accept",id=s["trades"][0]["id"])


def test_trading_improved_group_forbidden():
    s=game()
    own(s,"0",[1,3])
    s=e.apply(s,"0","build",property=1)
    with pytest.raises(e.RuleError):
        e.apply(s,"0","offer",to="1",give=[3])


def test_debt_raise_funds_automatic_settlement():
    s=game()
    own(s,"0",[39])
    s["players"]["0"]["money"]=10
    s["queue"]=[e.pay_task("0",150,"1","Rent")]
    s=e.apply(s,"0","mortgage",property=39)
    assert not s["queue"] and s["players"]["0"]["money"]==60 and s["players"]["1"]["money"]==1650


def test_bankruptcy_to_player_inheritance():
    s=game(3)
    own(s,"0",[39])
    e.deed(s,39)["mortgaged"]=True
    s["players"]["0"]["money"]=10
    s["queue"]=[e.pay_task("0",1000,"1","Rent")]
    s=e.apply(s,"0","bankrupt")
    assert e.deed(s,39)["owner"]=="1" and s["queue"][0]["type"]=="inherit"
    s=e.apply(s,"1","inherit",mode="keep")
    assert s["players"]["1"]["money"]==1490 and not s["queue"]


def test_bankruptcy_to_bank_auctions_and_winner():
    s=game(3)
    own(s,"0",[1,3])
    s["players"]["0"]["money"]=0
    s["queue"]=[e.pay_task("0",1000)]
    s=e.apply(s,"0","bankrupt")
    assert s["auction"]["property"]==1
    for q in ["1","2"]:
        s=e.apply(s,q,"pass")
    assert s["auction"]["property"]==3
    for q in ["1","2"]:
        s=e.apply(s,q,"pass")
    s["players"]["1"]["money"]=0
    s["queue"]=[e.pay_task("1",1000)]
    s=e.apply(s,"1","bankrupt")
    assert s["winner"]=="2" and s["status"]=="finished"


def test_cannot_declare_premature_bankruptcy():
    s=game()
    own(s,"0",[39])
    s["players"]["0"]["money"]=0
    s["queue"]=[e.pay_task("0",100)]
    with pytest.raises(e.RuleError):
        e.apply(s,"0","bankrupt")


def test_out_of_turn_illegal_action_immutable():
    s=game()
    original=copy.deepcopy(s)
    for action,kw in [("roll",{}),("buy",{}),("mortgage",{"property":1}),("offer",{"to":"0","give_cash":-1})]:
        with pytest.raises(e.RuleError):
            e.apply(s,"1",action,**kw)
        assert s==original


def test_lobby_requires_ready_and_unique_tokens():
    s=e.join(e.new_game(),"0","Alice",TOKENS[0])
    with pytest.raises(e.RuleError):
        e.join(s,"1","Bob",TOKENS[0])
    s=e.join(s,"1","Bob",TOKENS[1])
    with pytest.raises(e.RuleError):
        e.apply(s,"0","start")
    s=e.apply(s,"0","ready")
    s=e.apply(s,"1","ready")
    s=e.apply(s,"0","start")
    assert s["status"]=="playing" and e.current(s) in ["0","1"]


def test_private_sessions_refresh_and_six_seats(tmp_path):
    service=Service(SQLiteBackend(tmp_path/"test.db"))
    c=service.create("P0",TOKENS[0])
    friends=[service.join(c["code"],"P"+str(i),TOKENS[i]) for i in range(1,6)]
    state,v,pid=service.read(c["code"],c["session"])
    assert len(state["players"])==6 and pid==c["pid"]
    reconnected=Service(SQLiteBackend(tmp_path/"test.db"))
    assert reconnected.read(c["code"],c["session"])[0]==state
    with pytest.raises(e.RuleError):
        service.read(c["code"],"invalid-session-token-"+"x"*20)
    with pytest.raises(e.RuleError):
        service.join(c["code"],"P6",TOKENS[0])


def test_concurrent_actions_one_commit_and_duplicate_receipt(tmp_path):
    backend=SQLiteBackend(tmp_path/"test.db")
    service=Service(backend)
    c=service.create("P0",TOKENS[0])
    _,v,_=service.read(c["code"],c["session"])
    def action(_):
        try:
            return service.act(c["code"],c["session"],v,uuid.uuid4().hex,"ready")
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(action,range(8)))
    assert results.count("ok")==1 and results.count("conflict")==7
    record=backend.read(c["code"])
    action_id=uuid.uuid4().hex
    assert backend.commit(c["code"],record["version"],record["payload"],action_id)=="ok"
    assert backend.commit(c["code"],record["version"],record["payload"],action_id)=="duplicate"
    assert backend.read(c["code"])["version"]==2


@pytest.mark.parametrize("seed",[7,31,93])
def test_six_player_game_to_completion(seed,monkeypatch):
    rng=random.Random(seed)
    monkeypatch.setattr(e.secrets,"randbelow",lambda n:rng.randrange(n))
    s=game(6)
    for step in range(30000):
        e.validate(s)
        if s["status"]=="finished":
            assert len(e.living(s))==1
            return
        a=s["auction"]
        if a:
            active=[q for q in a["eligible"] if q not in a["passed"]]
            bidders=[q for q in active if q!=a["leader"]]
            q=bidders[0] if bidders else active[0]
            value=BOARD[a["property"]].price if a["property"] is not None else 100
            if a["bid"]==0 and s["players"][q]["money"]>value:
                s=e.apply(s,q,"bid",amount=max(1,value//2))
            else:
                s=e.apply(s,q,"pass")
            continue
        if s["building_request"]:
            r=s["building_request"]
            q=next(q for q in r["eligible"] if q not in r["responses"])
            s=e.apply(s,q,"building_reply",property=None)
            continue
        if s["queue"]:
            t=s["queue"][0]
            q=t["pid"]
            if t["type"]=="purchase":
                s=e.apply(s,q,"buy" if s["players"][q]["money"]>=BOARD[t["property"]].price+100 else "decline")
            elif t["type"]=="inherit":
                s=e.apply(s,q,"inherit",mode="keep")
            elif t["type"]=="pay":
                if e.liquid_value(s,q)<t["amount"]:
                    s=e.apply(s,q,"bankrupt")
                else:
                    improved=[i for i in e.owned(s,q) if e.deed(s,i)["level"]]
                    if improved:
                        s=e.apply(s,q,"sell_set",property=improved[0])
                    else:
                        i=next(i for i in e.owned(s,q) if not e.deed(s,i)["mortgaged"])
                        s=e.apply(s,q,"mortgage",property=i)
            continue
        q=e.current(s)
        # Test participants negotiate cash sales to complete colour sets.
        # These use the same offer/accept actions as human players, without
        # changing any game rule or directly assigning ownership.
        traded=False
        for ids in GROUPS.values():
            if not any(e.deed(s,i)["owner"]==q for i in ids):
                continue
            for i in ids:
                owner=e.deed(s,i)["owner"]
                price=BOARD[i].price*2
                if owner and owner!=q and not e.monopoly(s,owner,i) and s["players"][q]["money"]>price+300:
                    try:
                        s=e.apply(s,q,"offer",to=owner,take=[i],give_cash=price)
                        s=e.apply(s,owner,"accept",id=s["trades"][-1]["id"])
                        traded=True
                        break
                    except e.RuleError:
                        continue
            if traded:
                break
        if traded:
            continue
        built=False
        for i in e.owned(s,q):
            try:
                if s["players"][q]["money"]>BOARD[i].build+250 and s[e.can_build(s,q,i)]>0:
                    s=e.apply(s,q,"build",property=i)
                    built=True
                    break
            except e.RuleError:
                continue
        if built:
            continue
        s=e.apply(s,q,"roll" if s["stage"]=="roll" else "end")
    pytest.fail(f"Six-player simulation seed {seed} did not finish in {step+1} actions")

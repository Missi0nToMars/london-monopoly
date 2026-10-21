"""Server-only, serializable rules engine. Rejected actions never mutate input state."""
import copy
import secrets
from data import BOARD, DEEDS, GROUPS, DECKS, TOKENS


class RuleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuleError(message)


def number(value, low=0, high=1_000_000):
    require(type(value) is int and low <= value <= high, "Enter a valid whole amount.")
    return value


def log(s, text):
    s["events"].append(text)
    s["events"] = s["events"][-300:]


def new_game():
    decks = {k: list(range(len(v))) for k,v in DECKS.items()}
    for deck in decks.values():
        secrets.SystemRandom().shuffle(deck)
    return dict(players={}, order=[], host=None, status="lobby", turn=0, stage="roll",
                doubles=0, dice=[1,1], roll_id=0, decks=decks, queue=[], trades=[],
                deeds={str(i): dict(owner=None, level=0, mortgaged=False) for i in DEEDS},
                houses=32, hotels=12, events=["A new London table is open."], winner=None,
                last_card=None, auction=None, building_request=None)


def join(s, pid, name, token):
    s = copy.deepcopy(s)
    require(s["status"] == "lobby", "This game has already started.")
    require(len(s["players"]) < 6, "This table is full.")
    require(pid not in s["players"], "You already joined this table.")
    name = str(name).strip()
    require(1 <= len(name) <= 24 and not any(ord(c)<32 for c in name), "Use a name of 1–24 characters.")
    require(not any(p["name"].casefold()==name.casefold() for p in s["players"].values()), "That name is in use.")
    require(token in TOKENS and not any(p["token"]==token for p in s["players"].values()), "Choose an available token.")
    s["players"][pid] = dict(id=pid,name=name,token=token,money=1500,pos=0,jail=False,
                             jail_turns=0,cards=[],bankrupt=False,ready=False)
    s["order"].append(pid)
    if s["host"] is None:
        s["host"] = pid
    log(s, f"{name} joined the table.")
    return s


def living(s):
    return [i for i in s["order"] if not s["players"][i]["bankrupt"]]


def current(s):
    return s["order"][s["turn"]] if s["order"] else None


def deed(s, i):
    require(str(i) in s["deeds"], "Choose a property.")
    return s["deeds"][str(i)]


def owned(s, pid):
    return [i for i in DEEDS if deed(s,i)["owner"] == pid]


def group(s, i):
    return GROUPS.get(BOARD[i].group, [i])


def monopoly(s, pid, i):
    return BOARD[i].kind == "street" and all(deed(s,j)["owner"] == pid for j in group(s,i))


def rent(s, i, dice, special=None):
    d, b = deed(s,i), BOARD[i]
    if not d["owner"] or d["mortgaged"]:
        return 0
    if b.kind == "street":
        return b.rents[d["level"]] * (2 if d["level"]==0 and monopoly(s,d["owner"],i) else 1)
    count = sum(BOARD[j].kind == b.kind for j in owned(s,d["owner"]))
    if b.kind == "station":
        return 25 * 2**(count-1) * (2 if special=="station" else 1)
    return dice * (10 if count==2 or special=="utility" else 4)


def cash_available(s, pid):
    held = s["auction"]["bid"] if s["auction"] and s["auction"]["leader"]==pid else 0
    return s["players"][pid]["money"] - held


def spend(s, pid, amount):
    require(cash_available(s,pid) >= amount, "You need more available cash. Sell buildings, mortgage, or trade.")
    s["players"][pid]["money"] -= amount


def pay_task(pid, amount, to=None, reason="Payment"):
    return dict(type="pay",pid=pid,amount=amount,to=to,reason=reason)


def move_task(pid, dest, salary=True, special=None):
    return dict(type="move",pid=pid,dest=dest,salary=salary,special=special)


def record_move(s,pid,origin,destination,direction=1):
    """Persist actual square-by-square routes, including chained card moves."""
    distance=(destination-origin)*direction%40
    path=[(origin+direction*step)%40 for step in range(1,distance+1)]
    s["motion_seq"]=s.get("motion_seq",0)+1
    s.setdefault("motions",[]).append(dict(seq=s["motion_seq"],pid=pid,path=path))
    s["motions"]=s["motions"][-24:]


def send_jail(s, pid):
    p=s["players"][pid]
    record_move(s,pid,p["pos"],10)
    p.update(pos=10,jail=True,jail_turns=0)
    if current(s)==pid:
        s.update(stage="end",doubles=0)
    log(s, f"{p['name']} went directly to jail.")


def draw(s, pid, deck):
    index=s["decks"][deck].pop(0)
    text, op, amount=DECKS[deck][index]
    s["last_card"]={"deck":deck,"text":text,"pid":pid}
    log(s, f"{s['players'][pid]['name']} · {text}")
    if op=="jailfree":
        s["players"][pid]["cards"].append(deck)
        return
    s["decks"][deck].append(index)
    tasks=[]
    p=s["players"][pid]
    if op=="cash":
        if amount>=0:
            p["money"]+=amount
        else:
            tasks=[pay_task(pid,-amount,reason=text)]
    elif op=="move":
        tasks=[move_task(pid,amount)]
    elif op=="back":
        tasks=[move_task(pid,(p["pos"]-amount)%40,False)]
    elif op in {"station","utility"}:
        options=[i for i in DEEDS if BOARD[i].kind==op]
        dest=next((i for i in options if i>p["pos"]),options[0])
        tasks=[move_task(pid,dest,special=op)]
    elif op=="jail":
        send_jail(s,pid)
    elif op=="repairs":
        houses=sum(deed(s,i)["level"] for i in owned(s,pid) if deed(s,i)["level"]<5)
        hotels=sum(deed(s,i)["level"]==5 for i in owned(s,pid))
        tasks=[pay_task(pid,houses*amount[0]+hotels*amount[1],reason=text)]
    elif op=="each":
        tasks=[pay_task(other,amount,pid,text) if amount>0 else pay_task(pid,-amount,other,text)
               for other in living(s) if other!=pid]
    s["queue"][0:0]=tasks


def auction_start(s, i, targets=None):
    s["auction"]=dict(property=i,targets=targets,leader=None,bid=0,passed=[],
                       eligible=list(targets) if targets is not None else living(s))
    label="a building" if targets is not None else BOARD[i].name
    log(s, f"Auction opened for {label}. Everyone eligible may bid, including the player who declined.")


def pump(s):
    """Resolve deterministic obligations; stop at a human decision or insolvency."""
    if s["auction"] or s["building_request"]:
        return
    while s["queue"] and s["status"]=="playing":
        t=s["queue"][0]
        pid=t.get("pid")
        if pid and s["players"][pid]["bankrupt"]:
            s["queue"].pop(0)
            continue
        kind=t["type"]
        if kind in {"purchase","inherit"}:
            return
        if kind=="pay":
            if t["to"] and s["players"][t["to"]]["bankrupt"]:
                s["queue"].pop(0)
                continue
            if s["players"][pid]["money"]<t["amount"]:
                return
            s["players"][pid]["money"]-=t["amount"]
            if t["to"]:
                s["players"][t["to"]]["money"]+=t["amount"]
            log(s,f"{s['players'][pid]['name']} paid £{t['amount']:,} · {t['reason']}")
        elif kind=="move":
            p=s["players"][pid]
            if t["salary"] and t["dest"]<p["pos"]:
                p["money"]+=200
                log(s,f"{p['name']} collected £200 for passing GO.")
            record_move(s,pid,p["pos"],t["dest"],-1 if not t["salary"] else 1)
            p["pos"]=t["dest"]
            log(s,f"{p['name']} landed on {BOARD[p['pos']].name}.")
            s["queue"].pop(0)
            s["queue"].insert(0,dict(type="land",pid=pid,special=t["special"]))
            continue
        elif kind=="land":
            s["queue"].pop(0)
            p=s["players"][pid]
            b=BOARD[p["pos"]]
            if b.id in DEEDS:
                d=deed(s,b.id)
                if not d["owner"]:
                    s["queue"].insert(0,dict(type="purchase",pid=pid,property=b.id))
                elif d["owner"]!=pid:
                    dice=sum(s["dice"])
                    if t.get("special")=="utility" and not d["mortgaged"]:
                        rolled=[secrets.randbelow(6)+1,secrets.randbelow(6)+1]
                        dice=sum(rolled)
                        log(s,f"Utility rent dice: {rolled[0]} + {rolled[1]} = {dice}.")
                    amount=rent(s,b.id,dice,t.get("special"))
                    if amount:
                        s["queue"].insert(0,pay_task(pid,amount,d["owner"],b.name+" rent"))
            elif b.kind=="tax":
                s["queue"].insert(0,pay_task(pid,b.price,reason=b.name))
            elif b.kind in DECKS:
                draw(s,pid,b.kind)
            elif b.kind=="gotojail":
                send_jail(s,pid)
            continue
        elif kind=="auction":
            s["queue"].pop(0)
            auction_start(s,t["property"])
            return
        else:
            raise RuleError("Unknown pending obligation.")
        s["queue"].pop(0)


def end_turn(s):
    for _ in s["order"]:
        s["turn"]=(s["turn"]+1)%len(s["order"])
        if not s["players"][current(s)]["bankrupt"]:
            break
    s.update(stage="roll",doubles=0)
    log(s,f"It is {s['players'][current(s)]['name']}'s turn.")


def can_build(s,pid,i,check_cash=True):
    d,b=deed(s,i),BOARD[i]
    require(monopoly(s,pid,i),"You need the complete colour set.")
    require(not any(deed(s,j)["mortgaged"] for j in group(s,i)),"Unmortgage the entire colour set first.")
    require(d["level"]<5 and d["level"]==min(deed(s,j)["level"] for j in group(s,i)),"Build evenly, up to one hotel per street.")
    if check_cash:
        require(cash_available(s,pid)>=b.build,"You need more cash for this building.")
    return "hotels" if d["level"]==4 else "houses"


def add_building(s,pid,i,price):
    kind=can_build(s,pid,i,False)
    require(s[kind]>0,"The bank has none of this building left.")
    spend(s,pid,price)
    s[kind]-=1
    if kind=="hotels":
        s["houses"]+=4
    deed(s,i)["level"]+=1
    log(s,f"{s['players'][pid]['name']} built on {BOARD[i].name} for £{price}.")


def liquid_value(s,pid):
    return s["players"][pid]["money"] + sum(
        (0 if deed(s,i)["mortgaged"] else BOARD[i].price//2)
        + deed(s,i)["level"]*BOARD[i].build//2 for i in owned(s,pid))


def settle_auction(s):
    a=s["auction"]
    if not a:
        return
    active=[q for q in a["eligible"] if q not in a["passed"]]
    if not active or (a["leader"] and active==[a["leader"]]):
        s["auction"]=None
        if a["leader"]:
            winner=a["leader"]
            if a["targets"] is not None:
                add_building(s,winner,int(a["targets"][winner]),a["bid"])
            else:
                s["players"][winner]["money"]-=a["bid"]
                deed(s,a["property"])["owner"]=winner
                log(s,f"{s['players'][winner]['name']} won {BOARD[a['property']].name} for £{a['bid']}.")
        else:
            log(s,"The auction ended without a bid.")


def settle_building_request(s):
    r=s["building_request"]
    if r and len(r["responses"])==len(r["eligible"]):
        targets={q:j for q,j in r["responses"].items() if j is not None}
        s["building_request"]=None
        if len(targets)>s[r["kind"]]:
            auction_start(s,None,targets)
        else:
            for q,j in targets.items():
                add_building(s,q,j,BOARD[j].build)


def bankrupt(s,pid,voluntary=False):
    t=s["queue"][0] if s["queue"] else None
    debt=t and t["type"]=="pay" and t["pid"]==pid
    if not voluntary:
        require(debt,"Bankruptcy is available only for an unpaid debt.")
        require(liquid_value(s,pid)<t["amount"],"You can cover this debt by selling buildings and mortgaging. Raise the funds first.")
    p=s["players"][pid]
    creditor=t["to"] if debt else None
    if creditor and s["players"][creditor]["bankrupt"]:
        creditor=None
    additions=[]
    for i in owned(s,pid):
        d=deed(s,i)
        if d["level"]:
            p["money"]+=d["level"]*BOARD[i].build//2
            if d["level"]==5:
                s["hotels"]+=1
            else:
                s["houses"]+=d["level"]
        d["level"]=0
        d["owner"]=creditor
        if creditor and d["mortgaged"]:
            additions.append(dict(type="inherit",pid=creditor,property=i))
        if not creditor:
            d["mortgaged"]=False
            additions.append(dict(type="auction",property=i))
    if creditor:
        s["players"][creditor]["money"]+=p["money"]
        s["players"][creditor]["cards"]+=p["cards"]
    else:
        for deck in p["cards"]:
            s["decks"][deck].append(next(i for i,c in enumerate(DECKS[deck]) if c[1]=="jailfree"))
    p.update(bankrupt=True,money=0,cards=[])
    s["trades"]=[x for x in s["trades"] if pid not in (x["from"],x["to"])]
    remaining=s["queue"] if voluntary else s["queue"][1:]
    s["queue"]=additions+[x for x in remaining if x.get("pid")!=pid]
    if voluntary:
        log(s,f"{p['name']} declared bankruptcy and left the game.")
    log(s,f"{p['name']} is bankrupt. Assets went to {s['players'][creditor]['name'] if creditor else 'the bank'}.")
    if len(living(s))==1:
        s.update(status="finished",winner=living(s)[0],queue=[],auction=None,building_request=None)
        log(s,f"{s['players'][s['winner']]['name']} wins the game!")
    elif current(s)==pid:
        end_turn(s)
    if voluntary and s["status"]=="playing":
        a=s["auction"]
        if a:
            a["eligible"]=[q for q in a["eligible"] if q!=pid]
            a["passed"]=[q for q in a["passed"] if q!=pid]
            if a["targets"] is not None:
                a["targets"].pop(pid,None)
            if a["leader"]==pid:
                a.update(leader=None,bid=0,passed=[])
                log(s,"The leading bidder left. Bidding restarted at £0 for the remaining players.")
            settle_auction(s)
        r=s["building_request"]
        if r:
            r["eligible"]=[q for q in r["eligible"] if q!=pid]
            r["responses"].pop(pid,None)
            settle_building_request(s)


def trade_validate(s,t):
    a,b=t["from"],t["to"]
    require(a!=b and a in living(s) and b in living(s),"Choose another active player.")
    for side,pid in (("give",a),("take",b)):
        items=t[side]
        require(len(items)==len(set(items)),"Duplicate properties in this offer.")
        for i in items:
            require(deed(s,i)["owner"]==pid,"A property in this offer changed hands.")
            require(not any(deed(s,j)["level"] for j in group(s,i)),"Sell every building in that colour set before trading.")
        cards=t[side+"_cards"]
        require(len(cards)==len(set(cards)) and all(x in s["players"][pid]["cards"] for x in cards),"A jail card in this offer is unavailable.")
    number(t["give_cash"])
    number(t["take_cash"])
    require(t["give"] or t["take"] or t["give_cards"] or t["take_cards"] or t["give_cash"] or t["take_cash"],"Offer something to trade.")


def apply(state,pid,action,**args):
    s=copy.deepcopy(state)
    require(pid in s["players"],"Your session is not a member of this room.")
    p=s["players"][pid]
    require(not p["bankrupt"],"You are spectating after bankruptcy.")
    require(s["status"]!="finished","This game has finished.")
    if s["status"]=="lobby":
        if action=="resign":
            del s["players"][pid]
            s["order"].remove(pid)
            if s["host"]==pid:
                s["host"]=s["order"][0] if s["order"] else None
            log(s,f"{p['name']} left the lobby.")
        elif action=="ready":
            p["ready"]=not p["ready"]
        elif action=="start":
            require(pid==s["host"],"Only the host can start.")
            require(2<=len(s["players"])<=6 and all(q["ready"] for q in s["players"].values()),"Need 2–6 ready players.")
            candidates=s["order"][:]
            while len(candidates)>1:
                rolls={q:secrets.randbelow(6)+secrets.randbelow(6)+2 for q in candidates}
                log(s,"Starting rolls: "+", ".join(f"{s['players'][q]['name']} {v}" for q,v in rolls.items()))
                candidates=[q for q,v in rolls.items() if v==max(rolls.values())]
            s.update(status="playing",turn=s["order"].index(candidates[0]))
            log(s,f"{s['players'][current(s)]['name']} goes first.")
        else:
            raise RuleError("Ready up or wait for the host.")
        return s

    blocked=bool(s["queue"] or s["auction"] or s["building_request"])
    t=s["queue"][0] if s["queue"] else None
    debt=t and t["type"]=="pay"
    if action in {"roll","end","jail_pay","jail_card"}:
        require(current(s)==pid,"It is another player's turn.")
        require(not blocked,"Finish the pending payment, purchase, or auction first.")
    if action=="roll":
        require(s["stage"]=="roll","End your turn before rolling again.")
        # Dice inputs are never accepted from a client.
        dice=[secrets.randbelow(6)+1,secrets.randbelow(6)+1]
        s["dice"]=dice
        s["roll_id"]+=1
        double=dice[0]==dice[1]
        s["last_roll"]=dict(pid=pid,dice=dice[:],total=sum(dice),id=s["roll_id"],doubles=double)
        s["stage"]="end"
        log(s,f"{p['name']} rolled {dice[0]} + {dice[1]}.")
        if p["jail"]:
            p["jail_turns"]+=1
            if double or p["jail_turns"]==3:
                p["jail"]=False
                if not double:
                    s["queue"].append(pay_task(pid,50,reason="Third jail turn fine"))
                s["queue"].append(move_task(pid,(p["pos"]+sum(dice))%40))
        else:
            s["doubles"]=s["doubles"]+1 if double else 0
            if s["doubles"]==3:
                send_jail(s,pid)
            else:
                if double:
                    s["stage"]="roll"
                s["queue"].append(move_task(pid,(p["pos"]+sum(dice))%40))
    elif action=="end":
        require(s["stage"]=="end","Roll the dice first; doubles require another roll.")
        end_turn(s)
    elif action in {"jail_pay","jail_card"}:
        require(p["jail"] and s["stage"]=="roll","Choose this before trying to roll out of jail.")
        if action=="jail_pay":
            spend(s,pid,50)
        else:
            deck=args.get("deck")
            require(deck in p["cards"],"You do not have that card.")
            p["cards"].remove(deck)
            s["decks"][deck].append(next(i for i,c in enumerate(DECKS[deck]) if c[1]=="jailfree"))
        p.update(jail=False,jail_turns=0)
        log(s,f"{p['name']} left jail.")
    elif action in {"buy","decline"}:
        require(t and t["type"]=="purchase" and t["pid"]==pid,"There is no purchase for you.")
        i=t["property"]
        if action=="buy":
            spend(s,pid,BOARD[i].price)
            deed(s,i)["owner"]=pid
            log(s,f"{p['name']} bought {BOARD[i].name} for £{BOARD[i].price}.")
            s["queue"].pop(0)
        else:
            s["queue"].pop(0)
            auction_start(s,i)
    elif action in {"bid","pass"}:
        a=s["auction"]
        require(a and pid in a["eligible"] and pid not in a["passed"],"You are not an active bidder.")
        if action=="bid":
            amount=number(args.get("amount"),1)
            require(amount>a["bid"] and p["money"]>=amount,"Bid above the current price within your cash balance.")
            if a["targets"] is not None:
                can_build(s,pid,int(a["targets"][pid]),False)
            a.update(bid=amount,leader=pid)
            log(s,f"{p['name']} bid £{amount}.")
        else:
            require(a["leader"]!=pid,"The leading bidder cannot withdraw a committed bid.")
            a["passed"].append(pid)
        settle_auction(s)
    elif action in {"mortgage","unmortgage","sell","sell_set","build"}:
        i=number(args.get("property"),0,39)
        d=deed(s,i)
        require(d["owner"]==pid,"You do not own this property.")
        require(not s["building_request"] and not (s["auction"] and s["auction"]["targets"] is not None),"Finish building allocation first.")
        if action=="mortgage":
            require(not d["mortgaged"] and not any(deed(s,j)["level"] for j in group(s,i)),"Sell the colour set's buildings before mortgaging.")
            d["mortgaged"]=True
            p["money"]+=BOARD[i].price//2
            log(s,f"{p['name']} mortgaged {BOARD[i].name}.")
        elif action=="unmortgage":
            require(not debt,"Resolve the current debt before spending on redemption.")
            require(d["mortgaged"],"This property is not mortgaged.")
            spend(s,pid,BOARD[i].price//2*11//10)
            d["mortgaged"]=False
        elif action=="sell_set":
            require(BOARD[i].kind=="street","Choose a street with buildings.")
            # Whole-set liquidation permits selling hotels without needing replacement houses.
            for j in group(s,i):
                e=deed(s,j)
                require(e["owner"]==pid or not e["level"],"You must own the improved colour set.")
                p["money"]+=e["level"]*BOARD[j].build//2
                s["hotels" if e["level"]==5 else "houses"]+=1 if e["level"]==5 else e["level"]
                e["level"]=0
            log(s,f"{p['name']} sold all buildings in the {BOARD[i].group} set at half price.")
        elif action=="sell":
            require(d["level"]>0 and d["level"]==max(deed(s,j)["level"] for j in group(s,i)),"Sell buildings evenly.")
            if d["level"]==5:
                require(s["houses"]>=4,"The bank needs four houses to downgrade this hotel. Sell the whole set instead.")
                s["houses"]-=4
                s["hotels"]+=1
            else:
                s["houses"]+=1
            d["level"]-=1
            p["money"]+=BOARD[i].build//2
        else:
            require(not blocked,"Finish the current decision before requesting buildings.")
            kind=can_build(s,pid,i)
            require(s[kind]>0,"The bank has no buildings of this type available.")
            # Every player gets the chance to request scarce supply before any allocation.
            possible=[]
            for other in living(s):
                for j in owned(s,other):
                    try:
                        if can_build(s,other,j)==kind:
                            possible.append(other)
                            break
                    except RuleError:
                        continue
            if len(possible)>1 and s[kind]<len(possible):
                s["building_request"]=dict(kind=kind,responses={pid:i},eligible=possible)
                log(s,"Building shortage: eligible owners must request a location or decline; contested supply is auctioned.")
            else:
                add_building(s,pid,i,BOARD[i].build)
    elif action=="building_reply":
        r=s["building_request"]
        require(r and pid in r["eligible"] and pid not in r["responses"],"No building response is needed from you.")
        i=args.get("property")
        if i is not None:
            i=number(i,0,39)
            require(can_build(s,pid,i)==r["kind"],"Choose the requested building type.")
        r["responses"][pid]=i
        settle_building_request(s)
    elif action=="inherit":
        require(t and t["type"]=="inherit" and t["pid"]==pid,"No inherited mortgage decision is pending for you.")
        i=t["property"]
        value=BOARD[i].price//2
        mode=args.get("mode")
        require(mode in {"keep","redeem"},"Choose keep or redeem.")
        s["queue"].pop(0)
        cost=value//10
        if mode=="redeem":
            # Voluntary redemption requires cash; mandatory interest can become debt.
            spend(s,pid,value+cost)
            deed(s,i)["mortgaged"]=False
        else:
            s["queue"].insert(0,pay_task(pid,cost,reason="Interest on inherited "+BOARD[i].name))
    elif action=="bankrupt":
        require(debt and t["pid"]==pid,"You do not have an unpaid debt.")
        bankrupt(s,pid)
    elif action=="resign":
        bankrupt(s,pid,voluntary=True)
    elif action in {"offer","counteroffer"}:
        require(not s["auction"] and not s["building_request"],"Finish the auction or building allocation before trading.")
        original=None
        if action=="counteroffer":
            original=next((x for x in s["trades"] if x["id"]==args.get("id")),None)
            require(original is not None,"That offer is no longer open. Review the latest trades.")
            require(original["to"]==pid,"Only the recipient can counter this offer.")
            require(args.get("to")==original["from"],"Send the counteroffer to the original proposer.")
        require(original is not None or len(s["trades"])<12,"Resolve or cancel open offers first.")
        tr=dict(id=secrets.token_hex(8),**{"from":pid,"to":args.get("to")},
                give=args.get("give",[]),take=args.get("take",[]),give_cash=args.get("give_cash",0),
                take_cash=args.get("take_cash",0),give_cards=args.get("give_cards",[]),take_cards=args.get("take_cards",[]),
                from_redeem=args.get("redeem",[]))
        trade_validate(s,tr)
        require(set(tr["from_redeem"])<=set(tr["take"]),"Choose mortgages you are receiving.")
        if original:
            tr["counter_of"]=original["id"]
            s["trades"].remove(original)
        s["trades"].append(tr)
        verb="sent a counteroffer" if original else "proposed a trade"
        log(s,f"{p['name']} {verb} to {s['players'][tr['to']]['name']}.")
    elif action in {"accept","reject","cancel"}:
        require(not s["auction"] and not s["building_request"],"Finish the auction or building allocation before trading.")
        tr=next((x for x in s["trades"] if x["id"]==args.get("id")),None)
        require(tr is not None,"That offer is no longer open.")
        require(pid==(tr["from"] if action=="cancel" else tr["to"]),"You cannot respond to this offer.")
        if action=="accept":
            trade_validate(s,tr)
            a,b=tr["from"],tr["to"]
            redeemed={a:set(tr["from_redeem"]),b:set(args.get("redeem",[]))}
            require(redeemed[b]<=set(tr["give"]),"Choose mortgages you are receiving.")
            costs={a:0,b:0}
            for side,receiver in (("give",b),("take",a)):
                for i in tr[side]:
                    if deed(s,i)["mortgaged"]:
                        costs[receiver]+=BOARD[i].price//20
                        if i in redeemed[receiver]:
                            costs[receiver]+=BOARD[i].price//2
            require(s["players"][a]["money"]>=tr["give_cash"] and s["players"][b]["money"]>=tr["take_cash"],"An offered cash amount is no longer available.")
            delta=tr["take_cash"]-tr["give_cash"]
            require(s["players"][a]["money"]+delta>=costs[a] and s["players"][b]["money"]-delta>=costs[b],"Each player must cover mortgage transfer fees.")
            s["players"][a]["money"]+=delta-costs[a]
            s["players"][b]["money"]-=delta+costs[b]
            for side,giver,receiver in (("give",a,b),("take",b,a)):
                for i in tr[side]:
                    deed(s,i)["owner"]=receiver
                    if i in redeemed[receiver]:
                        deed(s,i)["mortgaged"]=False
                for card in tr[side+"_cards"]:
                    s["players"][giver]["cards"].remove(card)
                    s["players"][receiver]["cards"].append(card)
            log(s,f"{p['name']} accepted a trade with {s['players'][a]['name']}.")
        s["trades"].remove(tr)
    else:
        raise RuleError("Unknown action.")
    pump(s)
    validate(s)
    return s


def validate(s):
    """Invariants checked after every accepted action and in simulation tests."""
    assert s["houses"] + sum(d["level"] for d in s["deeds"].values() if d["level"]<5)==32
    assert s["hotels"] + sum(d["level"]==5 for d in s["deeds"].values())==12
    assert s["houses"]>=0 and s["hotels"]>=0
    for pid,p in s["players"].items():
        assert p["money"]>=0 and 0<=p["pos"]<40
        assert not p["bankrupt"] or not owned(s,pid)
    for i in DEEDS:
        d=deed(s,i)
        assert d["owner"] is None or d["owner"] in s["players"]
        assert 0<=d["level"]<=5
        if d["level"]:
            assert monopoly(s,d["owner"],i)
            assert not any(deed(s,j)["mortgaged"] for j in group(s,i))
    for deck, cards in DECKS.items():
        held=sum(deck in p["cards"] for p in s["players"].values())
        assert len(s["decks"][deck])+held==len(cards)
        assert len(s["decks"][deck])==len(set(s["decks"][deck]))

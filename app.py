"""Run with: streamlit run app.py. Configure Supabase using Streamlit secrets."""
import html
import os
import uuid
import time
import streamlit as st
from streamlit.errors import StreamlitAPIException
import engine
from data import BOARD, DEEDS, COLORS, TOKENS, PLAYER_COLORS
from store import Service, StorageError, Conflict, configured_backend
from ui import component

st.set_page_config(page_title="London Property Club",page_icon="🎩",layout="wide")
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
html,body,[class*="css"],.stApp{font-family:'DM Sans',sans-serif;color:#203d35}.stApp{background:#f5f3eb}h1,h2,h3{font-family:'Playfair Display',Georgia,serif!important;color:#203d35}.block-container{max-width:1550px;padding-top:2.1rem;padding-bottom:2rem}header[data-testid="stHeader"]{background:transparent}[data-testid="stToolbar"]{opacity:.4}.stButton>button{border-radius:9px;border:1px solid #c8d2c4;min-height:43px;font-weight:600}.stButton>button[kind="primary"]{background:#254f42;border-color:#254f42;color:#fff9eb}.stTextInput input,.stSelectbox>div{border-radius:9px}.eyeline{letter-spacing:3px;font-size:11px;color:#789180;text-transform:uppercase}.title{font-family:'Playfair Display',Georgia,serif;font-size:38px;margin:0;font-weight:700}.lede{color:#758371;margin:7px 0 25px}.player{background:#fffcf4;border:1px solid #dfe3d6;border-left:5px solid var(--c);border-radius:10px;margin:8px 0;padding:12px 14px;display:flex;gap:12px;align-items:center}.player.active{box-shadow:0 0 0 2px #bdcfae}.avatar{font-size:27px}.pname{font-weight:700}.balance{margin-left:auto;font-size:20px;font-weight:700}.meta{font-size:11px;color:#7b8577}.banner{padding:12px 17px;background:#e5eadb;border-radius:9px;color:#415d4a;font-size:13px;margin-bottom:15px}.history{background:#fffcf6;border:1px solid #e1e5d8;border-radius:9px;padding:12px 15px;max-height:240px;overflow:auto;font-size:12px;color:#5d6f5f;line-height:1.6}.history p{border-bottom:1px solid #eeeee4;padding:4px 0;margin:0}.deed{background:#fffdf4;border:1px solid #d4d7c9;border-radius:9px;padding:15px}.deed h3{font-size:20px;margin-top:4px}.stTabs [data-baseweb="tab-list"]{gap:18px}.stTabs [data-baseweb="tab"]{font-size:13px}.stAlert{border-radius:9px}div[data-testid="stExpander"]{background:#fffdf6;border-radius:9px}div[data-testid="stForm"]{background:#fffdf6;border-radius:12px}.stCaption{color:#70816e}
.stButton>button{transition:transform .12s,box-shadow .12s,background .12s}.stButton>button:active{transform:translateY(3px) scale(.98);box-shadow:inset 0 3px 8px #153d3340}.stButton>button:focus-visible{outline:3px solid #cba958;outline-offset:2px}.roll-callout{background:#fff6d7;border:2px solid #c49b43;border-radius:12px;padding:12px 16px;margin:12px 0 17px}.roll-callout small{display:block;font-size:12px;color:#776636}.roll-callout strong{font-size:30px;color:#234c3d}.roll-callout b{display:block;font-size:11px;color:#9a6d16}</style>''',unsafe_allow_html=True)
st.markdown('<div class="eyeline">GATHER YOUR FRIENDS. CLAIM YOUR CORNER.</div><div class="title">London Property Club <span style="font-size:23px">🎩</span></div><p class="lede">The classic London property game, together from anywhere.</p>',unsafe_allow_html=True)

try:
    settings=dict(st.secrets)
except FileNotFoundError:
    settings={}
backend=configured_backend(settings)
table=component()


def esc(x):
    return html.escape(str(x))


def credentials(value):
    st.session_state.credentials=value
    st.session_state.browse_tables=False
    st.session_state.pop("private_key",None)
    st.query_params["room"]=value["code"]


def rerun_fragment():
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def leave_view():
    st.session_state.pop("active_desk",None)
    st.session_state.credentials=None
    st.session_state.browse_tables=True
    st.session_state.notice=None
    st.query_params.clear()


def do(service,version,action,**kwargs):
    c=st.session_state.credentials
    try:
        service.act(c["code"],c["session"],version,uuid.uuid4().hex,action,**kwargs)
        st.session_state.notice=None
    except (engine.RuleError,Conflict,StorageError) as e:
        st.session_state.notice=str(e)
    # Widget callbacks run before the fragment renders. Its automatic rerun
    # reads the committed state once; an explicit rerun adds a second read.


def button(service,version,label,action,key=None,disabled=False,primary=False,**kwargs):
    st.button(label,key=key or action,disabled=disabled,type="primary" if primary else "secondary",
              use_container_width=True,on_click=do,args=(service,version,action),kwargs=kwargs)


def property_label(i):
    return BOARD[i].name


def component_data(s,version,pid):
    view={k:v for k,v in s.items() if k not in {"decks","admin_enabled"}} if s else None
    if view:
        view["trades"]=[t for t in s["trades"] if pid in (t["from"],t["to"])]
        view["events"]=[event for event in s["events"] if not event.startswith("⚡ ADMIN mode ")]
    return dict(state=view,version=version,pid=pid,board=[b.json() for b in BOARD],
                colors=COLORS,player_colors=PLAYER_COLORS,rules=engine.room_rules(s) if s else {},server_now=time.time())


def property_actions(s,pid,i):
    if i not in DEEDS or engine.deed(s,i)["owner"]!=pid:
        return []
    b,d=BOARD[i],engine.deed(s,i)
    operations=[("unmortgage" if d["mortgaged"] else "mortgage",
                 f"Redeem mortgage · £{b.price//2*11//10}" if d["mortgaged"] else f"Mortgage · receive £{b.price//2}")]
    if b.kind=="street":
        operations += [("build",f"{'Buy hotel' if d['level']==4 else 'Buy house'} · £{b.build}"),
                       ("sell",f"Sell one building · receive £{b.build//2}"),
                       ("sell_set","Sell this colour set's buildings")]
    result=[]
    for action,label in operations:
        reason=""
        try:
            engine.apply(s,pid,action,property=i)
        except engine.RuleError as e:
            reason=str(e)
        result.append(dict(action=action,label=label,enabled=not reason,reason=reason,primary=action=="build"))
    return result


def close_desk():
    st.session_state.pop("active_desk",None)
    st.session_state.desk_feedback=""


@st.dialog("Your table desk",width="large",on_dismiss=close_desk)
def desk(mode,property_id=None,trade_id=None):
    c=st.session_state.get("credentials")
    if not c or not backend:
        return
    service=Service(backend)
    try:
        s,version,pid=service.read(c["code"],c["session"])
    except (engine.RuleError,StorageError) as e:
        st.error(str(e))
        return
    trade=next((t for t in s["trades"] if t["id"]==trade_id and pid in (t["from"],t["to"])),None)
    msg=table(mode=mode,property=property_id,trade=trade,
              property_actions=property_actions(s,pid,property_id) if mode=="property" else [],
              feedback=st.session_state.get("desk_feedback",""),ack=st.session_state.get("desk_ack"),
              **component_data(s,version,pid),key="desk_"+mode+"_"+str(property_id or trade_id or ""))
    if isinstance(msg,dict) and msg.get("type")=="action" and msg.get("nonce")!=st.session_state.get("desk_nonce"):
        st.session_state.desk_nonce=msg.get("nonce")
        st.session_state.desk_ack=msg.get("nonce")
        permitted={"property":{"mortgage","unmortgage","build","sell","sell_set"},
                   "trade":{"offer"},"review":{"accept","reject","cancel","counteroffer"},"leave":{"resign"}}
        try:
            engine.require(msg.get("action") in permitted.get(mode,set()),"Choose an available action in this window.")
            service.act(c["code"],c["session"],msg.get("version"),uuid.uuid4().hex,msg["action"],**msg.get("args",{}))
            st.session_state.desk_feedback=""
            if msg["action"]=="resign":
                leave_view()
                st.rerun()
            if mode in {"trade","review"}:
                close_desk()
                st.session_state.notice=None
                st.rerun()
        except (engine.RuleError,Conflict,StorageError) as e:
            st.session_state.desk_feedback=str(e)
        rerun_fragment()


def open_desk(mode,property_id=None,trade_id=None):
    st.session_state.desk_feedback=""
    st.session_state.active_desk=(mode,property_id,trade_id)
    st.rerun()


def players(s):
    for index,pid in enumerate(s["order"]):
        p=s["players"][pid]
        status="Bankrupt · spectating" if p["bankrupt"] else "In jail" if p["jail"] else f"{len(engine.owned(s,pid))} properties · {len(p['cards'])} jail cards"
        active=s["status"]=="playing" and engine.current(s)==pid
        st.markdown(f'<div class="player {"active" if active else ""}" style="--c:{PLAYER_COLORS[index]}"><div class="avatar">{p["token"]}</div><div><div class="pname">{esc(p["name"])} {"•" if active else ""}</div><div class="meta">{esc(status)}</div></div><div class="balance">£{p["money"]:,}</div></div>',unsafe_allow_html=True)


RULE_LABELS={"starting_cash":"Starting cash (£)","go_salary":"GO salary (£)",
             "income_tax":"Income Tax (£)","super_tax":"Super Tax (£)","jail_fine":"Jail fine (£)",
             "double_go":"Double salary when landing exactly on GO","free_parking":"Bank payments fund a Free Parking jackpot",
             "decline_auction":"Auction declined bank purchases","even_build":"Build and sell evenly",
             "rent_in_jail":"Owners collect rent while in jail","clock_enabled":"Enable decision clock",
             "decision_seconds":"Ordinary decision time (seconds)","debt_seconds":"Debt decision time (seconds)",
             "auction_seconds":"Auction response time (seconds)","miss_limit":"Remove after consecutive missed decisions"}

def room_settings(service,s,version,pid):
    r=engine.room_rules(s);room=st.session_state.credentials["code"]
    with st.expander("⚙ Room rules & timers"):
        st.caption("The host chooses these before starting. Saving changes resets everyone's Ready status. Rules lock during play.")
        if pid==s["host"] and s["status"]=="lobby":
            with st.form("rules_"+room):
                ranges={"starting_cash":(500,5000,100),"go_salary":(0,1000,50),"income_tax":(0,1000,50),
                        "super_tax":(0,500,25),"jail_fine":(0,500,10),"decision_seconds":(30,300,15),
                        "debt_seconds":(60,600,30),"auction_seconds":(15,120,5),"miss_limit":(2,5,1)}
                chosen={}
                for key,label in RULE_LABELS.items():
                    if key in ranges:
                        low,high,step=ranges[key]
                        chosen[key]=int(st.number_input(label,min_value=low,max_value=high,value=r[key],step=step,key=room+"_rule_"+key))
                    else:chosen[key]=st.checkbox(label,value=r[key],key=room+"_rule_"+key)
                st.caption("A missed roll rolls automatically; a purchase is declined, an auction is passed, and a building request is declined. Debt receives another full grace period. Repeated misses forfeit the seat. The host can add time during play.")
                if st.form_submit_button("Save room rules",use_container_width=True):
                    do(service,version,"configure",rules=chosen);rerun_fragment()
        else:
            for key,label in RULE_LABELS.items():
                st.write(f"{label}: {'On' if r[key] is True else 'Off' if r[key] is False else r[key]}")
        if s.get("clock") and pid==s["host"]:
            button(service,version,"Give this decision +60 seconds","extend_clock",key="clock_extend",disabled=s["clock"].get("extensions",0)>=5)

ADMIN_POWERS={"add_cash":"Create cash","set_cash":"Set a player's cash","take_property":"Give / steal a property",
              "take_set":"Give / steal a complete colour set","free_hotels":"Give a colour set with free hotels",
              "teleport":"Move a piece anywhere","jail":"Send a player to jail","release":"Free a player from jail",
              "force_dice":"Rig the host's next dice roll","skip_turn":"Skip the current player's turn",
              "bankrupt":"Instantly bankrupt an opponent","win":"Declare an instant winner"}

def admin_controls(service,s,version,pid):
    if pid!=s["host"] or s["players"][pid]["bankrupt"] or s["status"]=="finished":return
    with st.expander("⚡ Admin commands"):
        st.caption("Only the host can unlock and use these powers. Every use appears in table history.")
        if not s.get("admin_enabled"):
            with st.form("admin_unlock",clear_on_submit=True):
                code=st.text_input("Admin unlock code",type="password",key="admin_unlock_code")
                if st.form_submit_button("Unlock admin mode",use_container_width=True):
                    do(service,version,"admin_mode",enabled=True,unlock_code=code);rerun_fragment()
            return
        button(service,version,"Disable admin mode","admin_mode",key="disable_admin",enabled=False)
        if s["status"]!="playing":
            st.info("Admin mode is unlocked. Start the game to use powers.")
            return
        power=st.selectbox("Admin power",list(ADMIN_POWERS),format_func=ADMIN_POWERS.get,key="admin_power")
        with st.form("admin_command"):
            target=pid if power=="force_dice" else st.selectbox("Target player",engine.living(s),format_func=lambda q:s["players"][q]["name"],key="admin_target")
            values=dict(power=power,target=target)
            if power in {"add_cash","set_cash"}:
                values["amount"]=int(st.number_input("Cash amount (£)",min_value=0,max_value=1000000,value=10000,step=100,key="admin_cash"))
            if power in {"take_property","take_set","free_hotels"}:
                choices=[i for i in DEEDS if power=="take_property" or BOARD[i].kind=="street"]
                values["property"]=st.selectbox("Property / colour set",choices,format_func=property_label,key="admin_property_"+power)
                st.caption("Reclaims affected buildings, clears mortgages and open trade offers. Free hotels still use the bank's hotel supply.")
            if power=="teleport":values["destination"]=st.selectbox("Destination",list(range(40)),format_func=property_label,key="admin_destination")
            if power=="force_dice":
                one=st.selectbox("First die",list(range(1,7)),key="admin_die1")
                two=st.selectbox("Second die",list(range(1,7)),key="admin_die2")
                values["dice"]=[one,two]
            st.caption("Most powers require the pending decision, auction and building allocation to be finished. Cash powers can resolve debt.")
            if st.form_submit_button("⚡ Execute admin power",use_container_width=True):
                do(service,version,"admin",**values);rerun_fragment()

def controls(service,s,version,pid):
    me=s["players"][pid]
    if s["status"]=="finished":
        st.success(f"🏆 {s['players'][s['winner']]['name']} wins the table!")
        return
    if me["bankrupt"]:
        st.info("You are spectating. Your friends' turns still update here.")
        return
    if s["status"]=="lobby":
        st.subheader("Make yourself at home")
        for q in s["players"].values():
            st.write(f"{q['token']} {q['name']} · {'✓ ready' if q['ready'] else 'choosing a seat'}")
        button(service,version,"✓ Ready" if not me["ready"] else "Not ready", "ready",primary=True)
        if pid==s["host"]:
            button(service,version,"Start the game", "start",disabled=len(s["players"])<2 or not all(q["ready"] for q in s["players"].values()))
        else:
            st.caption("The host starts when everyone is ready.")
        return
    a=s["auction"]
    r=s["building_request"]
    if a:
        st.subheader("Going once, going twice…")
        st.write("Building auction" if a["targets"] is not None else BOARD[a["property"]].name)
        st.metric("Current bid",f"£{a['bid']:,}",s["players"][a["leader"]]["name"] if a["leader"] else "No bids yet")
        if pid in a["eligible"] and pid not in a["passed"]:
            amount=st.number_input("Your bid (£)",min_value=a["bid"]+1,value=a["bid"]+1,step=1,key=f"bid_{a['property']}_{a['bid']}")
            button(service,version,"Place bid", "bid",amount=int(amount),primary=True)
            button(service,version,"Pass on this auction", "pass",disabled=pid==a["leader"])
        else:
            st.caption("Waiting for the remaining bidders.")
        waiting=[s["players"][q]["name"] for q in a["eligible"] if q not in a["passed"] and q!=a["leader"]]
        st.caption("Still bidding: "+", ".join(waiting))
        return
    if r:
        st.subheader("Limited building supply")
        if pid in r["eligible"] and pid not in r["responses"]:
            choices=[]
            for i in engine.owned(s,pid):
                try:
                    if engine.can_build(s,pid,i)==r["kind"]:
                        choices.append(i)
                except engine.RuleError:
                    pass
            selected=st.selectbox("Request a building for",choices,format_func=property_label) if choices else None
            button(service,version,"Request building", "building_reply",key="building_yes",property=selected,disabled=selected is None)
            button(service,version,"No building for me", "building_reply",key="building_no",property=None)
        else:
            st.caption("Waiting for eligible owners to respond.")
        return
    t=s["queue"][0] if s["queue"] else None
    if t:
        who=s["players"][t["pid"]]["name"] if t.get("pid") else "Bank"
        if t["type"]=="purchase":
            i=t["property"]
            st.subheader(BOARD[i].name)
            st.write(f"Available from the bank · £{BOARD[i].price}")
            if t["pid"]==pid:
                button(service,version,f"Buy for £{BOARD[i].price}","buy",primary=True,disabled=me["money"]<BOARD[i].price)
                button(service,version,"Send to auction","decline")
            else:
                st.caption(f"Waiting for {who} to buy or auction.")
        elif t["type"]=="pay":
            st.warning(f"{who} owes £{t['amount']:,} · {t['reason']}")
            if t["pid"]==pid:
                st.write("Raise cash using your portfolio or a trade. Payment settles automatically once you can afford it.")
                button(service,version,"Declare bankruptcy","bankrupt",disabled=engine.liquid_value(s,pid)>=t["amount"])
        elif t["type"]=="inherit":
            i=t["property"]
            st.warning(f"{who} received mortgaged {BOARD[i].name}.")
            if t["pid"]==pid:
                button(service,version,f"Keep mortgage · £{BOARD[i].price//20} interest","inherit",key="keep_inherit",mode="keep")
                button(service,version,f"Redeem now · £{BOARD[i].price//2*11//10}","inherit",key="redeem_inherit",mode="redeem")
        return
    mine=engine.current(s)==pid
    st.subheader("Your move" if mine else s["players"][engine.current(s)]["name"]+"'s turn")
    if mine:
        if me["jail"] and s["stage"]=="roll":
            st.caption(f"Jail attempt {me['jail_turns']+1} of 3. Doubles release you without an extra roll.")
            button(service,version,f"Pay £{engine.room_rules(s)['jail_fine']} to leave jail","jail_pay",disabled=me["money"]<engine.room_rules(s)["jail_fine"])
            for deck in me["cards"]:
                button(service,version,"Use "+deck+" jail card","jail_card",key="card_"+deck,deck=deck)
        if s["stage"]=="roll":
            button(service,version,"🎲 Try for doubles" if me["jail"] else "🎲 Roll the dice","roll",primary=True)
        else:
            button(service,version,"End turn →","end",primary=True)
    else:
        st.caption("The table updates automatically. You can manage your properties and propose trades between turns.")


def portfolio(service,s,version,pid):
    mine=engine.owned(s,pid)
    if not mine:
        st.caption("Land on a property to buy it, or join an auction.")
        return
    for i in mine:
        d=engine.deed(s,i)
        if st.button(("🏦 " if d["mortgaged"] else "🏨 " if d["level"]==5 else "🏠 " if d["level"] else "📜 ")+BOARD[i].name,key="deed_"+str(i),use_container_width=True):
            open_desk("property",property_id=i)


def trade_ui(service,s,version,pid):
    others=[q for q in engine.living(s) if q!=pid]
    if not others or s["players"][pid]["bankrupt"]:
        return
    if st.button("⇄ Open trade room",key="open_trade",use_container_width=True):
        open_desk("trade")
    for t in s["trades"]:
        if pid not in (t["from"],t["to"]):
            continue
        with st.container(border=True):
            st.write(f"{s['players'][t['from']]['name']} → {s['players'][t['to']]['name']}")
            st.caption("Gives: "+", ".join([BOARD[i].name for i in t["give"]]+[f"£{t['give_cash']}"]+t["give_cards"]))
            st.caption("Receives: "+", ".join([BOARD[i].name for i in t["take"]]+[f"£{t['take_cash']}"]+t["take_cards"]))
            if st.button("Review offer" if pid==t["to"] else "View your offer",key="review_"+t["id"],use_container_width=True):
                open_desk("review",trade_id=t["id"])


@st.fragment(run_every=None if st.session_state.get("active_desk") else 0.75)
def game():
    invite=st.query_params.get("room","").upper()
    c=st.session_state.get("credentials")
    service=Service(backend) if backend else None
    s=version=pid=None
    if c and service:
        try:
            s,version,pid=service.read(c["code"],c["session"])
        except (engine.RuleError,StorageError) as e:
            st.error(str(e))
    left,right=st.columns([1.85,1],gap="large")
    with left:
        msg=table(**component_data(s,version,pid),
                  credentials=c,invite=invite,room=c["code"] if c else "",clear=st.session_state.get("browse_tables",False),key="table")
        if isinstance(msg,dict) and msg.get("nonce")!=st.session_state.get("component_nonce"):
            st.session_state.component_nonce=msg.get("nonce")
            if msg.get("type")=="restore" and not c and not st.session_state.get("browse_tables") and msg.get("credentials"):
                saved=msg["credentials"]
                if isinstance(saved,dict) and {"code","session"}<=saved.keys() and service:
                    try:
                        service.read(saved["code"],saved["session"])
                        credentials(saved)
                        st.rerun()
                    except (engine.RuleError,StorageError):
                        pass
            elif s and msg.get("type")=="desk":
                mode=msg.get("mode")
                if mode=="property" and type(msg.get("property")) is int and 0<=msg["property"]<40:
                    open_desk("property",property_id=msg["property"])
                elif mode=="trade" and not s["players"][pid]["bankrupt"] and s["status"]=="playing":
                    open_desk("trade")
        if s:
            if s["last_card"]:
                st.info(s["last_card"]["deck"].title()+" · "+s["last_card"]["text"])
        else:
            st.markdown('''<div style="padding:45px 30px 60px;border:1px solid #cbd8c7;border-radius:15px;background:linear-gradient(140deg,#dce7d3,#eef0df);text-align:center"><div class="eyeline">2–6 PLAYERS · CLASSIC LONDON</div><div style="font:700 66px Georgia;color:#234c3d;margin:20px 0">Own your<br>little piece<br>of London.</div><div style="color:#6d7f65;font-size:17px;margin:25px 0">Buy the streets. Build your empire.<br>Make a deal your friends will remember.</div><div style="font-size:37px;letter-spacing:15px">🚗 🎩 🐕 🚢</div></div>''',unsafe_allow_html=True)
    with right:
        if not backend:
            st.subheader("The table is nearly ready")
            st.info("The host needs to connect the shared database before online games can start.")
            st.caption("Deployment: run schema.sql in Supabase, then set SUPABASE_URL and SUPABASE_SECRET_KEY in Streamlit's Secrets settings. For local testing set MONOPOLY_LOCAL=1.")
            return
        if backend.label.startswith("Local"):
            st.warning("Local test mode · games are saved on this server. Supabase must be configured for durable cloud hosting.")
        if st.session_state.get("notice"):
            st.warning(st.session_state.notice)
        if not s:
            st.subheader("Pull up a chair")
            tab1,tab2,tab3=st.tabs(["Create","Join","Reconnect"])
            with tab1:
                with st.form("create"):
                    name=st.text_input("Your name",max_chars=24)
                    token=st.selectbox("Your token",TOKENS)
                    if st.form_submit_button("Create a table",use_container_width=True,type="primary"):
                        try:
                            credentials(service.create(name,token))
                            st.rerun()
                        except (engine.RuleError,StorageError) as e:
                            st.error(str(e))
            with tab2:
                with st.form("join"):
                    code=st.text_input("Room code",value=invite,max_chars=6)
                    name=st.text_input("Your name",max_chars=24,key="join_name")
                    token=st.selectbox("Your token",TOKENS,key="join_token")
                    if st.form_submit_button("Join friends",use_container_width=True,type="primary"):
                        try:
                            credentials(service.join(code,name,token))
                            st.rerun()
                        except (engine.RuleError,Conflict,StorageError) as e:
                            st.error(str(e))
            with tab3:
                with st.form("reconnect"):
                    code=st.text_input("Room code",value=invite,key="restore_code")
                    key=st.text_input("Private recovery key",type="password")
                    if st.form_submit_button("Recover your seat",use_container_width=True):
                        try:
                            _,_,pid=service.read(code,key)
                            credentials(dict(code=code.upper().strip(),session=key,pid=pid))
                            st.rerun()
                        except (engine.RuleError,StorageError) as e:
                            st.error(str(e))
            st.caption("Each browser remembers your seat. Share the room code or invitation link with friends.")
            return
        st.markdown(f'<div class="banner">ROOM <strong>{esc(c["code"])}</strong> &nbsp;·&nbsp; {len(s["players"])}/6 seats &nbsp;·&nbsp; Live table</div>',unsafe_allow_html=True)
        if s.get("roll_id"):
            rolled=s.get("last_roll",{})
            values=rolled.get("dice",s["dice"])
            who=s["players"].get(rolled.get("pid"),{}).get("name","Last roll")
            double="<b>DOUBLES</b>" if values[0]==values[1] else ""
            st.markdown(f'<div class="roll-callout" role="status"><small>{esc(who)} · dice result</small><strong>{values[0]} + {values[1]} = {sum(values)}</strong>{double}</div>',unsafe_allow_html=True)
        if s.get("clock"):
            clock=s["clock"];left=max(0,int(clock["deadline"]-time.time()))
            st.caption(f"⏱ {s['players'][clock['pid']]['name']} · {clock['kind']} decision · about {left}s remaining · {s['players'][clock['pid']].get('missed_decisions',0)}/{engine.room_rules(s)['miss_limit']} misses")
        controls(service,s,version,pid)
        if s["status"]!="finished" and not s["players"][pid]["bankrupt"]:
            if st.button("declare bankrupcy",key="leave_game",use_container_width=True):
                open_desk("leave")
        st.divider()
        players(s)
        if s["status"]=="playing":
            for incoming in s["trades"]:
                if incoming["to"]==pid:
                    st.info(("🤝 Counteroffer from " if incoming.get("counter_of") else "🤝 Trade offer from ")+s["players"][incoming["from"]]["name"])
                    if st.button("Review incoming trade",key="incoming_"+incoming["id"],use_container_width=True):
                        open_desk("review",trade_id=incoming["id"])
            t1,t2=st.tabs(["Your portfolio","Deals"])
            with t1:
                portfolio(service,s,version,pid)
            with t2:
                trade_ui(service,s,version,pid)
        room_settings(service,s,version,pid)
        admin_controls(service,s,version,pid)
        with st.expander("Invite & reconnect"):
            base=os.environ.get("PUBLIC_APP_URL") or settings.get("PUBLIC_APP_URL","")
            st.code((base.rstrip('/') if base else "")+"/?room="+c["code"],language=None)
            st.caption("Share this invitation or the room code. Your recovery key below is private; it controls your seat.")
            st.text_input("Private recovery key",value=c["session"],type="password",key="private_key")
            st.caption("Your seat stays saved when you switch tables. Open this invitation again to return.")
            if st.button("Create or join another table",use_container_width=True):
                leave_view()
                st.rerun()
        with st.expander("How to play"):
            st.write(f"Start with £{engine.room_rules(s)['starting_cash']}. Buy or auction every unowned property you land on. Rent, taxes and card payments settle automatically. Complete a colour group to build evenly. There are 32 houses and 12 hotels. Mortgage property or sell buildings to raise funds. Negotiate trades through Deals. The last solvent player wins.")
            st.caption("See Room rules & timers for this table’s GO, tax, jail, Free Parking, building and clock settings. No player loans or rent immunity deals.")
            st.markdown("[Classic rules reference](https://instructions.hasbro.com/en-gb/instruction/monopoly-game)")
        st.caption(f"{backend.label} · State {version} · Live sync every 0.75 seconds")


game()
if st.session_state.get("active_desk"):
    desk(*st.session_state.active_desk)
st.caption("An independent fan-made property game. MONOPOLY is a trademark of Hasbro. No affiliation or endorsement. Original visual design; no supplied board artwork is redistributed.")



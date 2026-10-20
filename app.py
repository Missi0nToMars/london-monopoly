"""Run with: streamlit run app.py. Configure Supabase using Streamlit secrets."""
import html
import os
import uuid
import streamlit as st
import engine
from data import BOARD, DEEDS, COLORS, TOKENS, PLAYER_COLORS
from store import Service, StorageError, Conflict, configured_backend
from ui import component

st.set_page_config(page_title="London Property Club",page_icon="🎩",layout="wide")
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
html,body,[class*="css"],.stApp{font-family:'DM Sans',sans-serif;color:#203d35}.stApp{background:#f5f3eb}h1,h2,h3{font-family:'Playfair Display',Georgia,serif!important;color:#203d35}.block-container{max-width:1550px;padding-top:2.1rem;padding-bottom:2rem}header[data-testid="stHeader"]{background:transparent}[data-testid="stToolbar"]{opacity:.4}.stButton>button{border-radius:9px;border:1px solid #c8d2c4;min-height:43px;font-weight:600}.stButton>button[kind="primary"]{background:#254f42;border-color:#254f42;color:#fff9eb}.stTextInput input,.stSelectbox>div{border-radius:9px}.eyeline{letter-spacing:3px;font-size:11px;color:#789180;text-transform:uppercase}.title{font-family:'Playfair Display',Georgia,serif;font-size:38px;margin:0;font-weight:700}.lede{color:#758371;margin:7px 0 25px}.player{background:#fffcf4;border:1px solid #dfe3d6;border-left:5px solid var(--c);border-radius:10px;margin:8px 0;padding:12px 14px;display:flex;gap:12px;align-items:center}.player.active{box-shadow:0 0 0 2px #bdcfae}.avatar{font-size:27px}.pname{font-weight:700}.balance{margin-left:auto;font-size:20px;font-weight:700}.meta{font-size:11px;color:#7b8577}.banner{padding:12px 17px;background:#e5eadb;border-radius:9px;color:#415d4a;font-size:13px;margin-bottom:15px}.history{background:#fffcf6;border:1px solid #e1e5d8;border-radius:9px;padding:12px 15px;max-height:240px;overflow:auto;font-size:12px;color:#5d6f5f;line-height:1.6}.history p{border-bottom:1px solid #eeeee4;padding:4px 0;margin:0}.deed{background:#fffdf4;border:1px solid #d4d7c9;border-radius:9px;padding:15px}.deed h3{font-size:20px;margin-top:4px}.stTabs [data-baseweb="tab-list"]{gap:18px}.stTabs [data-baseweb="tab"]{font-size:13px}.stAlert{border-radius:9px}div[data-testid="stExpander"]{background:#fffdf6;border-radius:9px}div[data-testid="stForm"]{background:#fffdf6;border-radius:12px}.stCaption{color:#70816e}
</style>''',unsafe_allow_html=True)
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
    st.query_params["room"]=value["code"]


def do(service,version,action,**kwargs):
    c=st.session_state.credentials
    try:
        service.act(c["code"],c["session"],version,uuid.uuid4().hex,action,**kwargs)
        st.session_state.notice=None
    except (engine.RuleError,Conflict,StorageError) as e:
        st.session_state.notice=str(e)
    st.rerun()


def button(service,version,label,action,key=None,disabled=False,primary=False,**kwargs):
    if st.button(label,key=key or action,disabled=disabled,type="primary" if primary else "secondary",use_container_width=True):
        do(service,version,action,**kwargs)


def property_label(i):
    return BOARD[i].name


def players(s):
    for index,pid in enumerate(s["order"]):
        p=s["players"][pid]
        status="Bankrupt · spectating" if p["bankrupt"] else "In jail" if p["jail"] else f"{len(engine.owned(s,pid))} properties · {len(p['cards'])} jail cards"
        active=s["status"]=="playing" and engine.current(s)==pid
        st.markdown(f'<div class="player {"active" if active else ""}" style="--c:{PLAYER_COLORS[index]}"><div class="avatar">{p["token"]}</div><div><div class="pname">{esc(p["name"])} {"•" if active else ""}</div><div class="meta">{esc(status)}</div></div><div class="balance">£{p["money"]:,}</div></div>',unsafe_allow_html=True)


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
            button(service,version,"Pay £50 to leave jail","jail_pay",disabled=me["money"]<50)
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
    i=st.selectbox("Your properties",mine,format_func=property_label,key="portfolio_property")
    d=engine.deed(s,i)
    st.caption(f"{'Mortgaged' if d['mortgaged'] else 'Mortgage value £'+str(BOARD[i].price//2)} · {'Hotel' if d['level']==5 else str(d['level'])+' houses'}")
    c1,c2=st.columns(2)
    with c1:
        button(service,version,"Unmortgage" if d["mortgaged"] else "Mortgage","unmortgage" if d["mortgaged"] else "mortgage",property=i)
    with c2:
        button(service,version,"Build house / hotel","build",property=i,disabled=BOARD[i].kind!="street")
    c1,c2=st.columns(2)
    with c1:
        button(service,version,"Sell one building","sell",property=i,disabled=d["level"]==0)
    with c2:
        button(service,version,"Sell set's buildings","sell_set",property=i,disabled=BOARD[i].kind!="street")
    st.caption("Build and sell evenly. Buildings sell for half cost; mortgages pay half the printed property price.")


def trade_ui(service,s,version,pid):
    others=[q for q in engine.living(s) if q!=pid]
    if not others or s["players"][pid]["bankrupt"]:
        return
    with st.expander("Propose a trade"):
        other=st.selectbox("Trade with",others,format_func=lambda q:s["players"][q]["name"])
        give=st.multiselect("Properties you give",engine.owned(s,pid),format_func=property_label)
        take=st.multiselect("Properties you receive",engine.owned(s,other),format_func=property_label)
        c1,c2=st.columns(2)
        with c1:
            give_cash=st.number_input("Cash you give (£)",min_value=0,step=1)
        with c2:
            take_cash=st.number_input("Cash you receive (£)",min_value=0,step=1)
        give_cards=st.multiselect("Jail cards you give",s["players"][pid]["cards"])
        take_cards=st.multiselect("Jail cards you receive",s["players"][other]["cards"])
        mortgages=[i for i in take if engine.deed(s,i)["mortgaged"]]
        redeem=st.multiselect("Redeem these incoming mortgages now",mortgages,format_func=property_label)
        st.caption("Incoming mortgages cost 10% interest. Redeem now for principal + 10%, or keep the mortgage and pay another 10% when redeeming later.")
        button(service,version,"Send offer","offer",to=other,give=give,take=take,give_cash=int(give_cash),take_cash=int(take_cash),give_cards=give_cards,take_cards=take_cards,redeem=redeem,primary=True)
    for t in s["trades"]:
        if pid not in (t["from"],t["to"]):
            continue
        with st.container(border=True):
            st.write(f"{s['players'][t['from']]['name']} → {s['players'][t['to']]['name']}")
            st.caption("Gives: "+", ".join([BOARD[i].name for i in t["give"]]+[f"£{t['give_cash']}"]+t["give_cards"]))
            st.caption("Receives: "+", ".join([BOARD[i].name for i in t["take"]]+[f"£{t['take_cash']}"]+t["take_cards"]))
            if pid==t["to"]:
                incoming=[i for i in t["give"] if engine.deed(s,i)["mortgaged"]]
                redeemed=st.multiselect("Redeem incoming mortgages",incoming,format_func=property_label,key="redeem_"+t["id"])
                button(service,version,"Accept trade","accept",key="accept_"+t["id"],id=t["id"],redeem=redeemed)
                button(service,version,"Decline trade","reject",key="reject_"+t["id"],id=t["id"])
            else:
                button(service,version,"Cancel offer","cancel",key="cancel_"+t["id"],id=t["id"])


@st.fragment(run_every=1.5)
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
        view={k:v for k,v in s.items() if k!="decks"} if s else engine.new_game()
        if not s:
            view={k:v for k,v in view.items() if k!="decks"}
        msg=table(state=view if s else None,board=[b.json() for b in BOARD],colors=COLORS,player_colors=PLAYER_COLORS,
                  credentials=c,invite=invite,room=c["code"] if c else "",key="table")
        if isinstance(msg,dict) and msg.get("nonce")!=st.session_state.get("component_nonce"):
            st.session_state.component_nonce=msg.get("nonce")
            if msg.get("type")=="restore" and not c and msg.get("credentials"):
                saved=msg["credentials"]
                if isinstance(saved,dict) and {"code","session"}<=saved.keys() and service:
                    try:
                        service.read(saved["code"],saved["session"])
                        credentials(saved)
                        st.rerun()
                    except (engine.RuleError,StorageError):
                        pass
            elif msg.get("type")=="select" and type(msg.get("id")) is int:
                st.session_state.selected=msg["id"]
        if s:
            selected=st.selectbox("Inspect the board",range(40),format_func=property_label,index=st.session_state.get("selected",0),key=f"inspect_{st.session_state.get('selected',0)}")
            b=BOARD[selected]
            if selected in DEEDS:
                d=engine.deed(s,selected)
                with st.expander(b.name+" · title deed",expanded=True):
                    st.write(f"Price £{b.price} · Mortgage £{b.price//2} · Owner: "+(s["players"][d["owner"]]["name"] if d["owner"] else "Bank"))
                    if b.kind=="street":
                        st.write("Base rent / 1 house / 2 / 3 / 4 / hotel")
                        st.write(" · ".join("£"+str(v) for v in b.rents))
                        st.caption(f"Each house or hotel costs £{b.build}. Complete colour sets double unimproved rent.")
                    elif b.kind=="station":
                        st.write("1 / 2 / 3 / 4 stations: £25 / £50 / £100 / £200")
                    else:
                        st.write("1 utility: 4 × dice. Both utilities: 10 × dice.")
            if s["last_card"]:
                st.info(s["last_card"]["deck"].title()+" · "+s["last_card"]["text"])
            st.caption("TABLE HISTORY")
            st.markdown('<div class="history">'+''.join('<p>'+esc(e)+'</p>' for e in reversed(s["events"][-35:]))+'</div>',unsafe_allow_html=True)
        else:
            st.markdown('''<div style="padding:45px 30px 60px;border:1px solid #cbd8c7;border-radius:15px;background:linear-gradient(140deg,#dce7d3,#eef0df);text-align:center"><div class="eyeline">2–6 PLAYERS · CLASSIC LONDON</div><div style="font:700 66px Georgia;color:#234c3d;margin:20px 0">Own your<br>little piece<br>of London.</div><div style="color:#6d7f65;font-size:17px;margin:25px 0">Buy the streets. Build your empire.<br>Make a deal your friends will remember.</div><div style="font-size:37px;letter-spacing:15px">🚗 🎩 🐕 🚢</div></div>''',unsafe_allow_html=True)
    with right:
        if not backend:
            st.subheader("The table is nearly ready")
            st.info("The host needs to connect the shared database before online games can start.")
            st.caption("Deployment: run schema.sql in Supabase, then set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Streamlit's Secrets settings. For local testing set MONOPOLY_LOCAL=1.")
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
        controls(service,s,version,pid)
        st.divider()
        players(s)
        if s["status"]=="playing":
            t1,t2=st.tabs(["Your portfolio","Deals"])
            with t1:
                portfolio(service,s,version,pid)
            with t2:
                trade_ui(service,s,version,pid)
        with st.expander("Invite & reconnect"):
            base=os.environ.get("PUBLIC_APP_URL") or settings.get("PUBLIC_APP_URL","")
            st.code((base.rstrip('/') if base else "")+"/?room="+c["code"],language=None)
            st.caption("Share this invitation or the room code. Your recovery key below is private; it controls your seat.")
            st.text_input("Private recovery key",value=c["session"],type="password",key="private_key")
        with st.expander("How to play"):
            st.write("Start with £1,500. Buy or auction every unowned property you land on. Rent, taxes and card payments settle automatically. Complete a colour group to build evenly. There are 32 houses and 12 hotels. Mortgage property or sell buildings to raise funds. Negotiate trades through Deals. The last solvent player wins.")
            st.caption("Free Parking pays nothing. GO pays £200. Income Tax £200; Super Tax £100. No player loans or rent immunity deals.")
            st.markdown("[Classic rules reference](https://instructions.hasbro.com/en-gb/instruction/monopoly-game)")
        st.caption(f"{backend.label} · State {version} · Polling every 1.5 seconds")


game()
st.caption("An independent fan-made property game. MONOPOLY is a trademark of Hasbro. No affiliation or endorsement. Original visual design; no supplied board artwork is redistributed.")


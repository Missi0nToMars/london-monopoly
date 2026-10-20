"""Classic London board. Card instructions are independently paraphrased."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Space:
    id: int
    name: str
    kind: str = "street"
    price: int = 0
    group: str = ""
    rents: tuple = ()
    build: int = 0

    def json(self):
        return asdict(self)


BOARD = [
    Space(0,"GO","go"),
    Space(1,"Old Kent Road",price=60,group="brown",rents=(2,10,30,90,160,250),build=50),
    Space(2,"Community Chest","chest"),
    Space(3,"Whitechapel Road",price=60,group="brown",rents=(4,20,60,180,320,450),build=50),
    Space(4,"Income Tax","tax",200),
    Space(5,"King's Cross Station","station",200),
    Space(6,"The Angel, Islington",price=100,group="lightblue",rents=(6,30,90,270,400,550),build=50),
    Space(7,"Chance","chance"),
    Space(8,"Euston Road",price=100,group="lightblue",rents=(6,30,90,270,400,550),build=50),
    Space(9,"Pentonville Road",price=120,group="lightblue",rents=(8,40,100,300,450,600),build=50),
    Space(10,"Jail / Just Visiting","jail"),
    Space(11,"Pall Mall",price=140,group="pink",rents=(10,50,150,450,625,750),build=100),
    Space(12,"Electric Company","utility",150),
    Space(13,"Whitehall",price=140,group="pink",rents=(10,50,150,450,625,750),build=100),
    Space(14,"Northumberland Avenue",price=160,group="pink",rents=(12,60,180,500,700,900),build=100),
    Space(15,"Marylebone Station","station",200),
    Space(16,"Bow Street",price=180,group="orange",rents=(14,70,200,550,750,950),build=100),
    Space(17,"Community Chest","chest"),
    Space(18,"Marlborough Street",price=180,group="orange",rents=(14,70,200,550,750,950),build=100),
    Space(19,"Vine Street",price=200,group="orange",rents=(16,80,220,600,800,1000),build=100),
    Space(20,"Free Parking","parking"),
    Space(21,"Strand",price=220,group="red",rents=(18,90,250,700,875,1050),build=150),
    Space(22,"Chance","chance"),
    Space(23,"Fleet Street",price=220,group="red",rents=(18,90,250,700,875,1050),build=150),
    Space(24,"Trafalgar Square",price=240,group="red",rents=(20,100,300,750,925,1100),build=150),
    Space(25,"Fenchurch St. Station","station",200),
    Space(26,"Leicester Square",price=260,group="yellow",rents=(22,110,330,800,975,1150),build=150),
    Space(27,"Coventry Street",price=260,group="yellow",rents=(22,110,330,800,975,1150),build=150),
    Space(28,"Water Works","utility",150),
    Space(29,"Piccadilly",price=280,group="yellow",rents=(24,120,360,850,1025,1200),build=150),
    Space(30,"Go to Jail","gotojail"),
    Space(31,"Regent Street",price=300,group="green",rents=(26,130,390,900,1100,1275),build=200),
    Space(32,"Oxford Street",price=300,group="green",rents=(26,130,390,900,1100,1275),build=200),
    Space(33,"Community Chest","chest"),
    Space(34,"Bond Street",price=320,group="green",rents=(28,150,450,1000,1200,1400),build=200),
    Space(35,"Liverpool St. Station","station",200),
    Space(36,"Chance","chance"),
    Space(37,"Park Lane",price=350,group="blue",rents=(35,175,500,1100,1300,1500),build=200),
    Space(38,"Super Tax","tax",100),
    Space(39,"Mayfair",price=400,group="blue",rents=(50,200,600,1400,1700,2000),build=200),
]
DEEDS = [s.id for s in BOARD if s.kind in {"street", "station", "utility"}]
GROUPS = {s.group: [t.id for t in BOARD if t.group == s.group] for s in BOARD if s.group}
COLORS = dict(brown="#93603d",lightblue="#77c9eb",pink="#d650a8",orange="#f59b34",red="#e15352",yellow="#ead34f",green="#37a976",blue="#367ad9")
TOKENS = ["🚗", "🎩", "🐕", "🚢", "🐈", "🦆"]
PLAYER_COLORS = ["#e46b58", "#629fff", "#dba843", "#a38ae8", "#56b8a0", "#d477b8"]

# Traditional UK card set matching the fixed £200 / £100 tax board supplied.
# Tuples: independently written summary, operation, operands.
CHANCE = [
    ("Advance to GO. Collect £200.", "move", 0),
    ("Advance to Trafalgar Square; collect £200 if you pass GO.", "move", 24),
    ("Advance to Pall Mall; collect £200 if you pass GO.", "move", 11),
    ("Go to the nearest utility. If owned, roll fresh dice and pay ten times the total.", "utility", 0),
    ("Go to the nearest station. If owned, pay twice its usual rent.", "station", 0),
    ("The bank pays you a £50 dividend.", "cash", 50),
    ("Keep this card to leave jail free, or trade it.", "jailfree", 0),
    ("Move back three spaces.", "back", 3),
    ("Go directly to jail. Do not collect £200.", "jail", 0),
    ("Pay repairs: £25 per house and £100 per hotel.", "repairs", (25,100)),
    ("Pay a £15 speeding fine.", "cash", -15),
    ("Travel to King's Cross Station; collect £200 if you pass GO.", "move", 5),
    ("Advance to Mayfair.", "move", 39),
    ("Pay each other player £50 as chairman.", "each", -50),
    ("Your building loan matures. Collect £150.", "cash", 150),
    ("Go to the nearest station. If owned, pay twice its usual rent.", "station", 0),
]
CHEST = [
    ("Advance to GO. Collect £200.", "move", 0),
    ("A bank correction pays you £200.", "cash", 200),
    ("Pay the doctor £50.", "cash", -50),
    ("Receive £50 from a stock sale.", "cash", 50),
    ("Keep this card to leave jail free, or trade it.", "jailfree", 0),
    ("Go directly to jail. Do not collect £200.", "jail", 0),
    ("Your holiday fund pays £100.", "cash", 100),
    ("Receive an income tax refund of £20.", "cash", 20),
    ("Birthday: collect £10 from every other player.", "each", 10),
    ("Your life insurance pays £100.", "cash", 100),
    ("Pay hospital fees of £100.", "cash", -100),
    ("Pay school fees of £50.", "cash", -50),
    ("Receive £25 for consultancy.", "cash", 25),
    ("Pay street repairs: £40 per house and £115 per hotel.", "repairs", (40,115)),
    ("Receive £10 for second prize in a beauty contest.", "cash", 10),
    ("Receive a £100 inheritance.", "cash", 100),
]
DECKS = {"chance": CHANCE, "chest": CHEST}

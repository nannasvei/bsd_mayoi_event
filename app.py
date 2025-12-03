import json
import base64
from html import escape
from pathlib import Path
from typing import Dict, List
import streamlit as st

# --- Ścieżki ---
BASE = Path(__file__).parent
STATE_FILE = BASE / "inventory_state.json"
ICONS = BASE / "icons"
ICON_ITEMS = {i: ICONS / f"item{i}.jpg" for i in range(1, 6)}
ICON_REWARDS = ICONS / "rewards"

# --- Zasady wymiany (do max_take, nie używamy tu w krokach) ---
EXCHANGE: Dict[int, Dict] = {
    1: {"items": {}, "ep": 1000},
    2: {"items": {1: 15}, "ep": 2000},
    3: {"items": {1: 30, 2: 15}, "ep": 2500},
    4: {"items": {2: 30, 3: 20}, "ep": 4000},
    5: {"items": {2: 30, 3: 20}, "ep": 5000},
}

# --- Lista nagród ---
REWARDS_DEF = [
    ("SSR Ticket",          1,  0,  0,  0, 150, 100, 500000),
    ("Limited R Ticket",    3,  0,  0,  0,  40,  30,  40000),
    ("SR Ticket",           2,  0,  0,  0,  40,  30,  35000),
    ("R Ticket",            3,  0, 60, 40,   0,   0,  10000),
    ("Event Skip Ticket",  20,  0,  0,  0,   5,  15,   2500),
    ("AP Drink EX",         1,  0,  0,  0,  10,  10,   5000),
    ("Luxury Boiled Tofu", 10,  0,  0,  0,  10,  10,   5000),
    ("Color Boiled Tofu",  20,  0,  0,  0,   5,   5,   3000),
    ("Luxury Chazuke",     20,  0,  0, 30,  10,   0,   3000),
    ("Color Chazuke",      40,  0,  0, 20,   5,   0,   2000),
    ("Luxury Crepe",       40,  0, 30, 10,   0,   0,   2000),
    ("Color Crepe",        60,  0,  5, 10,   0,   0,   1000),
    ("Luxury Ramune",      60, 20, 10,  0,   0,   0,   1000),
    ("Color Book",          5,  0,  0,  0,  10,  10,   5000),
    ("Color Draft Paper",  10,  0,  0, 30,  10,   0,   3000),
    ("Color Fountain Pen", 15,  0, 30, 10,   0,   0,   2000),
    ("Color Pencil",       20, 20, 10,  0,   0,   0,   1000),
]

# --- Modele ---
class Inventory:
    def __init__(self, ep: int, items: List[int]):
        self.ep = ep
        self.items = items

    def copy(self) -> "Inventory":
        return Inventory(self.ep, self.items.copy())

class Reward:
    def __init__(self, name: str, limit: int, items: List[int], ep: int):
        self.name = name
        self.limit = limit
        self.items = items
        self.ep = ep

# --- Helpery ---
def img_data_uri(path: Path, size: int = 32) -> str:
    if not path or not path.exists():
        return ""
    b = path.read_bytes()
    encoded = base64.b64encode(b).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"

def reward_icon_path(name: str) -> Path:
    safe = name.lower().replace(" ", "_")
    return ICON_REWARDS / f"{safe}.jpg"

def fmt_ep(ep: int) -> str:
    return f"{ep:,}".replace(",", " ")

# --- Logika max ---
def can_make(n: int, inv: Inventory, r: Reward) -> bool:
    if n <= 0:
        return True
    inv = inv.copy()
    need = [0] * 6
    ep_need = r.ep * n

    for i in range(1, 6):
        need[i] = r.items[i] * n

    for t in range(5, 1, -1):
        if need[t] <= 0:
            continue
        use = min(need[t], inv.items[t])
        need[t] -= use
        inv.items[t] -= use

        if need[t] > 0:
            rec = EXCHANGE[t]
            cnt = need[t]
            for low, amt in rec["items"].items():
                need[low] += cnt * amt
            ep_need += cnt * rec["ep"]
            need[t] = 0

    if need[1] > 0:
        use = min(need[1], inv.items[1])
        need[1] -= use
        inv.items[1] -= use
        if need[1] > 0:
            ep_need += need[1] * EXCHANGE[1]["ep"]
            need[1] = 0

    return ep_need <= inv.ep

def max_take(inv: Inventory, r: Reward) -> int:
    if not can_make(1, inv, r):
        return 0
    lo, hi = 1, r.limit
    while lo < hi:
        m = (lo + hi + 1) // 2
        if can_make(m, inv, r):
            lo = m
        else:
            hi = m - 1
    return lo

# --- Stan ---
def load_state() -> Inventory:
    if not STATE_FILE.exists():
        return Inventory(0, [0, 0, 0, 0, 0, 0])
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        ep = int(d.get("ep", 0))
        items = [int(x) for x in d.get("items", [0, 0, 0, 0, 0, 0])]
        return Inventory(ep, items)
    except Exception:
        return Inventory(0, [0, 0, 0, 0, 0, 0])

def save_state(inv: Inventory) -> None:
    STATE_FILE.write_text(
        json.dumps({"ep": inv.ep, "items": inv.items}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def load_rewards() -> List[Reward]:
    lst: List[Reward] = []
    for name, limit, i1, i2, i3, i4, i5, ep in REWARDS_DEF:
        lst.append(Reward(name, limit, [0, i1, i2, i3, i4, i5], ep))
    return lst

# --- Braki uproszczone (bez wymian, tylko "ile mi brakuje") ---
def compute_missing_direct(inv: Inventory, reward: Reward, count: int):
    """
    Liczymy prosto:
    - potrzeba = recepta * count
    - braki = max(0, potrzeba - posiadane)
    Bez uwzględniania wymian. To odpowiada: "co muszę jeszcze zdobyć / wyfarmić".
    """
    need_items = [0] * 6
    missing_items = [0] * 6

    for i in range(1, 6):
        need_items[i] = reward.items[i] * count
        missing_items[i] = max(0, need_items[i] - inv.items[i])

    need_ep = reward.ep * count
    missing_ep = max(0, need_ep - inv.ep)

    return missing_items, missing_ep, need_items, need_ep

# --- UI ---
def main():
    st.set_page_config(page_title="Event Rewards Calculator", layout="wide")
    st.title("Event Rewards Calculator")

    inv = load_state()

    st.header("Twój ekwipunek")
    cols = st.columns(6)

    with cols[0]:
        ep = st.number_input("EP", min_value=0, value=inv.ep, step=1000)

    items = [0] * 6
    for i in range(1, 6):
        with cols[i]:
            if ICON_ITEMS[i].exists():
                st.image(str(ICON_ITEMS[i]), width=40)
            items[i] = st.number_input(f"Item {i}", min_value=0, value=inv.items[i])

    new_inv = Inventory(ep, [0, items[1], items[2], items[3], items[4], items[5]])

    if st.button("Zapisz"):
        save_state(new_inv)
        st.success("Zapisano stan ekwipunku.")

    st.header("Nagrody")

    rewards = load_rewards()

    # ikonki nagłówków itemów
    item_headers_img = {
        i: img_data_uri(ICON_ITEMS[i], size=28)
        for i in range(1, 6)
    }

    # HTML tabeli
    html = []
    html.append(
        """
        <style>
        table.event-table {
            border-collapse: collapse;
            width: 100%;
            font-size: 14px;
        }
        table.event-table th, table.event-table td {
            border: 1px solid #444;
            padding: 4px 6px;
            text-align: center;
        }
        table.event-table th {
            background-color: #222;
        }
        table.event-table td.left {
            text-align: left;
        }
        </style>
        """
    )

    html.append("<table class='event-table'>")
    html.append("<thead>")
    html.append("<tr>")
    html.append("<th>Ikona</th>")
    html.append("<th>Nazwa</th>")
    html.append("<th>Limit</th>")
    for i in range(1, 6):
        uri = item_headers_img[i]
        if uri:
            html.append(f"<th><img src='{uri}' width='28'></th>")
        else:
            html.append(f"<th>Item {i}</th>")
    html.append("<th>EP</th>")
    html.append("<th>Można?</th>")
    html.append("<th>Maks</th>")
    html.append("</tr>")
    html.append("</thead>")

    html.append("<tbody>")
    for r in rewards:
        max_n = max_take(new_inv, r)
        can_sym = "✅" if max_n > 0 else "❌"
        icon_uri = img_data_uri(reward_icon_path(r.name), size=32)

        html.append("<tr>")
        if icon_uri:
            html.append(f"<td><img src='{icon_uri}' width='32'></td>")
        else:
            html.append("<td></td>")

        html.append(f"<td class='left'>{escape(r.name)}</td>")
        html.append(f"<td>{r.limit}</td>")
        for i in range(1, 6):
            html.append(f"<td>×{r.items[i]}</td>")
        html.append(f"<td>{fmt_ep(r.ep)}</td>")
        html.append(f"<td>{can_sym}</td>")
        html.append(f"<td>{max_n}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")

    st.markdown("".join(html), unsafe_allow_html=True)

    # --- Sekcja odbioru i braków ---
    st.subheader("Odbierz nagrodę i zobacz braki")

    reward_names = [r.name for r in rewards]
    selected_name = st.selectbox("Wybierz nagrodę", reward_names)

    selected_reward = next(r for r in rewards if r.name == selected_name)

    max_n_for_inv = max_take(new_inv, selected_reward)
    if max_n_for_inv == 0:
        st.info("Na razie nie stać Cię na żadną sztukę tej nagrody (z uwzględnieniem wymian).")

    count = st.number_input(
        "Ile chcesz odebrać?",
        min_value=1,
        max_value=selected_reward.limit,
        step=1,
        value=1,
    )

    # Recepta graficzna (ile trzeba ogółem na count)
    st.markdown("### Recepta na tę ilość (bez wymian):")
    rec_parts = []
    for i in range(1, 6):
        if selected_reward.items[i] > 0:
            icon_uri = img_data_uri(ICON_ITEMS[i], size=24)
            qty = selected_reward.items[i] * count
            if icon_uri:
                rec_parts.append(
                    f"<img src='{icon_uri}' width='24'> ×{qty}"
                )
            else:
                rec_parts.append(f"item{i} ×{qty}")
    rec_parts.append(f"⭐ {fmt_ep(selected_reward.ep * count)} EP")
    st.markdown(" ".join(rec_parts), unsafe_allow_html=True)

    if st.button("Pokaż braki (bez wymian)"):
        missing_items, missing_ep, need_items, need_ep = compute_missing_direct(
            new_inv, selected_reward, count
        )

        st.markdown("### 🔧 Brakuje (patrząc tylko na receptę, bez wymian):")

        anything_missing = any(missing_items[1:]) or missing_ep > 0

        if not anything_missing:
            st.info("Masz już wszystkie wymagane przedmioty i EP na tę ilość nagrody.")
        else:
            lines = []
            for i in range(1, 6):
                if missing_items[i] > 0:
                    icon_uri = img_data_uri(ICON_ITEMS[i], size=20)
                    text = f"{missing_items[i]}× item{i}"
                    if icon_uri:
                        lines.append(f"• <img src='{icon_uri}' width='20'> {text}")
                    else:
                        lines.append(f"• {text}")
            if missing_ep > 0:
                lines.append(f"• ⭐ {fmt_ep(missing_ep)} EP")

            st.markdown("<br>".join(lines), unsafe_allow_html=True)

            st.markdown("### 🔄 Uproszczone kroki:")
            st.markdown(
                "- Zdobądź brakujące itemy (item1..item5) w dowolny sposób (drop, sklep, wymiany)\n"
                "- Zdobądź brakujące EP (farmienie / wymiany)\n"
                "- Gdy wszystko będzie na zero, możesz odebrać nagrodę"
            )

if __name__ == "__main__":
    main()

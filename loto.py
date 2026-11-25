# -*- coding: utf-8 -*-
"""
LÔ TÔ GỌI SỐ CHO BOT MESSENGER
=========================================================
- Bot là NGƯỜI HÔ SỐ (có hô vần). Mỗi người một tờ vé, mỗi hàng 5 số trong 1-90.
- Ai đủ 5 số trên MỘT HÀNG thì gõ "kinh". Bot tự kiểm tra, đúng thì thắng, sai thì bị loại.
- Mỗi người góp tiền vào quỹ (lấy từ ví chung), người thắng ăn cả quỹ (nhiều người kinh
  cùng lúc thì chia đều). Bot không ăn phế.

LỆNH
    /loto [tiền vào]   mở bàn (mặc định 50/người)
    /vaoloto           vào bàn (lúc bàn đang chờ)
    /batdauloto        người mở bàn gõ để bắt đầu (hoặc tự bắt đầu sau LOBBY_TIME giây)
    kinh               báo kinh khi đã đủ 1 hàng
    /ve                xem tờ vé của mình (số đã hô được đánh dấu ✅)
    /so                xem các số đã hô
    /dungloto          huỷ ván, hoàn tiền (người mở bàn hoặc chủ bot)
"""

import asyncio
import random

# ---------------- cấu hình ----------------
DEFAULT_BUYIN = 50
MIN_BUYIN = 10
MIN_PLAYERS = 1             # đổi thành 2 nếu muốn bắt buộc có đối thủ
MAX_PLAYERS = 10
ROWS = 3                    # số hàng trên 1 tờ vé
PER_ROW = 5                 # số ô có số trên 1 hàng
LOBBY_TIME = 60             # giây chờ người vào bàn rồi tự bắt đầu
CALL_INTERVAL = 9           # giây giữa 2 lần hô số (đừng để quá nhanh kẻo Facebook để ý)
KINH_WINDOW = 3             # giây chờ xem còn ai kinh cùng lúc không
AUTO_KINH_AFTER = 2         # đủ hàng mà quên kinh: sau chừng này số bot tự kinh hộ
                            # (đặt None để tắt)

# ---------------- hô vần ----------------
RHYMES = {
    1: "Một mình một chiếu, số một!",
    2: "Hai vợ chồng son, số hai!",
    3: "Ba cô gái xinh, số ba!",
    4: "Bốn mùa hoa nở, số bốn!",
    5: "Năm ngón tay xòe, số năm!",
    6: "Sáu sáu lộc lá, số sáu!",
    7: "Bảy nổi ba chìm, số bảy!",
    8: "Tám hướng phát tài, số tám!",
    9: "Chín người mười ý, số chín!",
    10: "Mười phân vẹn mười, số mười!",
    11: "Hai que song song, mười một!",
    12: "Một tá trứng gà, mười hai!",
    13: "Mười ba mà đẹp lắm nha, mười ba!",
    14: "Mười bốn trăng sắp tròn, mười bốn!",
    15: "Mười lăm trăng rằm, mười lăm!",
    16: "Mười sáu tuổi mộng mơ, mười sáu!",
    17: "Mười bảy bẻ gãy sừng trâu, mười bảy!",
    18: "Mười tám đôi mươi gần kề, mười tám!",
    19: "Mười chín mà chưa kinh, mười chín!",
    20: "Hai mươi tuổi xuân, hai mươi!",
    22: "Hai hai, hai con vịt bơi!",
    23: "Hai ba, ai trúng thì la lên nào!",
    25: "Hai lăm, hai lăm, nửa trăm còn thiếu!",
    26: "Hai sáu, hai sáu, ghi số nhanh tay!",
    30: "Ba mươi Tết, đón xuân sang!",
    33: "Ba ba, ba con ba ba!",
    34: "Ba bốn, ba bốn, nhìn kỹ vé nha!",
    36: "Ba mươi sáu kế, chạy là thượng sách!",
    38: "Ba tám, ngày vía Thần Tài!",
    39: "Ba chín, ngày vía Thần Tài, mua vàng chưa?",
    40: "Bốn mươi, bốn mươi, tuổi chín chắn!",
    44: "Bốn bốn, tứ quý đây!",
    45: "Bốn lăm, bốn lăm, ráng chờ chút nữa!",
    49: "Bốn chín, chưa qua tám ba!",
    50: "Năm mươi, nửa trăm, nửa đường rồi!",
    52: "Năm hai, năm hai, bài tây đủ bộ!",
    55: "Năm năm, hai bàn tay vỗ!",
    56: "Năm sáu, năm sáu, ai có giơ tay!",
    60: "Sáu mươi, mừng thọ, sáu mươi!",
    66: "Sáu sáu, lộc lộc, đại thuận!",
    68: "Sáu tám, lộc phát, sáu tám!",
    69: "Sáu chín, hai bên xoay vòng!",
    70: "Bảy mươi, xưa nay hiếm, bảy mươi!",
    75: "Bảy lăm, bảy lăm, cố lên sắp tới!",
    77: "Bảy bảy, hai cầu vồng!",
    79: "Bảy chín, bảy chín, thần tài gõ cửa!",
    80: "Tám mươi, tám mươi, còn khỏe lắm!",
    81: "Tám mốt, tám mốt, vuông vức chín nhân chín!",
    86: "Tám sáu, tám sáu, phát lộc phát tài!",
    88: "Tám tám, phát phát, phát tài phát lộc!",
    89: "Tám chín, tám chín, sắp hết rồi nha!",
    90: "Chín mươi, số cuối cùng, chín mươi!",
    99: "Chín chín, trường cửu, chín chín!",
}

TEMPLATES = [
    "Con số {w}, ai có thì giơ tay!",
    "Ơ kìa, {w}! Ai có {w} không nào?",
    "{w}, {w}, nghe cho rõ nha!",
    "Số {w} đây, dò vé đi bà con!",
    "Hô lên {w}, tìm cho kỹ nha!",
]

UNITS = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def doc_so(n):
    """Đọc số 1-90 bằng chữ: 15 -> 'mười lăm', 21 -> 'hai mươi mốt'."""
    if n < 10:
        return UNITS[n]
    if n == 10:
        return "mười"
    if n < 20:
        u = n - 10
        return "mười " + ("lăm" if u == 5 else UNITS[u])
    t, u = divmod(n, 10)
    s = UNITS[t] + " mươi"
    if u == 0:
        return s
    return s + " " + {1: "mốt", 4: "bốn", 5: "lăm"}.get(u, UNITS[u])


def ho_van(n, rng=random):
    if n in RHYMES:
        return RHYMES[n]
    line = rng.choice(TEMPLATES).format(w=doc_so(n))
    return line[0].upper() + line[1:]


# ---------------- vé ----------------
def _columns():
    cols = [list(range(1, 10))]
    cols += [list(range(10 * i, 10 * i + 10)) for i in range(1, 8)]
    cols.append(list(range(80, 91)))
    return cols


def make_ticket(rng=random):
    """ROWS hàng, mỗi hàng PER_ROW số khác cột nhau, không trùng số trên cùng tờ."""
    cols = _columns()
    used, count, rows = set(), [0] * 9, []
    for _ in range(ROWS):
        order = sorted(range(9), key=lambda c: (count[c], rng.random()))
        row = []
        for c in sorted(order[:PER_ROW]):
            n = rng.choice([x for x in cols[c] if x not in used])
            used.add(n)
            count[c] += 1
            row.append(n)
        rows.append(row)
    return rows


def row_complete(row, called):
    return all(n in called for n in row)


def ticket_complete(ticket, called):
    return any(row_complete(r, called) for r in ticket)


def one_missing(ticket, called):
    """True nếu có hàng chỉ còn thiếu đúng 1 số (đang 'chờ')."""
    return any(sum(1 for n in r if n not in called) == 1 for r in ticket)


def ticket_text(ticket, called):
    lines = []
    for i, row in enumerate(ticket, 1):
        cells = " ".join(f"{n:02d}✅" if n in called else f"{n:02d}" for n in row)
        lines.append(f"Hàng {i}: {cells}" + ("  🎉 ĐỦ HÀNG!" if row_complete(row, called) else ""))
    return "\n".join(lines)


# ---------------- game ----------------
class Loto:
    def __init__(self, send_group, get_name, chips, save, is_owner=lambda uid: False):
        self.send_group = send_group
        self.get_name = get_name
        self.chips = chips          # dict dùng chung ví tiền với các game khác
        self.save = save
        self.is_owner = is_owner
        self._reset()

    def _reset(self):
        self.phase = "idle"         # idle | lobby | calling | kinh | settling
        self.buyin = DEFAULT_BUYIN
        self.host = ""
        self.players = []
        self.tickets = {}
        self.out = set()            # bị loại vì kinh sai
        self.called = []
        self.callset = set()
        self.winners = []
        self.ready = {}             # uid -> số lần đã hô lúc đủ hàng (để bot tự kinh hộ)
        self.paid = False           # đã thu tiền vào chưa
        self.tasks = []

    def _cancel_tasks(self):
        cur = asyncio.current_task()
        for t in self.tasks:
            if not t.done() and t is not cur:
                t.cancel()
        self.tasks = []

    def abort(self):
        """Huỷ ván; nếu đã thu tiền thì hoàn lại."""
        self._cancel_tasks()
        if self.paid:
            for u in self.players:
                self.chips[u] = self._money(u) + self.buyin
            self.save()
        self._reset()

    def _money(self, uid):
        return self.chips.setdefault(uid, 1000)

    def _active(self):
        return [u for u in self.players if u not in self.out]

    # --- điều phối ---
    async def handle(self, cmd, uid):
        if cmd == "/loto" or cmd.startswith("/loto "):
            await self._open(uid, cmd[5:].strip())
        elif cmd == "/vaoloto":
            await self._join(uid)
        elif cmd == "/batdauloto":
            await self._start_cmd(uid)
        elif cmd == "/ve":
            await self._ve(uid)
        elif cmd == "/so":
            await self._so()
        elif cmd == "/dungloto":
            await self._stop(uid)
        elif cmd.strip("! .") in ("kinh", "/kinh") and self.phase in ("calling", "kinh") \
                and uid in self.players:
            await self._kinh(uid)
        else:
            return False
        return True

    # --- mở bàn / vào bàn ---
    async def _open(self, uid, arg):
        if self.phase != "idle":
            await self.send_group("🎰 Đang có ván lô tô rồi, gõ /vaoloto nếu bàn đang chờ.")
            return
        buyin = DEFAULT_BUYIN
        if arg:
            try:
                buyin = int(arg)
            except ValueError:
                await self.send_group("Tiền vào bàn phải là số, vd: /loto 100")
                return
            if buyin < MIN_BUYIN:
                await self.send_group(f"Tối thiểu {MIN_BUYIN}.")
                return
        if self._money(uid) < buyin:
            await self.send_group(f"Không đủ tiền vào bàn ({self._money(uid)}). Gõ /tien xem lại.")
            return
        self.phase, self.buyin, self.host, self.players = "lobby", buyin, uid, [uid]
        name = await self.get_name(uid)
        await self.send_group(
            f"🎰 LÔ TÔ GỌI SỐ! {name} mở bàn, vào bàn {buyin}/người, ăn cả quỹ.\n"
            f"Gõ /vaoloto để tham gia ({LOBBY_TIME}s). {name} gõ /batdauloto để bắt đầu sớm.\n"
            f"Luật: ai đủ {PER_ROW} số trên 1 hàng thì gõ \"kinh\". Kinh sai bị loại!")
        self.tasks.append(asyncio.create_task(self._lobby_timer()))

    async def _join(self, uid):
        if self.phase != "lobby" or uid in self.players:
            return
        if len(self.players) >= MAX_PLAYERS:
            await self.send_group("Bàn đầy rồi.")
            return
        if self._money(uid) < self.buyin:
            await self.send_group(f"{await self.get_name(uid)} không đủ tiền ({self._money(uid)}).")
            return
        self.players.append(uid)
        await self.send_group(f"✅ {await self.get_name(uid)} đã vào bàn ({len(self.players)} người).")

    async def _lobby_timer(self):
        try:
            await asyncio.sleep(LOBBY_TIME)
            if self.phase == "lobby":
                await self._start()
        except asyncio.CancelledError:
            pass

    async def _start_cmd(self, uid):
        if self.phase == "lobby" and (uid == self.host or self.is_owner(uid)):
            self._cancel_tasks()
            await self._start()

    # --- bắt đầu ---
    async def _start(self):
        # thu tiền vào bàn; ai không còn đủ tiền (do chơi game khác) thì mời ra
        ok, dropped = [], []
        for u in self.players:
            (ok if self._money(u) >= self.buyin else dropped).append(u)
        for u in dropped:
            await self.send_group(f"{await self.get_name(u)} không còn đủ tiền, mời ra khỏi bàn.")
        if len(ok) < MIN_PLAYERS:
            await self.send_group("🎰 Không đủ người chơi, huỷ ván.")
            self._reset()
            return
        self.players = ok
        for u in ok:
            self.chips[u] = self._money(u) - self.buyin
        self.paid = True
        self.save()
        self.tickets = {u: make_ticket() for u in ok}
        self.phase = "calling"

        pool = self.buyin * len(ok)
        await self.send_group(f"🎰 BẮT ĐẦU! {len(ok)} người, quỹ {pool}. Phát vé:")
        for i in range(0, len(ok), 3):          # gộp 3 người / tin cho đỡ dày
            chunk = []
            for u in ok[i:i + 3]:
                chunk.append(f"🎟️ {await self.get_name(u)}\n{ticket_text(self.tickets[u], set())}")
            await self.send_group("\n\n".join(chunk))
            await asyncio.sleep(0.5)
        await self.send_group("Bot hô số đây, nghe cho kỹ! Đủ 1 hàng thì gõ \"kinh\". /ve xem vé của mình.")
        self.tasks.append(asyncio.create_task(self._call_loop()))

    # --- hô số ---
    async def _call_loop(self):
        try:
            deck = list(range(1, 91))
            random.shuffle(deck)
            await asyncio.sleep(3)
            while self.phase == "calling" and deck:
                n = deck.pop()
                self.called.append(n)
                self.callset.add(n)
                msg = f"🔢 SỐ {n:02d}   (đã hô {len(self.called)}/90)\n🎤 {ho_van(n)}"
                waiting = [await self.get_name(u) for u in self._active()
                           if one_missing(self.tickets[u], self.callset)
                           and not ticket_complete(self.tickets[u], self.callset)]
                if waiting:
                    msg += "\n⏳ Đang chờ: " + ", ".join(waiting)
                await self.send_group(msg)
                if self.phase != "calling":
                    return
                if await self._auto_kinh():
                    return
                await asyncio.sleep(CALL_INTERVAL)
            if self.phase == "calling":     # hô hết 90 số mà chưa ai kinh
                await self._auto_kinh(force=True)
        except asyncio.CancelledError:
            pass

    async def _auto_kinh(self, force=False):
        """Ai đủ hàng mà quên kinh quá AUTO_KINH_AFTER số thì bot kinh hộ.
        force=True: đã hô hết 90 số, kinh hộ tất cả những ai đã đủ hàng."""
        if AUTO_KINH_AFTER is None and not force:
            return False
        auto = []
        for u in self._active():
            if ticket_complete(self.tickets[u], self.callset):
                self.ready.setdefault(u, len(self.called))
                if force or len(self.called) - self.ready[u] >= AUTO_KINH_AFTER:
                    auto.append(u)
        if not auto:
            return False
        for u in auto:
            await self.send_group(f"🤖 {await self.get_name(u)} đủ hàng mà quên kinh, bot kinh hộ!")
        self.winners = auto
        self.phase = "settling"
        await self._settle()
        return True

    # --- kinh ---
    async def _kinh(self, uid):
        if uid in self.out or uid in self.winners:
            return
        name = await self.get_name(uid)
        if ticket_complete(self.tickets[uid], self.callset):
            self.winners.append(uid)
            await self.send_group(f"🎉 {name} KINH! Đúng rồi!")
            if self.phase == "calling":
                self.phase = "kinh"     # dừng hô số, chờ xem còn ai kinh cùng lúc
                self.tasks.append(asyncio.create_task(self._kinh_window()))
        else:
            self.out.add(uid)
            await self.send_group(f"❌ {name} kinh nhầm, bị loại khỏi ván!")
            if not self._active() and not self.winners:
                await self.send_group("Không còn ai trong ván, hoàn tiền cho mọi người.")
                self.abort()

    async def _kinh_window(self):
        try:
            await asyncio.sleep(KINH_WINDOW)
            if self.phase == "kinh":
                self.phase = "settling"
                await self._settle()
        except asyncio.CancelledError:
            pass

    async def _settle(self):
        pool = self.buyin * len(self.players)
        share = pool // len(self.winners)
        lines = [f"🏆 KẾT THÚC sau {len(self.called)} số! Quỹ {pool}", ""]
        for u in self.winners:
            self.chips[u] = self._money(u) + share
            lines.append(f"✅ {await self.get_name(u)}: +{share}  [còn {self.chips[u]}]")
            lines.append(ticket_text(self.tickets[u], self.callset))
        for u in self.players:
            if u not in self.winners:
                lines.append(f"❌ {await self.get_name(u)}: -{self.buyin}  [còn {self.chips[u]}]")
        self.save()
        lines.append("\nChơi tiếp: /loto")
        await self.send_group("\n".join(lines))
        self.paid = False               # đã trả quỹ xong, abort/reset sẽ không hoàn tiền nữa
        self._cancel_tasks()
        self._reset()

    # --- phụ ---
    async def _ve(self, uid):
        if self.phase in ("calling", "kinh") and uid in self.players:
            tag = " (đã bị loại)" if uid in self.out else ""
            await self.send_group(
                f"🎟️ Vé của {await self.get_name(uid)}{tag}\n{ticket_text(self.tickets[uid], self.callset)}")

    async def _so(self):
        if self.phase in ("calling", "kinh") and self.called:
            nums = " ".join(f"{n:02d}" for n in sorted(self.callset))
            await self.send_group(f"🔢 Đã hô {len(self.called)} số (số mới nhất: {self.called[-1]:02d}):\n{nums}")

    async def _stop(self, uid):
        if self.phase in ("lobby", "calling", "kinh") and (uid == self.host or self.is_owner(uid)):
            refunded = self.paid
            self.abort()
            await self.send_group("🛑 Đã huỷ ván lô tô" + (", hoàn tiền cho mọi người." if refunded else "."))

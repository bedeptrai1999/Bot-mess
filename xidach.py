# -*- coding: utf-8 -*-
"""
XÌ DÁCH CHO BOT MESSENGER
=========================================================
- Bot là NHÀ CÁI, mọi người chơi với bot.
- Bài của mọi người hiện CÔNG KHAI trong nhóm (bài nhà cái lật ở cuối ván).
- Module này KHÔNG import gì từ bot.py, chỉ nhận 2 hàm async từ bên ngoài:
      send_group(text)        gửi vào nhóm
      get_name(user_id)       lấy tên hiển thị

LỆNH
    /xidach [tiền cược]   mở bàn (mặc định cược 100)
    /vao                  vào bàn (lúc bàn đang chờ)
    /chia                 người mở bàn gõ để chia bài (hoặc tự chia sau LOBBY_TIME giây)
    rút | /rut            rút thêm 1 lá
    dằn | /dan            dừng (phải từ 16 điểm trở lên)
    /bai                  hiện lại bàn đang chơi
    /tien                 xem tiền của mình (hết sạch gõ để được cho lại)
    /giau                 bảng top 5 người nhiều tiền nhất
    /cong <số> [ai]       (CHỦ BOT) cộng tiền. Bỏ trống [ai] = cộng cho mình;
                          [ai] = một phần tên (vd: /cong 500 minh), ID Facebook, hoặc all
    /dungxidach           huỷ bàn (người mở bàn hoặc chủ bot)
"""

import asyncio
import json
import os
import random
import time
from itertools import product
from pathlib import Path

# ---------------- cấu hình ----------------
DEFAULT_BET = 100
START_CHIPS = 1000
REFILL_CHIPS = 500          # hết tiền gõ /tien sẽ được cho lại
MAX_PLAYERS = 7
LOBBY_TIME = 60             # giây chờ người vào bàn rồi tự chia
PLAY_TIME = 60              # giây để mọi người rút/dằn
DEALER_STAND = 16           # nhà cái rút tới khi đủ điểm này
MIN_STAND = 16              # người chơi phải đủ điểm này mới được dằn
CHIPS_FILE = str(Path(os.environ.get("DATA_DIR", ".")) / "xidach_chips.json")
MAX_GRANT = 10_000_000       # mỗi lần /cong tối đa

SUITS = "♠♥♦♣"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# tier: 0 quắc, 1 thường, 3 ngũ linh, 4 xì dách, 5 xì bàn
MULT = {0: 1, 1: 1, 3: 2, 4: 2, 5: 3}
TIER_NAME = {0: "quắc", 1: "", 3: "NGŨ LINH", 4: "XÌ DÁCH", 5: "XÌ BÀN"}


# ---------------- luật chơi (hàm thuần) ----------------
def new_deck():
    d = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(d)
    return d


def card_str(c):
    return f"{c[0]}{c[1]}"


def hand_str(h):
    return " ".join(card_str(c) for c in h)


def points(hand):
    """Điểm tốt nhất không quá 21; nếu không có thì trả điểm nhỏ nhất (>21 = quắc).
    Át: 2-3 lá được 1/10/11, 4 lá được 1/10, 5 lá chỉ 1."""
    n = len(hand)
    aces = sum(1 for r, _ in hand if r == "A")
    base = sum(10 if r in ("10", "J", "Q", "K") else int(r)
               for r, _ in hand if r != "A")
    allowed = (1, 10, 11) if n <= 3 else ((1, 10) if n == 4 else (1,))
    best = None
    for combo in product(allowed, repeat=aces):
        t = base + sum(combo)
        if t <= 21 and (best is None or t > best):
            best = t
    return best if best is not None else base + aces


def classify(hand):
    """Trả (tier, điểm)."""
    n = len(hand)
    p = points(hand)
    if n == 2 and hand[0][0] == "A" and hand[1][0] == "A":
        return 5, p
    if n == 2 and p == 21 and any(r == "A" for r, _ in hand):
        return 4, p
    if p > 21:
        return 0, p
    if n == 5:
        return 3, p
    return 1, p


def compare(player, dealer):
    """Số dương = người chơi thắng (nhân hệ số), âm = thua, 0 = hoà."""
    pt, pp = classify(player)
    dt, dp = classify(dealer)
    if pt == 0:
        return -MULT[dt]
    if dt == 0:
        return MULT[pt]
    pk = (pt, pp if pt == 1 else 0)
    dk = (dt, dp if dt == 1 else 0)
    if pk > dk:
        return MULT[pt]
    if pk < dk:
        return -MULT[dt]
    return 0


# ---------------- game ----------------
class XiDach:
    def __init__(self, send_group, get_name, is_owner=lambda uid: False, find_uid=lambda q: []):
        self.send_group = send_group
        self.find_uid = find_uid      # tìm ID theo một phần tên
        self.get_name = get_name
        self.is_owner = is_owner
        self.chips = self._load()
        self._reset()

    # --- lưu tiền ---
    def _load(self):
        try:
            return {k: int(v) for k, v in json.loads(
                Path(CHIPS_FILE).read_text(encoding="utf-8")).items()}
        except Exception:
            return {}

    def _save(self):
        try:
            Path(CHIPS_FILE).write_text(
                json.dumps(self.chips, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"⚠️  Không lưu được tiền xì dách: {e}")

    def _money(self, uid):
        return self.chips.setdefault(uid, START_CHIPS)

    # --- trạng thái ---
    def _reset(self):
        self.phase = "idle"          # idle | lobby | playing
        self.bet = DEFAULT_BET
        self.host = ""
        self.players = []
        self.hands = {}
        self.done = set()
        self.dealer = []
        self.deck = []
        self.task = None

    def abort(self):
        if self.task and not self.task.done():
            self.task.cancel()
        self._reset()

    def active(self):
        return self.phase != "idle"

    # --- điều phối lệnh: trả True nếu tin này thuộc game (bot không xử lý tiếp) ---
    async def handle(self, cmd, uid):
        if cmd == "/xidach" or cmd.startswith("/xidach "):
            await self._open(uid, cmd[8:].strip())
        elif cmd == "/vao":
            await self._join(uid)
        elif cmd == "/chia":
            await self._deal_cmd(uid)
        elif cmd in ("/rut", "rút", "rut") and self._in_play(uid):
            await self._hit(uid)
        elif cmd in ("/dan", "dằn", "dan") and self._in_play(uid):
            await self._stand(uid)
        elif cmd == "/bai":
            await self._resend(uid)
        elif cmd == "/tien":
            await self._tien(uid)
        elif cmd == "/giau":
            await self._giau()
        elif cmd == "/cong" or cmd.startswith("/cong "):
            await self._cong(uid, cmd[5:].strip())
        elif cmd == "/dungxidach":
            await self._stop(uid)
        else:
            return False
        return True

    def _in_play(self, uid):
        return self.phase == "playing" and uid in self.players

    # --- mở bàn / vào bàn ---
    async def _open(self, uid, arg):
        if self.active():
            await self.send_group("🃏 Đang có bàn xì dách rồi, gõ /vao (nếu bàn đang chờ).")
            return
        bet = DEFAULT_BET
        if arg:
            try:
                bet = int(arg)
            except ValueError:
                await self.send_group("Cược phải là số, vd: /xidach 200")
                return
            if bet < 10:
                await self.send_group("Cược tối thiểu 10.")
                return
        if self._money(uid) < bet:
            await self.send_group(f"Không đủ tiền cược ({self._money(uid)}). Gõ /tien xem lại.")
            return
        self.phase, self.bet, self.host = "lobby", bet, uid
        self.players = [uid]
        name = await self.get_name(uid)
        await self.send_group(
            f"🃏 XÌ DÁCH! {name} mở bàn, cược {bet}/ván, bot làm cái.\n"
            f"Gõ /vao để tham gia ({LOBBY_TIME}s). {name} gõ /chia để chia sớm.")
        self.task = asyncio.create_task(self._lobby_timer())

    async def _join(self, uid):
        if self.phase != "lobby":
            return
        if uid in self.players:
            return
        if len(self.players) >= MAX_PLAYERS:
            await self.send_group("Bàn đầy rồi.")
            return
        if self._money(uid) < self.bet:
            await self.send_group(f"{await self.get_name(uid)} không đủ tiền ({self._money(uid)}).")
            return
        self.players.append(uid)
        await self.send_group(f"✅ {await self.get_name(uid)} đã vào bàn ({len(self.players)} người).")

    async def _lobby_timer(self):
        try:
            await asyncio.sleep(LOBBY_TIME)
            if self.phase == "lobby":
                await self._deal()
        except asyncio.CancelledError:
            pass

    async def _deal_cmd(self, uid):
        if self.phase == "lobby" and (uid == self.host or self.is_owner(uid)):
            if self.task and not self.task.done():
                self.task.cancel()
            await self._deal()

    # --- chia bài ---
    async def _deal(self):
        self.phase = "playing"
        self.deck = new_deck()
        self.hands = {u: [self.deck.pop(), self.deck.pop()] for u in self.players}
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.done = set()

        for u in self.players:                      # xì dách/xì bàn/ngũ linh thì khoá bài luôn
            if classify(self.hands[u])[0] >= 4:
                self.done.add(u)

        await self.send_group(
            "🎴 ĐÃ CHIA BÀI (nhà cái giấu 2 lá)\n" + await self._table()
            + f"\n\nGõ \"rút\" hoặc \"dằn\" trong nhóm ({PLAY_TIME}s).")

        if classify(self.dealer)[0] >= 4:           # cái có xì dách/xì bàn: lật luôn
            await self.send_group("😱 Nhà cái có bài đặc biệt, lật luôn!")
            await self._settle()
            return
        if len(self.done) == len(self.players):
            await self._settle()
            return
        self.task = asyncio.create_task(self._play_timer())

    async def _hand_line(self, uid):
        h = self.hands[uid]
        tier, p = classify(h)
        line = f"{await self.get_name(uid)}: {hand_str(h)} = {p} điểm"
        if TIER_NAME.get(tier):
            line += f" → {TIER_NAME[tier]}!"
        if tier != 0 and uid not in self.done and p < MIN_STAND:
            line += " (chưa đủ 16, phải rút)"
        elif uid in self.done and tier != 0:
            line += " 🔒"
        return line

    async def _table(self):
        return "\n".join([await self._hand_line(u) for u in self.players])

    # --- hành động của người chơi ---
    async def _hit(self, uid):
        if uid in self.done:
            return
        h = self.hands[uid]
        h.append(self.deck.pop())
        tier, _ = classify(h)
        if tier in (0, 3):                          # quắc hoặc ngũ linh: khoá bài
            self.done.add(uid)
        await self.send_group("➕ " + await self._hand_line(uid))
        await self._check_all_done()

    async def _stand(self, uid):
        if uid in self.done:
            return
        if points(self.hands[uid]) < MIN_STAND:
            await self.send_group(f"{await self.get_name(uid)} chưa đủ {MIN_STAND} điểm, không dằn được!")
            return
        self.done.add(uid)
        await self.send_group("✋ dằn - " + await self._hand_line(uid))
        await self._check_all_done()

    async def _check_all_done(self):
        if self.phase == "playing" and len(self.done) >= len(self.players):
            if self.task and not self.task.done() and self.task is not asyncio.current_task():
                self.task.cancel()
            await self._settle()

    async def _play_timer(self):
        try:
            await asyncio.sleep(PLAY_TIME)
            if self.phase == "playing":
                await self.send_group("⏰ Hết giờ! Ai chưa quyết thì bot tự xử.")
                await self._settle()
        except asyncio.CancelledError:
            pass

    async def _resend(self, uid):
        if self.phase == "playing":
            await self.send_group("🎴 BÀN HIỆN TẠI\n" + await self._table())

    # --- tính kết quả ---
    async def _settle(self):
        if self.phase != "playing":
            return
        self.phase = "settling"                     # chặn gọi 2 lần
        for u in self.players:                      # ai chưa dằn: tự rút cho đủ điểm
            h = self.hands[u]
            while u not in self.done and points(h) < MIN_STAND and len(h) < 5:
                h.append(self.deck.pop())
        while (classify(self.dealer)[0] < 4 and points(self.dealer) < DEALER_STAND
               and len(self.dealer) < 5):
            self.dealer.append(self.deck.pop())

        dt, dp = classify(self.dealer)
        d_label = TIER_NAME[dt] or f"{dp} điểm"
        lines = [f"🏦 NHÀ CÁI: {hand_str(self.dealer)}  ({d_label})", ""]
        for u in self.players:
            h = self.hands[u]
            pt, pp = classify(h)
            res = compare(h, self.dealer)
            delta = res * self.bet
            self.chips[u] = max(0, self._money(u) + delta)
            label = TIER_NAME[pt] or f"{pp} điểm"
            icon = "✅" if res > 0 else ("❌" if res < 0 else "🤝")
            sign = f"+{delta}" if delta > 0 else str(delta)
            lines.append(f"{icon} {await self.get_name(u)}: {hand_str(h)} ({label}) → {sign}  [còn {self.chips[u]}]")
        self._save()
        lines.append("\nChơi tiếp: /xidach")
        await self.send_group("\n".join(lines))
        self._reset()

    # --- phụ ---
    async def _tien(self, uid):
        m = self._money(uid)
        if m <= 0:
            self.chips[uid] = m = REFILL_CHIPS
            self._save()
            await self.send_group(f"{await self.get_name(uid)} cháy túi, bot cho lại {REFILL_CHIPS} 😭")
            return
        await self.send_group(f"💰 {await self.get_name(uid)}: {m}")

    async def _stop(self, uid):
        if self.active() and (uid == self.host or self.is_owner(uid)):
            self.abort()
            await self.send_group("🛑 Đã huỷ bàn xì dách (không ai mất tiền).")

    async def _giau(self):
        top = sorted(self.chips.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if not top:
            await self.send_group("Chưa ai chơi nên chưa có bảng xếp hạng.")
            return
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines = ["💰 TOP ĐẠI GIA"]
        for i, (u, m) in enumerate(top):
            lines.append(f"{medals[i]} {await self.get_name(u)}: {m}")
        await self.send_group("\n".join(lines))

    async def _cong(self, uid, arg):
        """/cong <số> [tên | id | all]  - chỉ chủ bot."""
        if not self.is_owner(uid):
            await self.send_group("Chỉ chủ bot mới dùng được /cong.")
            return
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await self.send_group("Cách dùng: /cong 500 (cho mình) | /cong 500 minh (theo tên) | /cong 500 all")
            return
        amount = int(parts[0])
        if not 0 < amount <= MAX_GRANT:
            await self.send_group(f"Số tiền phải từ 1 đến {MAX_GRANT}.")
            return
        target = parts[1].strip() if len(parts) > 1 else ""
        if not target:
            uids = [uid]
        elif target in ("all", "tatca", "tất cả"):
            uids = list(self.chips)          # mọi người đã từng chơi
        elif target.isdigit() and len(target) >= 8:
            uids = [target]
        else:
            uids = self.find_uid(target)
            if not uids:
                await self.send_group(f"Không tìm thấy ai tên có \"{target}\". Thử gõ ID Facebook của họ.")
                return
            if len(uids) > 1:
                names = ", ".join([f"{await self.get_name(u)} ({u})" for u in uids[:6]])
                await self.send_group(f"Có nhiều người khớp: {names}\nGõ lại kèm ID cho chính xác nhé.")
                return
        if not uids:
            await self.send_group("Chưa ai trong sổ để cộng.")
            return
        for u in uids:
            self.chips[u] = self._money(u) + amount
        self._save()
        if len(uids) == 1:
            await self.send_group(f"💸 Đã cộng {amount} cho {await self.get_name(uids[0])}, giờ có {self.chips[uids[0]]}.")
        else:
            await self.send_group(f"💸 Đã cộng {amount} cho {len(uids)} người.")
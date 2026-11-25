# -*- coding: utf-8 -*-
"""
TÀI XỈU CHO BOT MESSENGER
=========================================================
- Bot là NHÀ CÁI, lắc 3 xúc xắc. Cả nhóm cùng đặt cược trong thời gian chờ.
- Dùng chung ví tiền với xì dách / bầu cua (truyền cùng 1 dict `chips`).

LỆNH
    /taixiu [mức]     mở ván; "mức" là tiền cược mặc định khi chỉ gõ tài/xỉu (mặc định 50)
    đặt cược          gõ  tài  hoặc  xỉu  (+ số tiền), ví dụ:   tài      xỉu 200
                      mỗi người chỉ được cược 1 cửa; gõ lại để cược thêm
    /cuoctx           xem bàn cược hiện tại
    /lactx            lắc luôn (người mở ván hoặc chủ bot)
    /dungtaixiu       huỷ ván (không ai mất tiền)

LUẬT
    Tổng 3 xúc xắc: 4-10 = XỈU, 11-17 = TÀI. Thắng ăn 1x tiền cược, thua mất tiền cược.
    BÃO: 3 xúc xắc giống nhau (1-1-1, ..., 6-6-6) -> nhà cái ăn hết, ai cược cũng thua.
"""

import asyncio
import random

DEFAULT_UNIT = 50
BET_TIME = 45               # giây cho mọi người đặt cược
MIN_BET = 10
BAO_NHA_CAI_AN = True       # False = bão vẫn tính tài/xỉu bình thường

TAI, XIU = "tài", "xỉu"
EMOJI = {TAI: "🔺", XIU: "🔻"}
ALIAS = {"tài": TAI, "tai": TAI, "xỉu": XIU, "xiu": XIU, "xỉu.": XIU}
DICE_FACE = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}


def parse_bet(text, unit):
    """'tài' -> ('tài', unit); 'xỉu 200' -> ('xỉu', 200); không phải cược -> None."""
    parts = text.strip().lower().split()
    if not parts or len(parts) > 2 or parts[0] not in ALIAS:
        return None
    side = ALIAS[parts[0]]
    if len(parts) == 1:
        return side, unit
    try:
        return side, int(parts[1])
    except ValueError:
        return None


def roll(rng=random):
    return [rng.randint(1, 6) for _ in range(3)]


def outcome(dice):
    """Trả (cửa thắng hoặc None nếu bão ăn hết, tổng, có_bão)."""
    total = sum(dice)
    bao = dice[0] == dice[1] == dice[2]
    if bao and BAO_NHA_CAI_AN:
        return None, total, True
    return (TAI if total >= 11 else XIU), total, bao


def payout(bets, winner):
    """bets: {cửa: tiền}. Thắng +tiền, thua -tiền."""
    return sum(amount if side == winner else -amount for side, amount in bets.items())


class TaiXiu:
    def __init__(self, send_group, get_name, chips, save, is_owner=lambda uid: False):
        self.send_group = send_group
        self.get_name = get_name
        self.chips = chips          # dict dùng chung với xì dách / bầu cua
        self.save = save
        self.is_owner = is_owner
        self._reset()

    def _reset(self):
        self.phase = "idle"         # idle | betting | rolling
        self.unit = DEFAULT_UNIT
        self.host = ""
        self.bets = {}              # uid -> {cửa: tiền}
        self.task = None

    def abort(self):
        if self.task and not self.task.done():
            self.task.cancel()
        self._reset()

    def _money(self, uid):
        return self.chips.setdefault(uid, 1000)

    def _staked(self, uid):
        return sum(self.bets.get(uid, {}).values())

    # --- điều phối ---
    async def handle(self, cmd, uid):
        if cmd == "/taixiu" or cmd.startswith("/taixiu "):
            await self._open(uid, cmd[7:].strip())
        elif cmd == "/cuoctx":
            await self._show()
        elif cmd == "/lactx":
            await self._lac_cmd(uid)
        elif cmd == "/dungtaixiu":
            await self._stop(uid)
        elif self.phase == "betting":
            bet = parse_bet(cmd, self.unit)
            if not bet:
                return False
            await self._bet(uid, *bet)
        else:
            return False
        return True

    # --- mở ván ---
    async def _open(self, uid, arg):
        if self.phase != "idle":
            await self.send_group("🎲 Đang có ván tài xỉu rồi, cứ gõ tài hoặc xỉu để cược.")
            return
        unit = DEFAULT_UNIT
        if arg:
            try:
                unit = int(arg)
            except ValueError:
                await self.send_group("Mức cược phải là số, vd: /taixiu 100")
                return
            if unit < MIN_BET:
                await self.send_group(f"Mức tối thiểu {MIN_BET}.")
                return
        self.phase, self.unit, self.host, self.bets = "betting", unit, uid, {}
        name = await self.get_name(uid)
        await self.send_group(
            f"🎲 TÀI XỈU! {name} mở ván, bot làm cái.\n"
            f"{EMOJI[TAI]} TÀI (11-17)      {EMOJI[XIU]} XỈU (4-10)\n"
            f"⚠️ Ra bão (3 con giống nhau) là nhà cái ăn hết.\n\n"
            f"Gõ \"tài\" hoặc \"xỉu\" để cược {unit}, hoặc \"tài 100\" để chọn số tiền.\n"
            f"Có {BET_TIME}s. {name} gõ /lactx để lắc sớm. /cuoctx xem bàn cược.")
        self.task = asyncio.create_task(self._timer())

    # --- đặt cược ---
    async def _bet(self, uid, side, amount):
        if amount < MIN_BET:
            await self.send_group(f"Cược tối thiểu {MIN_BET}.")
            return
        mine = self.bets.setdefault(uid, {})
        if mine and side not in mine:
            await self.send_group(
                f"{await self.get_name(uid)} đã cược {next(iter(mine))} rồi, "
                f"không cược cả 2 cửa được.")
            return
        money = self._money(uid)
        if self._staked(uid) + amount > money:
            await self.send_group(
                f"{await self.get_name(uid)} không đủ tiền "
                f"(có {money}, đã cược {self._staked(uid)}).")
            if not mine:
                self.bets.pop(uid, None)
            return
        mine[side] = mine.get(side, 0) + amount
        await self.send_group(
            f"{EMOJI[side]} {await self.get_name(uid)} cược {side} {mine[side]}")

    async def _show(self):
        if self.phase != "betting":
            return
        if not self.bets:
            await self.send_group("Chưa ai cược. Gõ tài hoặc xỉu để cược.")
            return
        tot = {TAI: 0, XIU: 0}
        lines = ["📋 BÀN CƯỢC"]
        for uid, mine in self.bets.items():
            for side, m in mine.items():
                tot[side] += m
                lines.append(f"{EMOJI[side]} {await self.get_name(uid)}: {side} {m}")
        lines.append(f"\nTổng: tài {tot[TAI]} | xỉu {tot[XIU]}")
        await self.send_group("\n".join(lines))

    # --- lắc ---
    async def _timer(self):
        try:
            await asyncio.sleep(BET_TIME)
            if self.phase == "betting":
                await self._settle()
        except asyncio.CancelledError:
            pass

    async def _lac_cmd(self, uid):
        if self.phase == "betting" and (uid == self.host or self.is_owner(uid)):
            if self.task and not self.task.done():
                self.task.cancel()
            await self._settle()

    async def _settle(self):
        if self.phase != "betting":
            return
        self.phase = "rolling"      # chặn gọi 2 lần / cược trễ
        if not self.bets:
            await self.send_group("🎲 Không ai cược, huỷ ván.")
            self._reset()
            return

        dice = roll()
        await self.send_group("🎲 Bot đang lắc... 🥁")
        await asyncio.sleep(1.5)
        winner, total, bao = outcome(dice)
        faces = " ".join(DICE_FACE[d] for d in dice)
        nums = " + ".join(str(d) for d in dice)
        if winner is None:
            head = f"🎲 {faces}  {nums} = {total}\n🌪️ BÃO! Nhà cái ăn hết."
        else:
            head = f"🎲 {faces}  {nums} = {total}  →  {EMOJI[winner]} {winner.upper()}"
            if bao:
                head += " (có bão)"
        lines = [head, ""]
        for uid, mine in self.bets.items():
            delta = payout(mine, winner)
            self.chips[uid] = max(0, self._money(uid) + delta)
            icon = "✅" if delta > 0 else ("❌" if delta < 0 else "🤝")
            sign = f"+{delta}" if delta > 0 else str(delta)
            lines.append(f"{icon} {await self.get_name(uid)}: {sign}  [còn {self.chips[uid]}]")
        self.save()
        lines.append("\nChơi tiếp: /taixiu")
        await self.send_group("\n".join(lines))
        self._reset()

    async def _stop(self, uid):
        if self.phase == "betting" and (uid == self.host or self.is_owner(uid)):
            self.abort()
            await self.send_group("🛑 Đã huỷ ván tài xỉu (không ai mất tiền).")

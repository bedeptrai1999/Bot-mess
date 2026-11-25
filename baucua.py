# -*- coding: utf-8 -*-
"""
BẦU CUA CHO BOT MESSENGER
=========================================================
- Bot là NHÀ CÁI, lắc 3 xúc xắc. Cả nhóm cùng đặt cược trong thời gian chờ.
- Dùng chung ví tiền với xì dách (truyền cùng 1 dict `chips`).

LỆNH
    /baucua [mức]      mở ván; "mức" là tiền cược mặc định khi chỉ gõ tên con (mặc định 50)
    đặt cược           gõ tên con (+ số tiền), ví dụ:   cua      bầu 100      tôm 200
                       6 con: nai, bầu, gà, cá, cua, tôm
                       chỉ gõ tên con = cược mức mặc định; gõ lại để cược thêm
    /cuoc              xem bàn cược hiện tại
    /lac               lắc luôn (người mở ván hoặc chủ bot), khỏi chờ hết giờ
    /dungbaucua        huỷ ván (không ai mất tiền)

LUẬT TRẢ THƯỞNG
    Con mày cược ra 1 lần: lời 1x tiền cược, 2 lần: lời 2x, 3 lần: lời 3x.
    Con không ra: mất tiền cược.
"""

import asyncio
import random

DEFAULT_UNIT = 50
BET_TIME = 45               # giây cho mọi người đặt cược
MIN_BET = 10

ANIMALS = ["nai", "bầu", "gà", "cá", "cua", "tôm"]
EMOJI = {"nai": "🦌", "bầu": "🎃", "gà": "🐓", "cá": "🐟", "cua": "🦀", "tôm": "🦐"}
ALIAS = {
    "nai": "nai",
    "bầu": "bầu", "bau": "bầu",
    "gà": "gà", "ga": "gà",
    "cá": "cá", "ca": "cá",
    "cua": "cua",
    "tôm": "tôm", "tom": "tôm",
}


def parse_bet(text, unit):
    """'cua' -> ('cua', unit); 'bầu 100' -> ('bầu', 100); không phải cược -> None."""
    parts = text.strip().lower().split()
    if not parts or len(parts) > 2 or parts[0] not in ALIAS:
        return None
    animal = ALIAS[parts[0]]
    if len(parts) == 1:
        return animal, unit
    try:
        amount = int(parts[1])
    except ValueError:
        return None
    return animal, amount


def roll(rng=random):
    return [rng.choice(ANIMALS) for _ in range(3)]


def payout(bets, dice):
    """bets: {animal: tiền}. Trả (tiền thắng/thua, chi tiết)."""
    total = 0
    for animal, amount in bets.items():
        hits = dice.count(animal)
        total += amount * hits if hits else -amount
    return total


class BauCua:
    def __init__(self, send_group, get_name, chips, save, is_owner=lambda uid: False):
        self.send_group = send_group
        self.get_name = get_name
        self.chips = chips          # dict dùng chung với xì dách
        self.save = save
        self.is_owner = is_owner
        self._reset()

    def _reset(self):
        self.phase = "idle"         # idle | betting
        self.unit = DEFAULT_UNIT
        self.host = ""
        self.bets = {}              # uid -> {animal: tiền}
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
        if cmd == "/baucua" or cmd.startswith("/baucua "):
            await self._open(uid, cmd[7:].strip())
        elif cmd == "/cuoc":
            await self._show()
        elif cmd == "/lac":
            await self._lac_cmd(uid)
        elif cmd == "/dungbaucua":
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
            await self.send_group("🎲 Đang có ván bầu cua rồi, cứ gõ tên con để cược.")
            return
        unit = DEFAULT_UNIT
        if arg:
            try:
                unit = int(arg)
            except ValueError:
                await self.send_group("Mức cược phải là số, vd: /baucua 100")
                return
            if unit < MIN_BET:
                await self.send_group(f"Mức tối thiểu {MIN_BET}.")
                return
        self.phase, self.unit, self.host, self.bets = "betting", unit, uid, {}
        name = await self.get_name(uid)
        icons = "  ".join(f"{EMOJI[a]} {a}" for a in ANIMALS)
        await self.send_group(
            f"🎲 BẦU CUA! {name} mở ván, bot làm cái.\n{icons}\n\n"
            f"Gõ tên con để cược: \"cua\" = cược {unit}, hoặc \"bầu 100\" để chọn số tiền.\n"
            f"Có {BET_TIME}s. {name} gõ /lac để lắc sớm. /cuoc xem bàn cược.")
        self.task = asyncio.create_task(self._timer())

    # --- đặt cược ---
    async def _bet(self, uid, animal, amount):
        if amount < MIN_BET:
            await self.send_group(f"Cược tối thiểu {MIN_BET}.")
            return
        money = self._money(uid)
        if self._staked(uid) + amount > money:
            await self.send_group(
                f"{await self.get_name(uid)} không đủ tiền "
                f"(có {money}, đã cược {self._staked(uid)}).")
            return
        mine = self.bets.setdefault(uid, {})
        mine[animal] = mine.get(animal, 0) + amount
        await self.send_group(
            f"{EMOJI[animal]} {await self.get_name(uid)} cược {animal} "
            f"{mine[animal]} (tổng {self._staked(uid)})")

    async def _show(self):
        if self.phase != "betting":
            return
        if not self.bets:
            await self.send_group("Chưa ai cược. Gõ tên con (cua, bầu, tôm...) để cược.")
            return
        lines = ["📋 BÀN CƯỢC"]
        for uid, mine in self.bets.items():
            detail = ", ".join(f"{EMOJI[a]}{a} {m}" for a, m in mine.items())
            lines.append(f"{await self.get_name(uid)}: {detail}")
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
        lines = [f"🎲 KẾT QUẢ:  {'  '.join(EMOJI[d] + ' ' + d for d in dice)}", ""]
        for uid, mine in self.bets.items():
            delta = payout(mine, dice)
            self.chips[uid] = max(0, self._money(uid) + delta)
            icon = "✅" if delta > 0 else ("❌" if delta < 0 else "🤝")
            sign = f"+{delta}" if delta > 0 else str(delta)
            lines.append(f"{icon} {await self.get_name(uid)}: {sign}  [còn {self.chips[uid]}]")
        self.save()
        lines.append("\nChơi tiếp: /baucua")
        await self.send_group("\n".join(lines))
        self._reset()

    async def _stop(self, uid):
        if self.phase == "betting" and (uid == self.host or self.is_owner(uid)):
            self.abort()
            await self.send_group("🛑 Đã huỷ ván bầu cua (không ai mất tiền).")

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import requests
from bs4 import BeautifulSoup

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

STATE_FILE = "tv_program_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

TALENTS = [
    {"key": "hiyori", "name": "濱岸ひより"},
    {"key": "kawada", "name": "河田陽菜"},
]

# bangumi.org の area_code → 地域名（サイトの地域セレクタと同じ並び）
AREAS = {
    10: "札幌", 11: "函館", 12: "旭川", 13: "帯広", 14: "釧路", 15: "北見", 16: "室蘭",
    17: "宮城", 18: "秋田", 19: "山形", 20: "岩手", 21: "福島", 22: "青森",
    23: "東京", 24: "神奈川", 25: "群馬", 26: "茨城", 27: "千葉", 28: "栃木", 29: "埼玉",
    30: "長野", 31: "新潟", 32: "山梨", 33: "愛知", 34: "石川", 35: "静岡", 36: "福井",
    37: "富山", 38: "三重", 39: "岐阜",
    40: "大阪", 41: "京都", 42: "兵庫", 43: "和歌山", 44: "奈良", 45: "滋賀",
    46: "広島", 47: "岡山", 48: "島根", 49: "鳥取", 50: "山口",
    51: "愛媛", 52: "香川", 53: "徳島", 54: "高知",
    55: "福岡", 56: "熊本", 57: "長崎", 58: "鹿児島", 59: "宮崎", 60: "大分", 61: "佐賀",
    62: "沖縄", 63: "北九州",
}
TOKYO_AREA = 23  # 通知対象から除外する地域（東京で放送される番組は通知しない）

MAX_WORKERS = 8
MAX_AREAS_IN_MESSAGE = 6


def send_line(text: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    resp.raise_for_status()


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_bangumi_area(name: str, area_code: int) -> dict[str, tuple[str, str]]:
    """番組表.Gガイド（bangumi.org）の指定地域の検索結果を ebisId -> (タイトル, 日時と放送局) で返す"""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://bangumi.org/fetch_search_content/",
                params={"q": name, "type": "tv", "area_code": area_code},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            break
        except Exception as e:
            last_error = e
            time.sleep(0.5 * (attempt + 1))
    else:
        raise RuntimeError(f"{AREAS[area_code]}(area_code={area_code})の取得に失敗: {last_error}")

    soup = BeautifulSoup(resp.text, "html.parser")
    results = {}
    for li in soup.select("#tv-content li.block"):
        link = li.select_one("a[href^='/tv_events/']")
        if not link:
            continue
        program_id = link["href"].split("/tv_events/")[1].split("?")[0]
        ps = li.select("p.repletion")
        title = ps[0].get_text(strip=True) if len(ps) > 0 else "?"
        schedule = ps[1].get_text(strip=True) if len(ps) > 1 else "?"
        results[program_id] = (title, schedule)
    return results


def fetch_bangumi_nationwide(name: str) -> dict[str, str]:
    """東京以外の全地域を検索し、ebisId -> 通知用テキスト で返す。

    東京でも放送される番組（関東の他県にも出てくるキー局の番組など）は除外する。
    1地域でも取得に失敗したら例外にして、状態が中途半端に更新されるのを防ぐ。
    """
    area_codes = sorted(AREAS)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        per_area = dict(zip(area_codes, ex.map(partial(fetch_bangumi_area, name), area_codes)))

    tokyo_ids = set(per_area[TOKYO_AREA])

    merged: dict[str, dict] = {}
    for code in area_codes:
        if code == TOKYO_AREA:
            continue
        for pid, (title, schedule) in per_area[code].items():
            if pid in tokyo_ids:
                continue
            entry = merged.setdefault(pid, {"title": title, "schedule": schedule, "areas": []})
            entry["areas"].append(AREAS[code])

    results = {}
    for pid, e in merged.items():
        areas = e["areas"]
        shown = "、".join(areas[:MAX_AREAS_IN_MESSAGE])
        if len(areas) > MAX_AREAS_IN_MESSAGE:
            shown += f" ほか{len(areas) - MAX_AREAS_IN_MESSAGE}地域"
        results[pid] = (
            f"{e['title']}\n{e['schedule']}\n放送地域: {shown}\n"
            f"https://bangumi.org/tv_events/{pid}"
        )
    return results


ERROR_NOTIFY_THRESHOLD = 3  # この回数だけ連続で失敗したらエラー通知する（一過性の失敗は無視）


def check_source(state: dict, state_key: str, fetch_fn, name: str, source_label: str) -> None:
    error_flags = state.setdefault("_error_flags", {})
    error_counts = state.setdefault("_error_counts", {})

    try:
        current = fetch_fn()
    except Exception as e:
        print(f"[{state_key}] 取得エラー: {e}")
        error_counts[state_key] = error_counts.get(state_key, 0) + 1
        if error_counts[state_key] >= ERROR_NOTIFY_THRESHOLD and not error_flags.get(state_key):
            send_line(
                f"【エラー】{name}（{source_label}）の番組情報取得に{ERROR_NOTIFY_THRESHOLD}回連続で失敗しました。\n"
                f"{e}\n\n"
                "復旧するまでこのソースの新着検知は止まっています。"
            )
            error_flags[state_key] = True
        return

    error_counts[state_key] = 0
    if error_flags.get(state_key):
        error_flags[state_key] = False
        send_line(f"【復旧】{name}（{source_label}）の番組情報取得が復旧しました。新着検知を再開します。")

    known_ids = state.get(state_key)

    if known_ids is None:
        state[state_key] = list(current.keys())
        print(f"[{state_key}] 初回実行: {len(current)}件を保存")
        return

    known_ids = set(known_ids)
    new_ids = [pid for pid in current if pid not in known_ids]

    if not new_ids:
        print(f"[{state_key}] 変化なし ({len(current)}件)")
    else:
        for pid in new_ids:
            msg = f"【新着番組】{name}（{source_label}）\n\n{current[pid]}"
            send_line(msg)
            print(f"[{state_key}] 新着通知送信: {pid}")

    state[state_key] = list(current.keys())


def main() -> None:
    state = load_state()

    for talent in TALENTS:
        check_source(
            state,
            f"{talent['key']}_bangumi_nationwide",
            partial(fetch_bangumi_nationwide, talent["name"]),
            talent["name"],
            "番組表.Gガイド・東京以外",
        )

    save_state(state)


if __name__ == "__main__":
    main()

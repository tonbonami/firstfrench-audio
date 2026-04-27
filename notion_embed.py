#!/usr/bin/env python3
"""
firstfrench-audio / notion_embed.py
생성된 MP3를 Notion 페이지에 audio block으로 삽입

Usage:
    python notion_embed.py                          # page_map.json 전체
    python notion_embed.py pronon_nasal_01_an-am    # 특정 파일만

Flow:
    1. page_map.json에서 페이지 ID + anchor 텍스트 조회
    2. Notion REST API로 페이지 블록 목록 가져와 anchor H1 블록 ID 탐색
    3. anchor 직후에 audio block (jsDelivr CDN URL) 삽입

CDN URL 형식:
    https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@main/audio/{stem}.mp3
    ※ raw.githubusercontent.com 은 인라인 재생 불가 → jsDelivr 필수

Environment (.env):
    NOTION_API_KEY=secret_xxx
    GITHUB_REPO=tonbonami/firstfrench-audio
"""

import os, sys, json, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NOTION_KEY   = os.environ["NOTION_API_KEY"]
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "tonbonami/firstfrench-audio")
CDN_BASE     = f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@main/audio"
NOTION_BASE  = "https://api.notion.com/v1"
NOTION_VER   = "2022-06-28"

HEADERS = {
    "Authorization":  f"Bearer {NOTION_KEY}",
    "Notion-Version": NOTION_VER,
    "Content-Type":   "application/json",
}

PAGE_MAP = Path("page_map.json")
AUDIO_DIR = Path("audio")

# ── Notion 헬퍼 ───────────────────────────────────────────────────
def get_blocks(page_id: str) -> list:
    """페이지의 top-level 블록 목록 반환 (최대 100개)"""
    url  = f"{NOTION_BASE}/blocks/{page_id}/children"
    resp = requests.get(url, headers=HEADERS, params={"page_size": 100})
    resp.raise_for_status()
    return resp.json().get("results", [])

def find_anchor(blocks: list, anchor_text: str) -> str | None:
    """anchor_text를 포함하는 블록의 ID 반환 (heading 1/2/3 또는 paragraph)"""
    for block in blocks:
        btype = block.get("type", "")
        rich  = block.get(btype, {}).get("rich_text", [])
        text  = "".join(rt.get("plain_text", "") for rt in rich)
        if anchor_text.lower() in text.lower():
            return block["id"]
    return None

def insert_audio(page_id: str, after_id: str, url: str) -> dict:
    """anchor 블록 직후에 audio block 삽입"""
    body = {
        "children": [{"type": "audio", "audio": {"type": "external", "external": {"url": url}}}],
        "after": after_id,
    }
    resp = requests.patch(f"{NOTION_BASE}/blocks/{page_id}/children", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()

def already_has_audio(blocks: list, anchor_id: str, cdn_url: str) -> bool:
    """anchor 직후 블록이 이미 같은 URL의 audio block인지 확인 (중복 삽입 방지)"""
    for i, block in enumerate(blocks):
        if block["id"].replace("-", "") == anchor_id.replace("-", ""):
            if i + 1 < len(blocks):
                next_block = blocks[i + 1]
                if next_block.get("type") == "audio":
                    ext = next_block.get("audio", {}).get("external", {})
                    if ext.get("url") == cdn_url:
                        return True
    return False

# ── 메인 임베더 ───────────────────────────────────────────────────
def embed(stem: str, page_map: dict):
    entry = page_map.get(stem)
    if not entry:
        print(f"⚠ page_map 항목 없음: {stem}")
        return

    mp3 = AUDIO_DIR / f"{stem}.mp3"
    if not mp3.exists():
        print(f"⚠ MP3 없음: {mp3}  (generate_audio.py 먼저 실행)")
        return

    page_id     = entry["page_id"]
    anchor_text = entry["anchor"]
    cdn_url     = f"{CDN_BASE}/{stem}.mp3"

    print(f"\n📎 {stem}")
    print(f"   Page    : {page_id}")
    print(f"   Anchor  : '{anchor_text}'")
    print(f"   CDN URL : {cdn_url}")

    blocks    = get_blocks(page_id)
    anchor_id = find_anchor(blocks, anchor_text)

    if not anchor_id:
        print(f"   ⚠ anchor 블록 찾기 실패: '{anchor_text}'")
        print("   → Notion 페이지에서 H1 텍스트를 확인하고 page_map.json의 anchor 값을 수정하세요.")
        return

    if already_has_audio(blocks, anchor_id, cdn_url):
        print(f"   ⏭ 이미 삽입됨 — 건너뜀")
        return

    insert_audio(page_id, anchor_id, cdn_url)
    print(f"   ✅ audio block 삽입 완료")

# ── 엔트리포인트 ──────────────────────────────────────────────────
if __name__ == "__main__":
    page_map = json.loads(PAGE_MAP.read_text(encoding="utf-8"))

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(page_map.keys())
    for stem in targets:
        embed(stem, page_map)

    print("\n✨ 완료.")

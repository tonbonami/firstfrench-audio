#!/usr/bin/env python3
"""
firstfrench-audio / notion_embed.py
생성된 MP3를 Notion 페이지에 audio block으로 삽입/갱신

Usage:
    python notion_embed.py                          # page_map.json 전체
    python notion_embed.py pronon_nasal_01_an-am    # 특정 파일만

Flow:
    1. page_map.json에서 페이지 ID + anchor 텍스트 조회
    2. git rev-parse HEAD로 현재 커밋 해시 취득 → CDN URL에 반영
    3. Notion REST API로 페이지 블록 목록 가져와 anchor H1 블록 ID 탐색
    4. anchor 직후 audio block이 없으면 삽입, 있으면 URL 갱신

CDN URL 형식:
    https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GIT_HASH}/audio/{stem}.mp3
    ※ @main 대신 커밋 해시 사용 → CDN 캐시 문제 완전 우회

Environment (.env):
    NOTION_API_KEY=secret_xxx
    GITHUB_REPO=tonbonami/firstfrench-audio
"""

import os, sys, json, subprocess, requests
from typing import Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NOTION_KEY   = os.environ["NOTION_API_KEY"]
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "tonbonami/firstfrench-audio")
NOTION_BASE  = "https://api.notion.com/v1"
NOTION_VER   = "2022-06-28"

HEADERS = {
    "Authorization":  f"Bearer {NOTION_KEY}",
    "Notion-Version": NOTION_VER,
    "Content-Type":   "application/json",
}

PAGE_MAP  = Path("page_map.json")
AUDIO_DIR = Path("audio")

# ── 커밋 해시 취득 ────────────────────────────────────────────────
def get_git_hash() -> str:
    """현재 HEAD 커밋의 short hash 반환. git 없으면 'main' fallback."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent
        )
        return result.stdout.strip()[:7]
    except Exception:
        return "main"

GIT_HASH = get_git_hash()
CDN_BASE = f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GIT_HASH}/audio"

# ── Notion 헬퍼 ───────────────────────────────────────────────────
def get_blocks(page_id: str) -> list:
    """페이지의 top-level 블록 목록 반환 (최대 100개)"""
    url  = f"{NOTION_BASE}/blocks/{page_id}/children"
    resp = requests.get(url, headers=HEADERS, params={"page_size": 100})
    resp.raise_for_status()
    return resp.json().get("results", [])

def find_anchor(blocks: list, anchor_text: str) -> Optional[str]:
    """anchor_text를 포함하는 블록의 ID 반환 (heading 1/2/3 또는 paragraph)"""
    for block in blocks:
        btype = block.get("type", "")
        rich  = block.get(btype, {}).get("rich_text", [])
        text  = "".join(rt.get("plain_text", "") for rt in rich)
        if anchor_text.lower() in text.lower():
            return block["id"]
    return None

def find_audio_after_anchor(blocks: list, anchor_id: str) -> tuple:
    """anchor 직후 블록이 audio block이면 (block_id, current_url) 반환, 없으면 (None, None)"""
    for i, block in enumerate(blocks):
        if block["id"].replace("-", "") == anchor_id.replace("-", ""):
            if i + 1 < len(blocks):
                next_block = blocks[i + 1]
                if next_block.get("type") == "audio":
                    ext = next_block.get("audio", {}).get("external", {})
                    return next_block["id"], ext.get("url", "")
    return None, None

def insert_audio(page_id: str, after_id: str, url: str) -> dict:
    """anchor 블록 직후에 audio block 신규 삽입"""
    body = {
        "children": [{"type": "audio", "audio": {"type": "external", "external": {"url": url}}}],
        "after": after_id,
    }
    resp = requests.patch(f"{NOTION_BASE}/blocks/{page_id}/children", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()

def delete_block(block_id: str) -> None:
    """블록 아카이브(삭제). audio 타입은 API의 update 미지원이라 delete+insert로 우회."""
    resp = requests.delete(f"{NOTION_BASE}/blocks/{block_id}", headers=HEADERS)
    resp.raise_for_status()

def update_audio_block(block_id: str, url: str) -> dict:
    """DEPRECATED — 이전 호환용 stub. embed()에서 직접 delete+insert 사용."""
    raise RuntimeError("update_audio_block은 더 이상 사용하지 마세요. delete_block + insert_audio 조합을 쓰세요.")

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
        print("   → page_map.json의 anchor 값을 확인하세요.")
        return

    audio_block_id, current_url = find_audio_after_anchor(blocks, anchor_id)

    if audio_block_id:
        if current_url == cdn_url:
            print(f"   ⏭ 최신 URL 동일 — 건너뜀")
        else:
            delete_block(audio_block_id)
            insert_audio(page_id, anchor_id, cdn_url)
            old_hash = current_url.split('@')[1][:7] if '@' in current_url else '?'
            print(f"   🔄 재삽입 완료 ({old_hash} → {GIT_HASH})")
    else:
        insert_audio(page_id, anchor_id, cdn_url)
        print(f"   ✅ audio block 삽입 완료")

# ── 엔트리포인트 ──────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🔖 커밋 해시: {GIT_HASH}")
    page_map = json.loads(PAGE_MAP.read_text(encoding="utf-8"))

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(page_map.keys())
    for stem in targets:
        embed(stem, page_map)

    print("\n✨ 완료.")

#!/usr/bin/env python3
"""
firstfrench-audio / generate_audio.py
ElevenLabs TTS 생성기 — 나의 첫 프랑스어 책 v3.1

Usage:
    python generate_audio.py                        # scripts/ 전체 처리
    python generate_audio.py pronon_nasal_01_an-am  # 특정 파일만

Prerequisites:
    pip install requests pydub python-dotenv
    brew install ffmpeg  (macOS) / apt install ffmpeg  (Linux)

Environment (.env 또는 환경변수):
    ELEVENLABS_API_KEY=your_key_here
"""

import os, re, sys, time, io, requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ─────────────────────────────────────────────────────────
API_KEY  = os.environ["ELEVENLABS_API_KEY"]
BASE_URL = "https://api.elevenlabs.io/v1"

VOICES = {
    "FR": {"id": "sANWqF1bCMzR6eyZbCGw", "language_code": "fr", "model": "eleven_turbo_v2_5"},
    "KO": {"id": "uyVNoMrnUku1dZyVEXwD", "language_code": "ko", "model": "eleven_turbo_v2_5"},
}
VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}

SCRIPTS_DIR = Path("scripts")
OUTPUT_DIR  = Path("audio")
OUTPUT_DIR.mkdir(exist_ok=True)

# Break 태그 → 무음 길이(ms)
BREAK_MS = {"0.5s": 500, "0.7s": 700, "1.0s": 1000, "1.5s": 1500, "2.0s": 2000}

# 길이 이상 감지 (언어별 예상 ms/char)
EXPECTED_MS_PER_CHAR = {"FR": 90, "KO": 280}
RETRY_THRESHOLD = 1.8   # 예상 길이의 N배 초과 시 재시도
MIN_CLIP_MS     = 1200  # 이보다 짧은 클립은 검사 제외
MAX_RETRIES     = 2

# ── Sibilant break 자동 삽입 ─────────────────────────────────────
_SIB = re.compile(r"(s[se])([ ,'])(s['iìí])", re.IGNORECASE)

def inject_sibilant_breaks(text: str) -> str:
    """인접 /s/ 자음 경계에 200ms 무음 자동 삽입 (텍스트 변경 없이 SSML만)"""
    return _SIB.sub(r'\1\2<break time="200ms"/>\3', text)

# ── 클립 트림 ────────────────────────────────────────────────────
def trim_clip(audio: AudioSegment, thresh=-45, min_sil=30, fade=15) -> AudioSegment:
    """앞뒤 무음 제거 + 클릭 방지 fade"""
    parts = detect_nonsilent(audio, min_silence_len=min_sil, silence_thresh=thresh)
    if not parts:
        return audio
    s = max(0, parts[0][0] - 30)
    e = min(len(audio), parts[-1][1] + 30)
    return audio[s:e].fade_in(fade).fade_out(fade)

# ── TTS API 호출 ─────────────────────────────────────────────────
def tts(text: str, lang: str) -> AudioSegment:
    """ElevenLabs API 호출 → AudioSegment 반환 (길이 이상 시 자동 재시도)"""
    voice   = VOICES[lang]
    payload = {
        "text":           inject_sibilant_breaks(text),
        "model_id":       voice["model"],
        "language_code":  voice["language_code"],
        "voice_settings": VOICE_SETTINGS,
    }
    headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
    url     = f"{BASE_URL}/text-to-speech/{voice['id']}"

    for attempt in range(MAX_RETRIES + 1):
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        clip = trim_clip(AudioSegment.from_mp3(io.BytesIO(resp.content)))

        # 길이 이상 감지
        expected = len(text.replace(" ", "")) * EXPECTED_MS_PER_CHAR[lang]
        if len(clip) > MIN_CLIP_MS and len(clip) > expected * RETRY_THRESHOLD:
            print(f"    ⚠ 길이 이상 ({len(clip)}ms, 예상 {expected}ms) — 재시도 {attempt+1}/{MAX_RETRIES}")
            if attempt < MAX_RETRIES:
                time.sleep(0.5)
                continue
        break

    return clip

# ── 스크립트 파서 ─────────────────────────────────────────────────
def parse_script(path: Path) -> list:
    """
    .txt 파일 → 세그먼트 리스트
    반환 형식: [("speech", (lang, text)) | ("break", ms)]
    무시: # / = / - 로 시작하는 줄, 빈 줄
    """
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line[0] in "#=-":
            continue

        # <break time="Xs"/>
        m = re.fullmatch(r'<break time="([^"]+)"/>', line)
        if m:
            segments.append(("break", BREAK_MS.get(m.group(1), 700)))
            continue

        # [FR] text / [KO] text
        m = re.match(r'\[(FR|KO)\]\s+(.+)', line)
        if m:
            segments.append(("speech", (m.group(1), m.group(2).strip())))

    return segments

# ── 메인 생성기 ───────────────────────────────────────────────────
def generate(script_path: Path) -> Path:
    print(f"\n🎙 {script_path.name}")
    segments = parse_script(script_path)
    combined = AudioSegment.empty()
    speech_count = sum(1 for t, _ in segments if t == "speech")
    done = 0

    for seg_type, value in segments:
        if seg_type == "break":
            combined += AudioSegment.silent(duration=value)
        elif seg_type == "speech":
            lang, text = value
            print(f"  [{lang}] {text[:60]}")
            combined += tts(text, lang)
            done += 1
            time.sleep(0.3)   # rate limiting

    out = OUTPUT_DIR / (script_path.stem + ".mp3")
    combined.export(out, format="mp3", bitrate="128k")
    print(f"  ✅ {out}  ({len(combined)/1000:.1f}s,  {done}/{speech_count} 클립)")
    return out

# ── 엔트리포인트 ──────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = [SCRIPTS_DIR / f"{a}.txt" for a in sys.argv[1:]]
    else:
        targets = sorted(SCRIPTS_DIR.glob("*.txt"))

    for path in targets:
        if not path.exists():
            print(f"⚠ 파일 없음: {path}")
            continue
        generate(path)

    print("\n✨ 완료.")

#!/usr/bin/env python3
"""
firstfrench-audio / generate_audio.py
ElevenLabs TTS 생성기 — 나의 첫 프랑스어 책 v3.1

Usage:
    python generate_audio.py                        # scripts/ 전체 처리
    python generate_audio.py pronon_nasal_01_an-am  # 특정 파일만

다중 캐릭터 음성 (회화·듣기 자료용):
    스크립트 상단에 헤더로 캐릭터→음성 타입 매핑:
        # voices: Sophie=bright-female Lucas=lively-male
    본문에서:
        [FR-Sophie] Bonjour, ça va ?
        [FR-Lucas] Très bien, merci !

문법·발음 강좌는 기존 [FR]/[KO] 단일 음성 그대로 사용.
"""

import os, re, sys, time, io, requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from pydub.effects import normalize
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ─────────────────────────────────────────────────────────
API_KEY  = os.environ["ELEVENLABS_API_KEY"]
BASE_URL = "https://api.elevenlabs.io/v1"

# 발음·문법 강좌용 기본 음성 (절대 변경 금지)
VOICES = {
    "FR": {"id": "sANWqF1bCMzR6eyZbCGw", "language_code": "fr", "model": "eleven_turbo_v2_5"},
    "KO": {"id": "uyVNoMrnUku1dZyVEXwD", "language_code": "ko", "model": "eleven_turbo_v2_5"},
}

# 회화·듣기 자료용 다중 캐릭터 음성 레지스트리 (시맨틱 타입 → ElevenLabs voice_id)
# - 여성 ----------------------------------------------------------
# - 남성 ----------------------------------------------------------
VOICE_REGISTRY = {
    # 여성
    "bright-female":      "zgR4sWC2Er1b98AtnnBf",  # 조금 밝은 여성
    "older-female":       "1T2MOlQA0Xp3hNv1dBxp",  # 좀 나이든 여성
    "whispering-female":  "sH0WdfE5fsKuM2otdQZr",  # 속삭이는 여성
    "warm-mother":        "TojRWZatQyy9dujEdiQ1",  # 친절한 엄마 같은 여자
    # 남성
    "bright-male":        "vBKc2FfBKJfcZNyEt1n6",  # 조금 밝은 남성
    "lively-male":        "0bKGtCCpdKSI5NjGhU3z",  # 조금 활기찬 남성
    "older-male":         "4p5WXd3ZuWR9pPtRQuxC",  # 조금 나이 있는 남성
    "teen-male":          "mr1ubFaLs5xVrh1EqWtc",  # 중·고등학교 남자 (어린 캐릭터 대체)
    "whispering-male":    "k1w1SeihHyKDJXr7nZRX",  # 젊은 남자 속삭이는 톤
    "grandfather":        "M4DbUhGmKgKUc1GsJEHY",  # 할아버지 느낌
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

# 길이 이상 감지
EXPECTED_MS_PER_CHAR = {"FR": 90, "KO": 280}
RETRY_THRESHOLD = 1.8
MIN_CLIP_MS     = 1200
MAX_RETRIES     = 2

# ── Sibilant break 자동 삽입 ─────────────────────────────────────
_SIB = re.compile(r"(s[se])([ ,'])(s['iìí])", re.IGNORECASE)

def inject_sibilant_breaks(text: str) -> str:
    return _SIB.sub(r'\1\2<break time="200ms"/>\3', text)

# ── 클립 트림 ────────────────────────────────────────────────────
def trim_clip(audio: AudioSegment, thresh=-45, min_sil=30, fade=15, target_peak_db=-3.0, short_clip_ms=2000) -> AudioSegment:
    """앞뒤 무음 제거 + 클릭 방지 fade + peak 정규화 (-3dBFS).

    target_peak_db 정규화는 인터-클립 음량 불균형 방지가 핵심.
    ElevenLabs는 짧은 감탄문/느낌표에 음량 부스트를 자주 걸어서,
    여러 클립을 concat하면 한 클립만 폭탄처럼 시끄러워지는 문제 해결.

    단, 짧은 클립(< short_clip_ms)은 normalize 스킵 — 짧은 감탄문/감사 표현은
    TTS 본 신호가 작아서 정규화 시 노이즈 플로어가 함께 증폭되는 부작용이 큼.
    """
    parts = detect_nonsilent(audio, min_silence_len=min_sil, silence_thresh=thresh)
    if not parts:
        return audio
    s = max(0, parts[0][0] - 30)
    e = min(len(audio), parts[-1][1] + 30)
    trimmed = audio[s:e].fade_in(fade).fade_out(fade)
    # 짧은 클립 보호: normalize가 노이즈 플로어 증폭하는 부작용 차단
    if len(trimmed) < short_clip_ms:
        return trimmed
    # Peak normalize to target_peak_db (헤드룸 확보, 인터-클립 음량 균등화)
    return normalize(trimmed, headroom=abs(target_peak_db))


# ── TTS API 호출 ─────────────────────────────────────────────────
def tts(text: str, lang: str, voice_id: str = None) -> AudioSegment:
    """ElevenLabs API 호출. voice_id가 주어지면 기본 음성 대신 사용."""
    voice  = VOICES[lang]
    use_id = voice_id if voice_id else voice["id"]
    payload = {
        "text":           inject_sibilant_breaks(text),
        "model_id":       voice["model"],
        "language_code":  voice["language_code"],
        "voice_settings": VOICE_SETTINGS,
    }
    headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
    url     = f"{BASE_URL}/text-to-speech/{use_id}"

    for attempt in range(MAX_RETRIES + 1):
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        clip = trim_clip(AudioSegment.from_mp3(io.BytesIO(resp.content)))

        expected = len(text.replace(" ", "")) * EXPECTED_MS_PER_CHAR[lang]
        if len(clip) > MIN_CLIP_MS and len(clip) > expected * RETRY_THRESHOLD:
            print(f"    ⚠ 길이 이상 ({len(clip)}ms, 예상 {expected}ms) — 재시도 {attempt+1}/{MAX_RETRIES}")
            if attempt < MAX_RETRIES:
                time.sleep(0.5)
                continue
        break

    return clip

# ── 스크립트 파서 ─────────────────────────────────────────────────
def parse_script(path: Path):
    """
    .txt 파일 → (세그먼트 리스트, 캐릭터→음성타입 dict)
    
    세그먼트 형식: 
        ("speech", (lang, text, char_or_None))
        ("break",  ms)
    
    헤더 인식:
        # voices: Sophie=bright-female Lucas=lively-male
    """
    segments = []
    char_map = {}

    voice_header_re = re.compile(r'#\s*voices?\s*:\s*(.+)', re.IGNORECASE)
    break_re        = re.compile(r'<break time="([^"]+)"/>')
    speech_re       = re.compile(r'\[(FR|KO)(?:-([^\]]+))?\]\s+(.+)')

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        # 헤더 코멘트에서 voices 매핑 추출
        if line.startswith("#"):
            m = voice_header_re.match(line)
            if m:
                for pair in m.group(1).split():
                    if "=" in pair:
                        char, vtype = pair.split("=", 1)
                        char_map[char.strip()] = vtype.strip()
            continue

        # 일반 코멘트
        if line[0] in "=-":
            continue

        # break 태그
        m = break_re.fullmatch(line)
        if m:
            segments.append(("break", BREAK_MS.get(m.group(1), 700)))
            continue

        # [FR-Char] / [FR] / [KO]
        m = speech_re.match(line)
        if m:
            lang, char, text = m.group(1), m.group(2), m.group(3).strip()
            segments.append(("speech", (lang, text, char)))

    return segments, char_map

def resolve_voice_id(char, char_map, script_name):
    """캐릭터명 → ElevenLabs voice_id 해석. 없으면 명확한 에러."""
    if not char:
        return None
    vtype = char_map.get(char)
    if not vtype:
        raise ValueError(
            f"[{script_name}] 캐릭터 '{char}' 음성 매핑 없음.\n"
            f"  → 스크립트 상단에 추가: # voices: {char}=bright-female"
        )
    voice_id = VOICE_REGISTRY.get(vtype)
    if not voice_id:
        raise ValueError(
            f"[{script_name}] 음성 타입 '{vtype}' 미등록.\n"
            f"  → VOICE_REGISTRY 사용 가능: {', '.join(VOICE_REGISTRY)}"
        )
    return voice_id

# ── 메인 생성기 ───────────────────────────────────────────────────
def generate(script_path: Path) -> Path:
    print(f"\n🎙 {script_path.name}")
    segments, char_map = parse_script(script_path)

    if char_map:
        print(f"   🎭 voices: {', '.join(f'{c}→{t}' for c, t in char_map.items())}")

    combined = AudioSegment.empty()
    speech_count = sum(1 for t, _ in segments if t == "speech")
    done = 0

    for seg_type, value in segments:
        if seg_type == "break":
            combined += AudioSegment.silent(duration=value)
        elif seg_type == "speech":
            lang, text, char = value
            voice_id = resolve_voice_id(char, char_map, script_path.name)
            tag = f"{lang}-{char}" if char else lang
            print(f"  [{tag}] {text[:60]}")
            combined += tts(text, lang, voice_id=voice_id)
            done += 1
            time.sleep(0.3)

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

#!/usr/bin/env python3
"""숫자 전용 generator — voice 다르게 (older-female) + model multilingual_v2."""
import os, sys, re, time, io, requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from pydub.effects import normalize
from dotenv import load_dotenv

load_dotenv()
API = os.environ["ELEVENLABS_API_KEY"]

VOICES = {
    "FR":     {"id": "1T2MOlQA0Xp3hNv1dBxp", "model": "eleven_multilingual_v2"},  # older-female
    "FR-V25": {"id": "1T2MOlQA0Xp3hNv1dBxp", "model": "eleven_turbo_v2_5", "language_code": "fr"},
    "KO":     {"id": "uyVNoMrnUku1dZyVEXwD", "model": "eleven_turbo_v2_5", "language_code": "ko"},
}
VS_FR  = {"stability": 0.95, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
VS_FR2 = {"stability": 0.85, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
VS_KO  = {"stability": 0.75, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
VS = {"FR": VS_FR, "FR-V25": VS_FR2, "KO": VS_KO}
SCRIPTS_DIR = Path("scripts"); OUTPUT_DIR = Path("audio")
BREAK_MS = {"0.5s":500,"0.7s":700,"1.0s":1000,"1.5s":1500,"2.0s":2000}

def trim_clip(audio):
    parts = detect_nonsilent(audio, min_silence_len=30, silence_thresh=-45)
    if not parts: return audio
    s = max(0, parts[0][0]-30); e = min(len(audio), parts[-1][1]+30)
    out = audio[s:e].fade_in(15).fade_out(15)
    if len(out) >= 2000: out = normalize(out, headroom=3.0)
    return out

def tts(text, lang):
    voice = VOICES[lang]
    body = {"text": text, "model_id": voice["model"], "voice_settings": VS[lang]}
    if "language_code" in voice: body["language_code"] = voice["language_code"]
    headers = {"xi-api-key": API, "Content-Type": "application/json"}
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice['id']}"
    r = requests.post(url, json=body, headers=headers, timeout=20)
    r.raise_for_status()
    return trim_clip(AudioSegment.from_mp3(io.BytesIO(r.content)))

def parse_script(path):
    segments = []
    break_re = re.compile(r'<break time="([^"]+)"/>')
    speech_re = re.compile(r'\[(FR|FR-V25|KO)\]\s+(.+)')
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"): continue
        m = break_re.fullmatch(line)
        if m:
            segments.append(("break", BREAK_MS.get(m.group(1), 700))); continue
        m = speech_re.match(line)
        if m:
            segments.append(("speech", (m.group(1), m.group(2).strip())))
    return segments

def generate(script_path):
    print(f"\n🎙 {script_path.name}")
    segments = parse_script(script_path)
    combined = AudioSegment.empty()
    for typ, val in segments:
        if typ == "break": combined += AudioSegment.silent(duration=val)
        else:
            lang, text = val
            print(f"  [{lang}] {text[:50]}")
            combined += tts(text, lang)
            time.sleep(0.3)
    out = OUTPUT_DIR / (script_path.stem + ".mp3")
    combined.export(out, format="mp3", bitrate="128k")
    print(f"  ✅ {out}  ({len(combined)/1000:.1f}s)")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    targets = [SCRIPTS_DIR / f"{a}.txt" for a in sys.argv[1:]] if len(sys.argv) > 1 else sorted(SCRIPTS_DIR.glob("pronon_nombre_*.txt"))
    for p in targets:
        if p.exists(): generate(p)
print("\n✨ 완료")

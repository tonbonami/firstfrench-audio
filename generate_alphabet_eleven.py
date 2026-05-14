#!/usr/bin/env python3
"""
generate_alphabet_eleven.py — 알파벳 전용 ElevenLabs warm-mother (자음 페이지와 동일 성우).
- model: eleven_multilingual_v2 (단음 letter에서도 또렷)
- voice: warm-mother (FR + KO 동일 ID)
- trim 매우 보수적 (silence_thresh=-70, min_silence_len=300)
"""
import os, sys, re, time, io, requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ["ELEVENLABS_API_KEY"]

# warm-mother voice ID (FR + KO 같은 화자)
VOICE = "uyVNoMrnUku1dZyVEXwD"
MODEL_FR = "eleven_multilingual_v2"
MODEL_KO = "eleven_turbo_v2_5"
VS_FR = {"stability":0.95,"similarity_boost":0.75,"style":0.0,"use_speaker_boost":True}
VS_KO = {"stability":0.75,"similarity_boost":0.75,"style":0.0,"use_speaker_boost":True}

SCRIPTS_DIR = Path("scripts"); OUTPUT_DIR = Path("audio")
BREAK_MS = {"0.5s":500,"0.7s":700,"0.8s":800,"1.0s":1000,"1.5s":1500,"2.0s":2000}

def gentle_trim(audio):
    """매우 보수적 trim: 단음 letter도 안전하게 보존."""
    if len(audio) < 800:  # 단음 letter는 trim skip
        return audio.fade_in(5).fade_out(15)
    parts = detect_nonsilent(audio, min_silence_len=300, silence_thresh=-70)
    if not parts: return audio
    s = max(0, parts[0][0]-150); e = min(len(audio), parts[-1][1]+150)
    return audio[s:e].fade_in(5).fade_out(15)

def tts(text, lang):
    if lang == "FR":
        body = {"text":text,"model_id":MODEL_FR,"language_code":"fr","voice_settings":VS_FR}
    else:
        body = {"text":text,"model_id":MODEL_KO,"language_code":"ko","voice_settings":VS_KO}
    headers = {"xi-api-key":KEY,"Content-Type":"application/json"}
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}", json=body, headers=headers, timeout=20)
    r.raise_for_status()
    return gentle_trim(AudioSegment.from_mp3(io.BytesIO(r.content)))

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
            tag = m.group(1)
            lang = "FR" if tag.startswith("FR") else "KO"
            segments.append(("speech", (lang, m.group(2).strip())))
    return segments

def generate(script_path):
    print(f"\n🎙 [ElevenLabs warm-mother] {script_path.name}")
    segments = parse_script(script_path)
    combined = AudioSegment.silent(duration=500)
    for typ, val in segments:
        if typ == "break": combined += AudioSegment.silent(duration=val)
        else:
            lang, text = val
            clip = tts(text, lang)
            print(f"  [{lang}] {text}  → {len(clip)}ms")
            combined += clip
            time.sleep(0.2)
    out = OUTPUT_DIR / (script_path.stem + ".mp3")
    combined.export(out, format="mp3", bitrate="128k")
    print(f"  ✅ {out}  ({len(combined)/1000:.1f}s)")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    targets = [SCRIPTS_DIR / f"{a}.txt" for a in sys.argv[1:]]
    for p in targets:
        if p.exists(): generate(p)
print("\n✨ 완료")

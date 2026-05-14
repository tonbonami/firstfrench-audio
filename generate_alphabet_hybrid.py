#!/usr/bin/env python3
"""
generate_alphabet_hybrid.py — 알파벳 전용. 단음 letter 잘림 방지.
- Google fr-FR-Chirp3-HD-Aoede (FR) + ElevenLabs warm-mother (KO)
- trim 매우 보수적: silence_thresh=-65, min_silence_len=200
- 단음 letter는 trim 안 함 (길이 1~2자)
"""
import os, sys, re, time, io, base64, requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from dotenv import load_dotenv

load_dotenv()
GOOGLE_KEY = os.environ["GOOGLE_TTS_API_KEY"]
ELEVEN_KEY = os.environ["ELEVENLABS_API_KEY"]

GOOGLE_FR_VOICE = {"languageCode":"fr-FR","name":"fr-FR-Chirp3-HD-Aoede","ssmlGender":"FEMALE"}
GOOGLE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
EL_KO_VOICE = "uyVNoMrnUku1dZyVEXwD"
EL_KO_MODEL = "eleven_turbo_v2_5"
EL_KO_VS = {"stability":0.75,"similarity_boost":0.75,"style":0.0,"use_speaker_boost":True}

SCRIPTS_DIR = Path("scripts"); OUTPUT_DIR = Path("audio")
BREAK_MS = {"0.5s":500,"0.7s":700,"0.8s":800,"1.0s":1000,"1.5s":1500,"2.0s":2000}

def gentle_trim(audio, is_short_letter=False):
    """단음 letter (1~3자) 는 trim 안 함. 더 긴 건 보수적 trim."""
    if is_short_letter:
        return audio.fade_in(5).fade_out(15)
    parts = detect_nonsilent(audio, min_silence_len=200, silence_thresh=-65)
    if not parts: return audio
    s = max(0, parts[0][0]-100); e = min(len(audio), parts[-1][1]+100)
    return audio[s:e].fade_in(5).fade_out(15)

def google_tts(text):
    payload = {
        "input":{"text":text},
        "voice":GOOGLE_FR_VOICE,
        "audioConfig":{"audioEncoding":"MP3","sampleRateHertz":24000}
    }
    r = requests.post(f"{GOOGLE_URL}?key={GOOGLE_KEY}", json=payload, timeout=20)
    r.raise_for_status()
    audio_bytes = base64.b64decode(r.json()["audioContent"])
    audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
    is_short = len(text.replace(".","").strip()) <= 4  # "a", "bé", "i", "elle" 등
    return gentle_trim(audio, is_short_letter=is_short)

def eleven_ko(text):
    body = {"text":text,"model_id":EL_KO_MODEL,"language_code":"ko","voice_settings":EL_KO_VS}
    headers = {"xi-api-key":ELEVEN_KEY,"Content-Type":"application/json"}
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{EL_KO_VOICE}", json=body, headers=headers, timeout=20)
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
    print(f"\n🎙 [Alphabet Hybrid] {script_path.name}")
    segments = parse_script(script_path)
    combined = AudioSegment.silent(duration=500)
    for typ, val in segments:
        if typ == "break": combined += AudioSegment.silent(duration=val)
        else:
            lang, text = val
            print(f"  [{lang}] {text}")
            clip = google_tts(text) if lang == "FR" else eleven_ko(text)
            print(f"    → {len(clip)}ms")
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

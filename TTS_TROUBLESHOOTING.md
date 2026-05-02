# ElevenLabs TTS 함정 & 해결책 모음

30 Days in Paris 음원 작업하면서 시행착오로 알아낸 노하우.
다른 프랑스어 교재 음원 작업할 때 같은 실수 반복하지 말 것.

---

# 🚨🚨🚨 최우선 절대 규칙 — 이 파일의 어떤 내용보다 먼저 적용 🚨🚨🚨

## ❌ 절대 금지: 발음 강좌 스크립트의 [KO] 인트로에 섹션 제목을 읽히지 말 것

발음 강좌 페이지(`pronon_*.txt`) 스크립트 작성 시:

```
❌ 절대 금지:
[KO] 악상떼귀.
[KO] 모음 a.
[KO] 자음 c — e/i/y 앞 [s] 소리.
[KO] il, ill — 이으.
[KO] 선택 리에종.
[KO] R 발음 연습.
```

**왜 금지**: 한국어 TTS가 알파벳·기호를 한 글자씩 읽어버림 ("지엔 니으", "이엘, 이엘엘"). 한국어 phrase여도 학습자가 페이지 H1을 이미 보고 있어서 음성 인트로가 불필요·산만.

```
✅ 올바른 방법:
스크립트 시작 = 즉시 [FR] 또는 [FR-V25] 첫 단어부터.
인트로 라인 자체를 작성하지 말 것.

[FR] la Corée.
<break time="0.7s"/>
[KO] 한국.
<break time="0.5s"/>
[FR] la Corée.
<break time="1.5s"/>
...
```

### 사전 확인 — 새 발음 스크립트 작성 시 매번 통과시킬 것

- [ ] 스크립트 첫 비-주석 라인이 `[FR]` 또는 `[FR-V25]`로 시작하는가?
- [ ] `[KO]` 라인이 단어 뜻 외에 섹션 제목·라벨을 읽지 않는가?
- [ ] `[KO]` 라인에 알파벳·기호·괄호 외국어가 없는가?

위 3가지 중 하나라도 어기면 → **generate_pronon.py 실행 금지**.

이 규칙은 nasal·voy1·voy3·cons·accent·liaison1·liaison2·liaison3·special·nombre 등 **모든 발음 스크립트에 적용**.

### 망친 사례 (4번째 늘어남 — 같은 실수 반복 금지)

| 페이지 | 망친 인트로 | 해결 |
|---|---|---|
| nasal (an/am/in...) | `[KO] an, am, en, em.` | 인트로 제거 |
| voy1 (a/e/i/il/o/u) | `[KO] a [아].` | 인트로 제거 |
| cons (c/g/gn/ch...) | `[KO] gn — 니으.` | 인트로 제거 |
| accent (악상떼귀...) | `[KO] 악상떼귀 (accent aigu).` | 인트로 제거 |

다음에 또 추가되면 SKILL과 트러블슈팅 모두 다시 검토할 것.

---

## 1. 첫 단어가 다른 언어로 새는 문제

**증상**: 프랑스어 `Un café`의 `Un`이 스페인어 "운"이나 이탈리아어 발음으로 나옴.

**원인**: ElevenLabs는 짧은 첫 단어만 보고 언어를 추측함. 짧으면 다국어 후보 중 잘못 고르기 쉬움.

**해결**: API 요청 body에 `language_code` 인자 명시.

```python
body = {
    "text": text,
    "model_id": "eleven_turbo_v2_5",   # turbo_v2_5 / v3 / flash_v2_5만 language_code 지원
    "language_code": "fr",              # ★ 핵심
    "voice_settings": VOICE_SETTINGS,
}
```

`language_code`는 turbo v2.5 이상에서만 작동. 옛날 모델 (`eleven_multilingual_v2` 등)은 안 받음 → 모델 자체를 turbo v2.5로 바꿔야 함.

---

## 2. /s/ 자음 늘어지는 elongation

**증상**: `En terrasse, s'il vous plaît` → 'sse,' 다음 's'il' 부분에서 /s/가 비정상적으로 길게 끌리거나 ASMR 같은 마찰음 잡음.

**원인**: 인접한 sibilant 자음 두 개를 ElevenLabs 모델이 한 음소처럼 합쳐 처리하면서 길이 분배가 망가짐.

**해결**: API 호출 직전에 그 경계에만 200ms `<break>` 자동 삽입. **교재 텍스트는 절대 안 건드림** (TTS 한계는 TTS에서 해결).

```python
import re
SIBILANT_BOUNDARY_RE = re.compile(
    r"(s+s?e?[,.])\s+(s['']\w)",   # 'sse,' / 'ss.' 다음 's'' 시작 단어
    re.IGNORECASE,
)

def preprocess_for_tts(text, voice_tag):
    if voice_tag != "FR":
        return text
    return SIBILANT_BOUNDARY_RE.sub(r'\1 <break time="0.2s"/> \2', text)
```

---

## 3. 클립 끝의 트레일링 잡음 ("쉬익~")

**증상**: 한 문장 끝에 짧은 마찰음/숨소리 잡음이 붙어서 합본할 때 부자연스러운 끊김 발생.

**해결**: pydub로 받자마자 시작/끝 무음 트림 + 양 끝 15ms 페이드.

```python
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
from io import BytesIO

def trim_clip(clip, threshold_db=-45):
    if len(clip) == 0: return clip
    start = detect_leading_silence(clip, silence_threshold=threshold_db, chunk_size=10)
    end = detect_leading_silence(clip.reverse(), silence_threshold=threshold_db, chunk_size=10)
    start = max(0, start - 30)   # 30ms 안전 마진 (말머리 잘림 방지)
    end = max(0, end - 30)
    trimmed = clip[start:len(clip) - end] if end > 0 else clip[start:]
    return trimmed.fade_in(15).fade_out(15)  # click 방지
```

`threshold_db`는 **-45가 적당**. -50은 너무 보수적(잡음 남음), -40은 너무 적극적(약한 발음 잘림).

---

## 4. 발음 변동성 (같은 문장이 호출마다 다르게)

**증상**: 같은 텍스트인데 어떤 호출은 정상, 어떤 호출은 자음 elongation 또는 발음 부정확.

**원인**: ElevenLabs는 비결정적. `stability` 값이 낮으면 매 호출 결과가 흔들림.

**해결**: VOICE_SETTINGS의 `stability`를 **0.75**로. 학습 콘텐츠는 표현력보다 일관성 우선.

```python
VOICE_SETTINGS = {
    "stability": 0.75,        # ★ 0.55에서 0.75로 올림 — 발음 안정화
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}
```

게다가 자동 재시도 메커니즘도 같이 두면 실패 케이스 자동 회복:
- 클립 길이가 예상치 × 1.8 초과 → 비정상으로 보고 재호출
- FR 예상치: 90ms × char 수
- KO 예상치: 280ms × syllable 수
- 최소 임계값 1200ms (짧은 클립이 이상치로 잘못 잡히는 거 방지)
- MAX_RETRIES = 2 (대부분 1번 재시도로 정상)

---

## 5. 한국어 짧은 클립이 자꾸 재시도 트리거

**증상**: "설탕" 같은 2음절 한국어가 자꾸 "비정상 길이" 경고 + 재시도 → 결과는 정상인데 시간 낭비.

**원인**: 한국어 임계값 130ms/char 적용 시 짧은 단어가 자꾸 임계값 초과로 오판됨.

**해결**: 한국어 임계값을 음절 단위 280ms로 상향 + 절대 최소값 1200ms.

```python
EXPECTED_MS_PER_CHAR = {"FR": 90, "KO": 280}
ANOMALY_RATIO = 1.8
MIN_ANOMALY_THRESHOLD_MS = 1200

def anomaly_threshold_ms(voice_tag, text):
    chars = sum(1 for c in text if c.isalpha() or c.isdigit())
    expected = chars * EXPECTED_MS_PER_CHAR.get(voice_tag, 90)
    return max(expected * ANOMALY_RATIO, MIN_ANOMALY_THRESHOLD_MS)
```

---

## 6. 스크립트 헤더가 음성에 새는 버그

**증상**: 첫 mp3에 "다음은 Day 4 카페 어휘입니다..." 같은 코멘트 텍스트가 그대로 음성으로 읽힘.

**원인**: 파서가 라인 단위로 처리할 때 코멘트 라인을 TTS로 보내버림.

**해결**: 코멘트 라인은 명시적으로 `#`, `=`, `-`로 시작하게 하고 파서에서 무시.

```python
LINE_RE = re.compile(r'^\[(FR|KO)\]\s*(.+)$')
BREAK_RE = re.compile(r'<break\s+time="([\d.]+)s?"\s*/?>')

def parse_script(path):
    segments = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            br = BREAK_RE.search(line)
            if br:
                segments.append(('silence', int(float(br.group(1)) * 1000)))
                continue
            m = LINE_RE.match(line)
            if m:
                segments.append(('tts', (m.group(1), m.group(2).strip())))
                continue
            if line.startswith('#') or line.startswith('=') or line.startswith('-'):
                continue
    return segments
```

---

## 7. 30 Days in Paris 보이스 ID (다른 교재도 통일 권장)

```python
VOICES = {
    "FR": {
        "id": "sANWqF1bCMzR6eyZbCGw",
        "language_code": "fr",
        "model": "eleven_turbo_v2_5",
    },
    "KO": {
        "id": "uyVNoMrnUku1dZyVEXwD",
        "language_code": "ko",
        "model": "eleven_turbo_v2_5",
    },
}
```

새 교재에서도 동일 보이스 사용하면 학습자가 두 책 사이를 오갈 때 음성 일관성 확보됨.

---

## 8. 호스팅 + 임베드

- **GitHub public repo + jsDelivr CDN**:
  `https://cdn.jsdelivr.net/gh/{user}/{repo}@main/{file}.mp3`
  - `raw.githubusercontent.com`은 다운로드 강제 → 브라우저 인라인 재생 안 됨. **반드시 jsDelivr.**
- **Notion 임베드**: enhanced markdown으로는 audio block 못 만듦. REST API 직접 호출:

```python
PATCH https://api.notion.com/v1/blocks/{page_id}/children
body: {
    "children": [{"type": "audio", "audio": {"type": "external", "external": {"url": URL}}}],
    "after": anchor_block_id
}
```

- 헤더(H1/H2)를 anchor 잡고 그 직후에 audio block 삽입하는 패턴 권장.

---

## 9. 환경 제약 (Cowork sandbox)

`api.elevenlabs.io`와 `api.notion.com`이 sandbox 프록시에서 차단됨.
**두 작업(TTS 생성 + Notion 임베드) 모두 사용자 로컬에서 직접 Python 실행 필요.**
스크립트는 sandbox에서 만들고, 실행은 로컬.

---

## 10. 최종 검증 체크리스트

음원 한 개 생성 후 들어보면서 확인:

- [ ] 프랑스어 첫 단어가 정확히 프랑스어로 발음됨 (스페인어/이탈리아어 변종 X)
- [ ] /s/ 인접 자음 사이가 자연스러움 (`sse, s'il` 류)
- [ ] 한국어 해석이 또박또박, 너무 늘어지거나 줄임 없음
- [ ] 클립 시작·끝에 잡음/숨소리 없음 (트림됨)
- [ ] 같은 텍스트를 두 번 호출해도 유사한 결과 (stability 0.75 효과)
- [ ] 코멘트 라인이 음성에 새지 않음

이 6가지 다 통과하면 일괄 생성 진입 가능.

---

## 부록 — 본 프로젝트 적용 상태

`generate_audio.py`에 이미 모두 반영됨:
- ✅ `language_code` (VOICES dict)
- ✅ `stability=0.75`
- ✅ `inject_sibilant_breaks()` 함수
- ✅ `trim_clip()` (-45 dB, 30ms 마진, 15ms fade)
- ✅ `EXPECTED_MS_PER_CHAR = {"FR": 90, "KO": 280}`
- ✅ `RETRY_THRESHOLD = 1.8`, `MIN_CLIP_MS = 1200`, `MAX_RETRIES = 2`
- ✅ `[FR]/[KO]` 마커 + `#/=/-` 코멘트 무시 파서

---

## 10. 짧은 단어(3~5자) + phoneme SSML tag = 무음/누락 (Turbo v2.5)

**증상**: `<phoneme alphabet="ipa" ph="...">word</phoneme>` 적용한 짧은 단어가 mp3에서 아예 안 들리거나 한국어 KO만 들림.

예시 — 안 됨:
- `<phoneme ph="mɛ">mais</phoneme>` → 무음
- `<phoneme ph="mais">maïs</phoneme>` → 무음
- `<phoneme ph="aiti">Haïti</phoneme>` → 무음

같은 phoneme tag가 긴 단어(7자+)에는 잘 작동: `gentille`, `oreille`, `genoux` 등.

**원인 추정**: Turbo v2.5가 짧은 텍스트 + SSML phoneme 조합에서 빈 응답 또는 노이즈만 반환. trim_clip이 그 무음을 다 깎아버림.

**해결**:
- 짧은 단어는 phoneme tag 쓰지 말 것.
- 발음 부정확하면 spelling 자체 변경(`maïs` → `ma-isse` 같은 phonetic) 또는 컨텍스트 추가(`le maïs`).
- 긴 단어(7자 이상)에서는 phoneme tag OK.

**규칙**: 
- ≤5자 단어: phoneme tag 금지
- 6자: 케이스별 테스트
- 7자+: phoneme tag 안전

---

## 11. 학습 콘텐츠는 두 모델 hybrid — multilingual_v2 + turbo_v2_5

**증상**: 한 모델로 모든 발음 단어 100% 정확하게 못 만듦. 모델별 정반대 약점.

| 단어 | turbo v2.5 | multilingual_v2 |
|---|---|---|
| `la classe` (final e) | ❌ 클라쎄 | ✅ 클라스 |
| `le reste` (final e) | ❌ 헤스떼 | ✅ 헤스뜨 |
| `la fille` (silent l) | ❌ 필 | ✅ 피으 |
| `il` (단음절 마지막 위치) | ✅ 차분 | ❌ 비명/강조 |
| `mille`/`ville` (-ille 예외) | ✅ 밀/빌 | ❌ 밀레/빌레 |
| `utile` (final e) | ✅ 우띨 | ❌ 우띨레 |
| `le futur` (breathing) | ✅ 깨끗 | ❌ 숨소리 |
| `œil` (톤) | ✅ 차분 | ❌ 표현적 |

**원인**:
- `eleven_multilingual_v2` — 자연 흐름 학습 → 단어 단위·짧은·마지막에서 emphasis/breathing 추가, final e를 schwa로 살림
- `eleven_turbo_v2_5` — 빠른 응답 위해 음운 분석 단순화 → 짧은 단어 final e 자주 살림

**해결 — Hybrid 워크플로우** (단어별로 더 좋은 모델 선택, voice는 동일 warm-mother 유지):

### 결정 규칙

| 단어 패턴 | 권장 모델 |
|---|---|
| 자음 시작 + final e (classe, reste, fille, semelle) | `multilingual_v2` |
| 단음절 (il, lit, qui) | `turbo_v2_5` |
| -ille 예외 (mille, ville, tranquille) | `turbo_v2_5` |
| 형용사 final e (utile, agréable) | `turbo_v2_5` |
| breathing 발생 단어 (le futur, le mur) | `turbo_v2_5` |
| 일반 명사 (la rue, le musée, la rose) | `multilingual_v2` |

### generate_pronon.py 구현

```python
VOICES = {
    "FR":     {"id": WARM_MOTHER, "model": "eleven_multilingual_v2"},
    "FR-V25": {"id": WARM_MOTHER, "model": "eleven_turbo_v2_5", "language_code": "fr"},
    "KO":     {"id": KO_VOICE,    "model": "eleven_turbo_v2_5", "language_code": "ko"},
}
VS_FR  = {"stability": 0.95, ...}  # multilingual_v2 — 모델이 자유분방하니 stability 높게
VS_FR2 = {"stability": 0.85, ...}  # turbo v2.5 — 차분한 모델이라 0.85로 충분
# language_code는 multilingual_v2 미지원 → 조건부 추가
```

### 스크립트 마커

```
[FR] la classe.       ← multilingual_v2 (기본)
[FR-V25] il.          ← turbo_v2_5 (단음절·-ille 예외·breathing)
```

### 새 단어 결정 플로우

```
새 단어 X
 → multilingual_v2로 시도 → 검수
 → 비명/breathing/-ille final e 살림? → [FR-V25]로 전환
 → V25에서도 실패? → 단어 자체 교체 (utile → la lune)
 → 교체 후에도 실패? → phoneme tag (≥7자만)
 → 다 실패? → 페이지에 "🤖 AI 음성, Forvo 참조" 콜아웃
```

### 절대 금지

- 같은 단어를 두 모델로 splice → 톤·음량 불일치
- 한 mp3에서 voice 바꾸기 (warm-mother로 통일, 모델만 다름)
- stability < 0.85 (학습용 일관성 깨짐)

### 과거 망친 사례

| 단어 | 망친 패턴 | 해결책 |
|---|---|---|
| `il` (i 섹션) | multilingual 비명 | `[FR-V25]` |
| `mille`/`ville` | multilingual final e | `[FR-V25]` |
| `œil` | multilingual 표현적 | `[FR-V25]` |
| `le futur` | multilingual breathing | `[FR-V25]` |
| `la classe`/`le reste` | turbo schwa 살림 | `[FR]` 기본 |

표가 늘어나면 같은 실수 반복. **새 페이지 작업 전 결정 플로우 통과 후에만 generate**.

---

## 12. [KO] 라인에 알파벳·기호 절대 금지 (한국어 TTS letter-spelling)

**증상**: 발음 강좌 스크립트의 `[KO] {label}.` 인트로에 알파벳·괄호·특수문자가 섞이면, 한국어 TTS가 한 글자씩 읽어버림.

| `[KO]` 입력 | TTS가 읽는 결과 |
|---|---|
| `[KO] gn — 니으.` | "지엔 니으" |
| `[KO] il, ill — 이으.` | "이엘, 이엘엘 — 이으" |
| `[KO] ch — sh 소리.` | "씨에이치 — 에스에이치 소리" |
| `[KO] c — e/i/y 앞 [s].` | "씨 — 이 슬래시 아이..." |
| `[KO] 악상떼귀 (accent aigu, ´).` | "...(악센트 아이구, ...)" |

**원인**: 한국어 TTS는 한국어 외 문자를 spell-out (한 글자씩 읽음).

**해결**:
1. **인트로 라인 자체를 빼기** — 발음 강좌는 페이지 H1·H3로 섹션 시각화되어 있음. TTS는 순수 발음 예시만 들려주면 됨.
2. 정 필요하면 **100% 한국어 phrase**로 (예: "지금부터 R 발음 연습 시작합니다", "단어 첫머리 R")
3. **프랑스어 라벨은 [FR] 또는 [FR-V25]로** — 한국어 라인에 섞지 말 것

### 사전 체크리스트

새 발음 스크립트 작성 시 반드시:
- [ ] `[KO]` 라인에 알파벳(a, e, c, gn, il...) 없는가?
- [ ] `[KO]` 라인에 기호(´, `, ˆ, ¨, ·, [], ...) 없는가?
- [ ] `[KO]` 라인에 괄호 안 외국어(accent aigu) 없는가?
- [ ] H1 직후에 audio 2개 이상 스택 안 하는가? → H3 또는 paragraph 라벨로 분산

### 과거 망친 사례

| 페이지 | 망친 패턴 | 해결 |
|---|---|---|
| pronon_nasal_*.txt | `[KO] an, am, en, em.` | 인트로 빼기 |
| pronon_voy1_*.txt | `[KO] a [아].`, `[KO] il, ill — 이으.` | 인트로 빼기 |
| pronon_cons_*.txt | `[KO] gn — 니으.`, `[KO] ch — sh 소리.` | 인트로 빼기 |
| pronon_accent_*.txt | `[KO] 악상떼귀 (accent aigu).` | 인트로 빼기 또는 한국어만 |


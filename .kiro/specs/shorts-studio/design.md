# Design — AI 숏폼 자동 수익화 스튜디오

## 개요

로컬에서 동작하는 Python 기반 반자동 숏폼 제작 스튜디오. 단일 FastAPI 애플리케이션이
대시보드(웹 UI)와 제작 파이프라인을 모두 호스팅한다. 데이터는 SQLite 파일 하나에 저장하고,
영상 조립은 FFmpeg에 위임한다. 모든 제작 단계는 **라이선스 게이트**와 **인간 승인 게이트**를
통과해야 한다.

### 설계 목표
- 초보자가 Windows에서 쉽게 실행(가상환경 + 단일 실행 명령).
- 유료 의존성 없이 MVP가 끝까지 동작(플랜 A: 전부 무료/로컬).
- 각 외부 서비스(TTS, LLM, 비디오 생성)는 **교체 가능한 프로바이더 인터페이스**로 추상화하여,
  무료 → 유료 전환을 코드 수정 없이 설정으로 가능하게 한다.

---

## 아키텍처

```
FastAPI 앱
├── web/                 대시보드 (HTML + 최소 JS, 한국어)
├── api/                 REST 엔드포인트 (소재, 영상, 검수, 아이디어, 비용)
├── pipeline/            제작 오케스트레이터 (단계별 스테이지)
│   ├── script.py        대본 생성 (LLM 프로바이더)
│   ├── tts.py           내레이션 (TTS 프로바이더)
│   ├── subtitles.py     자막/싱크 (Whisper 또는 TTS 타임스탬프)
│   ├── assets.py        소재 선택 (라이선스 게이트 적용)
│   ├── compose.py       FFmpeg 영상 조립 (9:16, 1080x1920, H.264)
│   └── metadata.py      제목/설명/썸네일문구/해시태그 생성
├── rights/              라이선스 판정 엔진 (CC 매트릭스 등)
├── qc/                  품질 검수 (FFmpeg 분석 + 규칙)
├── trends/              YouTube Data API 분석 (확인불가 처리)
├── publish/             업로드 패키지 / (조건부) API 업로드
├── providers/           LLM/TTS/Video 프로바이더 추상화
├── db/                  SQLite 모델 + 마이그레이션
└── config/              .env 로더, 설정
```

### 데이터 흐름 (한 편 제작)
```
주제 → [대본생성] → (독창성 점검) → [소재선택: 라이선스 게이트]
     → [TTS] → [자막/싱크] → [FFmpeg 조립: A·B 버전] → [메타데이터]
     → [품질검수] → (통과 시) 미리보기 → 사용자 승인 → 업로드 패키지/게시
```

---

## 컴포넌트와 인터페이스

### 1. 라이선스 판정 엔진 (`rights/`)
CC 라이선스 매트릭스를 코드로 보유한다.

| 라이선스 | 상업적 이용 | 수정/2차저작 |
|---|---|---|
| CC0 / Public Domain | 가능 | 가능 |
| CC BY | 가능(표기) | 가능 |
| CC BY-SA | 가능(표기, 동일조건) | 가능 |
| CC BY-NC | **불가** | 가능 |
| CC BY-ND | 가능(표기) | **불가(편집 불가)** |
| CC BY-NC-ND | **불가** | **불가** |
| Unknown/미확인 | **불가** | **불가** |

판정 함수 `evaluate(asset) -> Decision{usable, reasons[]}`:
- 상업적 이용 불가 → usable=False
- 2차저작(편집) 불가 → usable=False (영상 편집은 2차 저작이므로)
- 별도 권리(음악/초상권/상표) 중 하나라도 "미확인" → usable=False
- 만료일 경과 → usable=False
- 출처 표기 의무는 "표기 필요" 플래그로 기록하되, 표기만으로 usable=True가 되지 않음

### 2. 프로바이더 추상화 (`providers/`)
```python
class LLMProvider(Protocol):
    def generate_script(self, topic, duration_profile) -> Script: ...

class TTSProvider(Protocol):
    def synthesize(self, text, voice) -> AudioFile: ...   # wav/mp3 + 단어 타임스탬프(가능 시)
```
MVP 기본 구현: 로컬/무료 프로바이더. 설정으로 유료 API 프로바이더로 교체.
키가 없으면 해당 프로바이더는 비활성화되고 UI에 "설정 필요"로 표시.

### 3. 영상 조립 (`pipeline/compose.py`)
FFmpeg 명령 구성:
- 스케일/패드로 1080×1920 보장, `-r 30`, `-c:v libx264 -pix_fmt yuv420p`
- 이미지 소재는 Ken Burns(zoompan)로 동적 효과
- 자막은 `subtitles`(ASS/SRT) 필터로 번인(가독성 위해 외곽선/하단 배치)
- 내레이션 + 배경음악 믹싱(배경음 ducking), 오디오 `-c:a aac`
- A(25~45초)와 B(65~90초)는 **서로 다른 대본/장면 리스트**로 각각 조립

### 4. 품질 검수 (`qc/`)
- 검은 화면: FFmpeg `blackdetect`
- 볼륨: `volumedetect` / loudnorm 기준
- 길이/해상도: `ffprobe`
- 싱크: 자막 타임스탬프 vs 오디오 길이 비교
- 증빙 존재: 사용된 모든 소재가 라이선스 게이트를 통과했는지 재확인
- 독창성: 대본과 소스 텍스트의 n-gram 중복률 임계값 점검
- 결과: pass/warn/fail + 사유 목록. fail 1개라도 있으면 "보류".

### 5. 트렌드 분석 (`trends/`)
- YouTube Data API: `search`, `videos`(statistics, contentDetails) 호출.
- 획득: 제목, 조회수, 좋아요, 댓글수, 길이, 태그.
- **미제공 지표(완료율/3초이탈 등)는 응답 객체에 `"확인 불가"` 상수로 채움.**
- 아이디어 생성: 수집된 주제 키워드 + 흥행 패턴(길이대, 질문형 제목 등)으로 LLM에 10개 요청.
  타인 대본 복제 금지 프롬프트 가드 포함.

### 6. 업로드 (`publish/`)
- 자격 판정: 플랫폼별 자격/토큰 존재 여부 확인.
- 토큰 없음 → `package/` 에 `{video.mp4, metadata.json, caption.txt, thumbnail_text.txt}` 생성.
- 토큰 있고 사용자가 승인 → API 업로드(초기엔 승인 영상만). 성공/실패/중복 기록.

---

## 데이터 모델 (SQLite)

```
assets(id, type, source_url, author, license, commercial_use, editable,
       attribution_required, proof_ref, expires_at, music_rights, person_rights,
       trademark_rights, usable, reasons, created_at)

ideas(id, topic, source_signals, status, created_at)

videos(id, idea_id, title, description, hashtags, thumbnail_text,
       version(A|B), status(draft|composed|qc_pending|held|approved|published),
       file_path, duration, resolution, created_at)

video_assets(video_id, asset_id)             -- 사용된 소재 추적(증빙)

qc_results(id, video_id, check_name, result(pass|warn|fail), detail, created_at)

uploads(id, video_id, platform, status(packaged|uploaded|failed),
        external_id, scheduled_at, created_at)   -- 중복 방지 unique(video_id, platform)

costs(id, video_id, item, provider, amount, currency, created_at)

performance(id, video_id, platform, views, likes, comments, is_estimate, fetched_at)
```

---

## 에러 처리
- 외부 서비스 실패: 재시도(지수 백오프) 후 해당 영상 상태를 `held`로 전환하고 사유 기록.
- FFmpeg 실패: stderr를 로그/DB에 저장, 영상 `held`.
- 라이선스 게이트 실패: 제작 시작 전 차단, 부족 소재 목록 반환(요구사항 3.8).
- 키 미설정: 기능 비활성 + UI 안내(가짜 성공 금지).

## 보안
- `.env`에서 키 로드, `.gitignore`에 `.env` 포함. 저장소엔 `.env.example`만.
- DB의 proof_ref는 파일 경로/URL만 저장(비밀 아님).

## 테스트 전략
- 단위: 라이선스 판정 매트릭스, CC 종류별 usable 판정, 만료 처리.
- 단위: QC 규칙(모의 ffprobe/blackdetect 출력으로 pass/fail).
- 통합: 더미 소재 + 로컬 TTS로 짧은 샘플 영상 1편을 실제 조립하여 ffprobe로 9:16/길이 검증.
- 수동 확인: 대시보드 미리보기에서 영상 재생.

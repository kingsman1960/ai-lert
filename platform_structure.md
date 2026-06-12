# GeoAX 플랫폼 전체 구조

## 🏛️ 1. 프로젝트 개요 (Project Overview)

`Sicher-BW`는 독일 바덴뷔르템베르크(Baden-Württemberg) 주 하일브론(Heilbronn) 지역**을 중심으로 한 시민 대상 **홍수 및 자연재해 위험 인식 플랫폼**입니다.


핵심 목표는 **공공 데이터(NINA, PEGELONLINE 등)를 시민이 한눈에 이해할 수 있는 "개인화된 위험 가이드"로 변환**하는 것이며, 하드코딩된 예측 모델 대신 **결정론적 규칙(Deterministic Rules)** + **공식 데이터**를 결합하여 신뢰성 있는 정보를 제공합니다.

---

## 🧱 2. 최상위 아키텍처 (Top-Level Architecture)

```
GeoAX/
│
├── 🖥️  frontend/            (React + TypeScript + Vite 사용자 인터페이스)
│   ├── src/
│   ├── public/
│   ├── vite.config.ts
│   └── vite.wms-test.config.ts
│
├── ⚙️  backend/             (FastAPI 집계 및 위험도 산출 서버)
│   ├── app/
│   │   ├── api/routes/      (라우터 계층)
│   │   ├── schemas/         (Pydantic 데이터 모델)
│   │   └── services/        (외부 API 연동 및 비즈니스 로직)
│   ├── tests/               (단위 테스트 및 통합 테스트)
│   └── requirements.txt
│
├── 📂  Dataset/             (하일브론 정사영상 DOP 타일 및 샘플 데이터)
│   ├── heilbronn_dop_native_tiles/
│   ├── heilbronn_stadt_dop_native_tiles/
│   └── lgl_bw_dop_samples/
│
├── 📄  docs/                 (프로젝트 문서)
│   ├── heilbronn-citizen-risk-guide-prd.md   (제품 요구사항 정의서)
│   └── geoai-program-requirements.md         (GeoAI 프로그램 요구사항)
│
├── ⚙️  환경 설정 및 문서
│   ├── README.md            (메인 프로젝트 README)
│   ├── dev_manual.md        (팀원용 한국어 개발 가이드)
│   ├── .env.example         (환경변수 템플릿)
│   └── logo.png
│
└── 🛠️  기타
    ├── .ai/mcp/             (AI 모델 컨텍스트 프로토콜 설정)
    ├── .idea/               (IDE 설정)
    └── GeoAX.iml             (IntelliJ 모듈 설정)
```


---

## 🔄 3. 데이터 흐름 (Data Flow)

### 핵심 흐름: `사용자 위치 입력 → 위험도 산출`

```
[사용자] → 위치 입력 (주소/좌표)
    │
    ▼
[Frontend] (React + Leaflet Map)
    │
    │  POST /risk-assessment
    ▼
[Backend FastAPI] (Aggregator)
    │
    ├──► [NINA API]        → 지역 재난 경보 수집
    ├──► [PEGELONLINE API]  → 인근 수위 관측소 데이터 수집
    ├──► [Geocoding]        → 주소를 좌표로 변환
    ├──► [Air Quality API]  → 대기질 컨텍스트 수집
    ├──► [LUBW/LGRB WMS]    → 공간 위험 데이터(지오메트리)
    │
    ▼
[Risk Scoring Engine] (결정론적 점수 산출)
    │
    ▼
[응답 객체 구성]
    - location, warnings, water_context, risk, active_scenario, safe_places
    │
    ▼
[Frontend] → 결과 시각화 (지도 + 텍스트)
```


---

## 🖥️ 4. Frontend (사용자 인터페이스)

| 항목 | 기술 스택 | 역할 |
|:---|:---|:---|
| **프레임워크** | React 19.2 + TypeScript 6.0 | UI 컴포넌트 및 타입 안정성 |
| **빌드 도구** | Vite 8.0 | 빠른 HMR 및 개발 서버 |
| **지도 렌더링** | Leaflet 1.9 + react-leaflet 5.0 | 대화형 지도 시각화 |
| **공간 데이터** | WMS Tile Layer (LUBW, LGRB, 연방 수로청) | 위험 구역 오버레이 |
| **스타일링** | CSS (모듈식) | 카드/레이아웃 디자인 |
| **린팅** | ESLint 10.0 + typescript-eslint | 코드 품질 관리 |

### Frontend의 듀얼 모드 구조
- **메인 앱** (`http://localhost:5173`): 시민용 결과 요약 인터페이스
- **WMS 테스트 빌드** (`http://localhost:5174`): LUBW/LGRB 지오메트리 레이어 검증용 샌드박스

---

## ⚙️ 5. Backend (서버 계층)

### 5.1 아키텍처 레이어

```
[Routes]  ──►  [Services]  ──►  [Schemas]  ──►  [External APIs]
   │              │                │
   │              ▼                │
   │         [Scoring Engine]      │
   │              │                │
   └──────────────┴────────────────┘
```


### 5.2 핵심 서비스 모듈 (서비스 디렉토리 구조)

| 서비스 모듈 | 역할 | 대응하는 테스트 파일 |
|:---|:---|:---|
| `geocoding.py` | 주소↔좌표 변환 (Nominatim 활용) | `test_geocoding.py` |
| `nina.py` | NINA 경보 데이터 fetch | `test_api.py` (mock) |
| `pegel.py` | PEGELONLINE 수위 데이터 (HEILBRONN SCHLEUSE UP 우선 선택) | `test_pegel.py` |
| `lubw_flood.py` | LUBW 홍수 위험 폴리곤 분석 (Point-in-Polygon, 최근접점 투영) | `test_lubw_flood.py` |
| `scoring.py` | 결정론적 위험 점수 및 티어 산출 | `test_scoring.py` |
| `scenario_parser.py` | 데모 시나리오 토큰 파싱 (`[demo:flood]` 등) | `test_scenarios.py` |
| `scenario_places.py` | 하일브론 시나리오별 안전 장소 데이터 | `test_scenarios.py` |

### 5.3 주요 엔드포인트

**`POST /risk-assessment`**

요청:
```json
{
  "query": "Heilbronn, Germany",
  "include_weather": false
}
```


응답 핵심 필드:
- `location`: 지오코딩된 위치 정보
- `warnings`: NINA 경보 목록
- `water_context`: 가장 가까운 수위 관측소 + 트렌드
- `risk`: `{ tier: "Low|Medium|High", score: 0-100 }`
- `active_scenario`: 데모 시나리오 정보
- `safe_places`: 안전 대피 장소

### 5.4 외부 API 통합 (`.env` 기반)
- `GEOCODING_BASE_URL`: Nominatim
- `NINA_BASE_URL`: warnung.bund.de
- `PEGELONLINE_BASE_URL`: pegelonline.wsv.de
- `BACKEND_CORS_ORIGINS`: 개발용 localhost:5173/5174

---

## 📊 6. Dataset (공간 데이터 자산)

`Dataset/` 폴더는 실제 테스트/시연에 활용되는 **하일브론 지역 정사영상 타일**을 보관합니다:

| 디렉토리 | 내용 |
|:---|:---|
| `heilbronn_dop_native_tiles/` | 16x23 격자 (368장), ~0.2m/px 해상도, EPSG:4326, WMS 1.1.1 |
| `heilbronn_stadt_dop_native_tiles/` | 하일브론 시 단위 별도 타일 |
| `lgl_bw_dop_samples/` | LGL-BW(지자체 측량국) 샘플 |
| `besucher_in_den_oeffentlichen_schwimmbaedern_stuttgarts_seit_1980.csv` | 참고용 보조 데이터 |

**기술 메타데이터 (manifest.json)**
- 좌표계: EPSG:4326 (WGS84)
- 바운딩 박스: 9.0444°E ~ 9.3021°E, 49.0929°N ~ 49.2099°N
- 전체 해상도: 93,793 × 65,138 픽셀
- 그리드: 16행 × 23열

---

## 🧪 7. 테스트 전략

`backend/tests/` 디렉토리에 6개의 테스트 모듈이 존재하며, 외부 API 실패 시에도 견디는지(Fallbacks) 검증합니다:

- `test_api.py`: 핵심 3가지 시나리오 (외부 API 장애 / 시뮬레이션 / 직접 좌표)
- `test_geocoding.py`: Baden-Württemberg 주 지역 인식
- `test_lubw_flood.py`: Point-in-Polygon 및 폴리곤 탈출 지점 계산
- `test_pegel.py`: HEILBRONN SCHLEUSE UP 관측소 우선 선택
- `test_scenarios.py`: 데모 토큰 파싱 + 하일브론 랜드마크 병합
- `test_scoring.py`: Low/High 티어 분류 정확도

---

## 📚 8. 문서화 계층

| 문서 | 대상 | 내용 |
|:---|:---|:---|
| `README.md` (루트) | 일반 방문자/심사위원 | 프로젝트 소개 및 로컬 셋업 |
| `frontend/README.md` | React 개발자 | Vite + React 스택 기본 가이드 |
| `docs/heilbronn-citizen-risk-guide-prd.md` | 제품/기획 | 32개 섹션의 상세 PRD |
| `docs/geoai-program-requirements.md` | 아키텍트/전략 | GeoAI 표준/연동 거버넌스 |
| `dev_manual.md` | 한국어 팀원 | 데이터 소스 힌트 + 구현 방향 (공개 범위 외 노하우 제외) |

---

## 🔐 9. 개발 워크플로우 및 거버넌스

- **버전 관리**: Git (`.gitattributes` LF 정규화)
- **Python 환경**: Python 3.13 (IntelliJ SDK), `pip` + `requirements.txt`
- **Node 환경**: npm + Vite 워크플로우, `package.json`의 스크립트로 `dev`, `dev:wms-test`, `build`, `lint`, `preview` 관리
- **테스트**: `pytest` (백엔드), TypeScript 컴파일러 (프론트엔드)
- **데이터 거버넌스**: NINA·PEGELONLINE 등 **공식 데이터 우선 정책** + **공식 정보와 생성 설명 구분(TS-2)** + **시민 인식/대비용 disclaimer 의무화(TS-5)**

---

## 🎯 10. 설계 철학 요약

| 원칙 | 구현 |
|:---|:---|
| **공식 데이터 우선** | NINA, PEGELONLINE 등 권위 있는 소스 사용 |
| **결정론적 규칙 엔진** | LLM 의존 없이 해석 가능한 점수 산출 |
| **공간-시간 컨텍스트** | WMS 기반 지오메트리 + 수위 트렌드 결합 |
| **Graceful Degradation** | 외부 API 실패 시에도 200 응답 + 부분 데이터 제공 |
| **시뮬레이션 데모 모드** | `[demo:flood]`, `[demo:heat]` 토큰으로 시연 시나리오 주입 |
| **로컬 신뢰성** | 하일브론 도시/시 단위 데이터셋 + 랜드마크 (Wartberg, Berufsfeuerwehr 등) 하드코딩 |
| **표준 지향성** | OGC API, WMS 1.1.1/1.3.0 동시 지원 |
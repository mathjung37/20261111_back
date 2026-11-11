# Tomorrow Desk API

업무 목록을 OpenAI Agent와 함께 내일의 계획으로 정리하고 Firebase Firestore에 저장하는 FastAPI 백엔드입니다.

## 주요 흐름

1. `POST /work-sessions`가 업무 목록을 받고 OpenAI 대화 Agent 세션을 생성합니다.
2. Agent의 OpenAI-hosted 환경에 `OPENAI_SKILL_ID`를 `skill_reference`로 연결합니다.
3. `POST /work-sessions/{sessionId}/messages`가 같은 Agent 세션에서 대화를 이어갑니다.
4. `POST /work-sessions/{sessionId}/finalize`가 업무 정리 Agent를 호출하고 최종 계획을 Firestore에 저장합니다.

## 로컬 실행

Python 3.11 이상이 필요합니다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

로컬에서 실제 Firestore 대신 메모리 저장소를 사용하려면 `.env`의 `STORAGE_BACKEND`를 `memory`로 바꿉니다. 메모리 데이터는 프로세스를 종료하면 사라집니다.

## 필수 환경 변수

- `OPENAI_API_KEY`: OpenAI 프로젝트 API 키
- `OPENAI_MODEL`: 사용할 모델. 기본값은 `gpt-5.6-sol`
- `OPENAI_REASONING_EFFORT`: 추론 강도. 기본값은 `medium`
- `OPENAI_SKILL_ID`: 사용할 업로드 Skill ID
- `FIREBASE_PROJECT_ID`: Firebase 프로젝트 설정에 표시되는 프로젝트 ID
- `FIRESTORE_DATABASE_ID`: Firestore 데이터베이스 ID. 기본값은 `(default)`
- `FIRESTORE_COLLECTION`: 업무 세션을 저장할 컬렉션. 기본값은 `work_sessions`
- `GOOGLE_APPLICATION_CREDENTIALS`: 로컬 서비스 계정 JSON 경로. Google Cloud에서는 Application Default Credentials를 권장합니다.
- `ALLOWED_ORIGINS`: 쉼표로 구분한 Netlify 및 로컬 프론트엔드 주소

기본 Skill ID는 다음 값으로 설정되어 있습니다.

```text
skill_6af440f78bb08191bcd8bc8691b228bb05903870db4bc490
```

API 키와 서비스 계정 파일은 저장소에 커밋하지 않습니다.

## 테스트

```powershell
pytest
```

테스트는 외부 OpenAI API와 Firestore를 호출하지 않고 가짜 Agent 및 메모리 저장소를 사용합니다.

## Google Cloud 배포

`Dockerfile`은 Cloud Run에서 바로 사용할 수 있도록 `PORT` 환경 변수를 사용합니다. 프로덕션 환경에서는 Secret Manager로 `OPENAI_API_KEY`를 주입하고, Cloud Run 서비스 계정에 Firestore 접근 권한을 부여합니다.

Cloud Run에서는 `FIREBASE_PROJECT_ID`에 Firebase 프로젝트 ID를 설정합니다. Firebase Admin SDK는 Cloud Run 서비스 계정의 Application Default Credentials를 사용하며, `FIRESTORE_DATABASE_ID`로 지정한 데이터베이스에 연결합니다.


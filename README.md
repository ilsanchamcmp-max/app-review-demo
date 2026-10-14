# App Review Demo (독립 프로젝트)

이 폴더는 `daily-monitoring`과 **완전히 분리된** Meta App Review용 데모입니다.
코드/설정 어떤 것도 공유하지 않습니다 (`daily-monitoring`의 어떤 파일도 이 프로젝트에서 참조하지 않음).

## 1. 리다이렉트 URI - 로컬 `http://localhost:5000/...`은 사용 불가 (문서 확인 결과)

요청하신 대로 Meta 공식 문서를 확인했습니다. 결론부터:

- **Threads API는 `localhost`를 리다이렉트 URI 호스트로 아예 지원하지 않습니다.** Meta의 공식 Threads 샘플 앱 문서(fbsamples/threads_api)에 "Threads apps do not support redirect URLs using localhost"라고 명시되어 있습니다.
- **Facebook Login(= Instagram 해시태그 검색 경로)도 HTTPS가 필수**입니다. `http://localhost:5000/...`처럼 평문 HTTP는 두 경로 모두 등록 자체가 거부됩니다.
- 즉 **`http://localhost:5000/callback/threads`, `http://localhost:5000/callback/facebook` 두 URI 모두 Meta 콘솔에 그대로 등록할 수 없습니다.**

Meta가 공식적으로 제시하는 대안은 다음 셋 중 하나입니다:
1. **HTTPS 터널(예: ngrok)로 localhost를 노출** - 가장 간단, 이 프로젝트는 이 방식을 기본으로 가정하고 만들었습니다.
2. hosts 파일에 가상 도메인(예: `app-review-demo.local`)을 127.0.0.1로 매핑 + `mkcert` 등으로 자체 서명 인증서 발급 후 로컬 HTTPS 서버 실행
3. 실제 배포된 HTTPS 서버(예: 사내 테스트 서버)

코드 자체는 Flask 앱이 내부적으로 계속 `localhost:5000`에서 동작하고(포트는 자유롭게 바꿔도 됨), **Meta에 등록하는 리다이렉트 URI만 `demo_config.json`에서 별도로 설정**하도록 만들어져 있습니다. 어떤 방식을 택하든 코드 수정 없이 설정값만 바꾸면 됩니다.

## 2. 실행 방법 (ngrok 사용 기준)

```bash
cd app-review-demo
python -m pip install -r requirements.txt
```

1. [ngrok](https://ngrok.com/download)을 설치하고 `ngrok http 5000`을 실행 → `https://xxxx.ngrok-free.app` 같은 주소가 발급됩니다.
2. `demo_config.json`의 `threads.redirect_uri`, `facebook.redirect_uri`를 각각
   - `https://xxxx.ngrok-free.app/callback/threads`
   - `https://xxxx.ngrok-free.app/callback/facebook`
   로 채워 넣습니다.
3. Meta 개발자 콘솔(아래 3번 참고)의 Valid OAuth Redirect URIs에도 **정확히 같은 두 URL**을 등록합니다.
4. Flask 서버 실행:
   ```bash
   flask --app app run --port 5000
   ```
5. 브라우저로 **ngrok 주소**(`https://xxxx.ngrok-free.app/`)에 접속해서 데모를 진행합니다. (`localhost:5000`으로 직접 접속하면 로그인 버튼을 눌렀을 때 Meta가 리다이렉트를 거부합니다 - 반드시 ngrok 주소로 접속하세요.)

## 3. `demo_config.json`에 채워야 할 값 - Meta 개발자 콘솔에서 찾는 법

[developers.facebook.com/apps](https://developers.facebook.com/apps) 에서 앱 선택 후:

| 필드 | 찾는 위치 |
|---|---|
| `flask_secret_key` | Meta와 무관한 값. 아무 랜덤 문자열이나 넣으면 됨(예: `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `threads.app_id` | 앱 대시보드 좌측 "Threads" 제품 추가 후 "App settings" 상단의 App ID (Meta App ID와 동일할 수 있음) |
| `threads.app_secret` | 같은 화면의 App Secret ("표시" 클릭 후 확인) |
| `threads.redirect_uri` | 좌측 메뉴 "Threads" → "API Setup" → "Redirect Callback URLs"에 등록한 값과 동일하게 입력 |
| `facebook.app_id` | 앱 대시보드 상단 "App ID" |
| `facebook.app_secret` | 좌측 메뉴 "App settings" → "Basic" → "App Secret" |
| `facebook.redirect_uri` | 좌측 메뉴 "Facebook Login" → "Settings" → "Valid OAuth Redirect URIs"에 등록한 값과 동일하게 입력 |

권한(scope)은 `demo_config.json`에 기본값을 넣어뒀지만, 실제 App Review에서 신청 중인 권한 이름과 정확히 일치하는지 확인 후 필요하면 수정하세요.

**`facebook.scope`는 신청한 6개 권한 중 `scope` 파라미터로 요청 가능한 것만 넣습니다**
(`instagram_basic`, `pages_show_list`, `pages_read_engagement`). `threads_basic`,
`threads_keyword_search`는 `threads.scope`에 별도로 들어갑니다.

**"Instagram Public Content Access"는 OAuth `scope`에 넣지 않습니다.** 이건 Meta
App Review에서 별도로 승인받는 Feature이며, 승인만 되어 있으면 `ig_hashtag_search`
호출 시 Meta가 서버 쪽에서 자동으로 확인합니다. 코드/설정 어디에도 이 이름을
문자열로 넣을 필요가 없습니다.
(참고: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/hashtag-search)

## 4. 데모 흐름 요약

- `/threads`: "Threads로 로그인" → `threads.net/oauth/authorize` 리다이렉트 → 콜백 처리 후 검색창 표시 → `graph.threads.net/v1.0/keyword_search` 호출 → 카드 UI로 결과 표시(0건이면 "검색 결과가 없습니다" 표시)
- `/instagram`: "Facebook으로 로그인" → `facebook.com/.../dialog/oauth` 리다이렉트 → 콜백 처리 후 검색창 표시 → 연결된 Instagram 비즈니스 계정을 자동 조회 → `ig_hashtag_search` + `top_media` 호출 → 카드 UI로 결과 표시

Graph API Explorer의 원시 JSON이 아니라, 실제 화면(로그인 버튼 → 검색창 → 카드형 결과)을 그대로 녹화해서 심사에 제출하면 됩니다.

## 5. 참고한 공식 문서

- Threads API Keyword Search: https://developers.facebook.com/docs/threads/keyword-search/
- Instagram Hashtag Search: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/hashtag-search
- Facebook Login Security(리다이렉트 URI 규칙): https://developers.facebook.com/documentation/facebook-login/security
- Threads 샘플 앱(로컬 개발 시 localhost 미지원 및 대안): https://github.com/fbsamples/threads_api

## 6. Render.com 배포 (무료 Web Service)

### 환경변수 목록 (Render → Environment 탭에 입력)

코드는 환경변수가 있으면 `demo_config.json`보다 **우선**하고, 배포 환경에서는 `demo_config.json` 자체가 필요 없습니다 (`.gitignore`로 GitHub에서도 제외됨).

| 환경변수 | 넣을 값 (= demo_config.json의 어떤 값) |
|---|---|
| `FLASK_SECRET_KEY` | `flask_secret_key`. render.yaml 사용 시 자동 생성됨. 수동이면 `python -c "import secrets; print(secrets.token_hex(32))"` 결과 |
| `THREADS_APP_ID` | `threads.app_id` |
| `THREADS_APP_SECRET` | `threads.app_secret` |
| `THREADS_REDIRECT_URI` | `https://앱이름.onrender.com/callback/threads` (ngrok 주소 아님) |
| `THREADS_SCOPE` | `threads_basic,threads_keyword_search` |
| `FACEBOOK_APP_ID` | `facebook.app_id` |
| `FACEBOOK_APP_SECRET` | `facebook.app_secret` |
| `FACEBOOK_REDIRECT_URI` | `https://앱이름.onrender.com/callback/facebook` (ngrok 주소 아님) |
| `FACEBOOK_SCOPE` | `instagram_basic,pages_show_list,pages_read_engagement,business_management` |
| `FACEBOOK_PAGE_ID` | `1266008319925722` (me/accounts가 비어 있을 때만 쓰는 폴백, 선택) |

### 중요: 리다이렉트 URI를 반드시 Render 주소로 바꿔야 함

배포하면 주소가 ngrok이 아니라 Render가 주는 고정 주소(`https://앱이름.onrender.com`)가 됩니다. Meta 콘솔에 등록된 URI가 ngrok 주소 그대로면 로그인이 거부됩니다.
- Threads: 앱 → Threads → API Setup → Redirect Callback URLs
- Facebook: Facebook Login → Settings → Valid OAuth Redirect URIs
- 위 두 곳과 Render 환경변수 `*_REDIRECT_URI`를 **글자 하나까지 동일하게** 맞출 것.

### 배포 순서

1. GitHub 계정 생성 → New repository (예: `app-review-demo`, Private 권장).
2. 이 폴더에서 (`demo_config.json`은 `.gitignore`에 있으니 올라가지 않음):
   ```bash
   git init
   git add .
   git status   # demo_config.json 이 목록에 없는지 반드시 확인
   git commit -m "App Review demo"
   git branch -M main
   git remote add origin https://github.com/내계정/app-review-demo.git
   git push -u origin main
   ```
3. Render 계정 생성(GitHub 연동 로그인) → New + → Blueprint(`render.yaml` 자동 인식) 또는 Web Service 선택 후 저장소 연결.
   - Web Service로 수동 생성 시: Runtime `Python`, Build `pip install -r requirements.txt`, Start `gunicorn app:app --workers 1 --threads 4 --timeout 60`, Plan `Free`.
4. Environment 탭에서 위 표의 환경변수를 입력 (`sync: false` 항목은 값을 직접 입력해야 함).
5. 배포 완료 후 발급된 `https://앱이름.onrender.com` 주소를 확인하고, 위 "리다이렉트 URI" 두 곳(Meta 콘솔 + Render 환경변수)을 이 주소로 수정 → Render에서 재배포.
6. `https://앱이름.onrender.com/` 접속해서 두 흐름 테스트 후 화면 녹화.

주의: 무료 플랜은 일정 시간 접속이 없으면 잠들어 첫 접속이 30~60초 느립니다. 녹화 전에 미리 한 번 접속해 깨워두세요. 워커를 1개로 둔 것은 세션 상태(OAuth state)를 안정적으로 유지하기 위함입니다.

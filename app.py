# -*- coding: utf-8 -*-
"""
Meta App Review 데모용 최소 웹앱.

daily-monitoring 폴더와는 완전히 분리된 독립 프로젝트입니다. 이 파일은
daily-monitoring 안의 그 어떤 파일도 import/read/write 하지 않습니다.
설정은 이 폴더 안의 demo_config.json(로컬) 또는 환경변수(배포)에서만 읽습니다.

두 개의 엔드투엔드 데모 흐름:
  1. Threads: Threads OAuth 로그인 -> 검색창 -> threads_keyword_search API 호출
     -> 결과를 카드 UI로 표시
  2. Instagram: Facebook Login OAuth -> 검색창 -> (IG 비즈니스 계정 해석 후)
     ig_hashtag_search API 호출 -> 결과를 카드 UI로 표시

실행:
  python -m pip install -r requirements.txt
  flask --app app run --port 5000
(자세한 안내는 이 폴더의 README.md 참고)
"""
import json
import os
import secrets

import requests
from flask import Flask, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "demo_config.json")

THREADS_AUTHORIZE_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_GRAPH_BASE = "https://graph.threads.net/v1.0"
THREADS_KEYWORD_SEARCH_URL = f"{THREADS_GRAPH_BASE}/keyword_search"

FACEBOOK_API_VERSION = "v21.0"
FACEBOOK_AUTHORIZE_URL = f"https://www.facebook.com/{FACEBOOK_API_VERSION}/dialog/oauth"
FACEBOOK_TOKEN_URL = f"https://graph.facebook.com/{FACEBOOK_API_VERSION}/oauth/access_token"
FACEBOOK_GRAPH_BASE = f"https://graph.facebook.com/{FACEBOOK_API_VERSION}"


# 환경변수 이름 -> (섹션, 키). 환경변수가 설정돼 있으면 demo_config.json 값보다 우선한다.
# Render 같은 배포 환경에서는 demo_config.json 없이 환경변수만으로 동작한다.
ENV_MAP = {
    "FLASK_SECRET_KEY": (None, "flask_secret_key"),
    "THREADS_APP_ID": ("threads", "app_id"),
    "THREADS_APP_SECRET": ("threads", "app_secret"),
    "THREADS_REDIRECT_URI": ("threads", "redirect_uri"),
    "THREADS_SCOPE": ("threads", "scope"),
    "FACEBOOK_APP_ID": ("facebook", "app_id"),
    "FACEBOOK_APP_SECRET": ("facebook", "app_secret"),
    "FACEBOOK_REDIRECT_URI": ("facebook", "redirect_uri"),
    "FACEBOOK_SCOPE": ("facebook", "scope"),
    "FACEBOOK_PAGE_ID": ("facebook", "page_id"),
}


def load_config():
    config = {"threads": {}, "facebook": {}}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))

    for env_name, (section, key) in ENV_MAP.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        if section is None:
            config[key] = value
        else:
            config.setdefault(section, {})[key] = value
    return config


def _is_placeholder(value):
    return not value or "REPLACE_WITH" in str(value)


CONFIG = load_config()

app = Flask(__name__)


@app.errorhandler(requests.RequestException)
def handle_network_error(exc):
    return render_template(
        "error.html",
        title="Temporary network problem",
        message="A request to the Meta API timed out or failed. Please go back and try again.",
        back_url=request.referrer or url_for("index"),
    ), 502


app.secret_key = (
    CONFIG.get("flask_secret_key")
    if not _is_placeholder(CONFIG.get("flask_secret_key"))
    else secrets.token_hex(32)  # 값을 안 채웠으면 임시 키로라도 기동은 되게 함(재시작 시 세션 초기화됨)
)


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


def _config_warning(provider_key):
    """demo_config.json 값이 아직 채워지지 않았으면 안내 메시지를 돌려준다."""
    cfg = CONFIG.get(provider_key, {})
    missing = [k for k in ("app_id", "app_secret", "redirect_uri") if _is_placeholder(cfg.get(k))]
    if missing:
        return (
            f"Some fields for '{provider_key}' are not configured yet: {', '.join(missing)}. "
            "Set them in demo_config.json or as environment variables and restart the server."
        )
    return None


# ---------------------------------------------------------------------------
# Threads 데모
# ---------------------------------------------------------------------------

@app.route("/threads")
def threads_home():
    if session.get("threads_access_token"):
        return redirect(url_for("threads_profile"))
    warning = _config_warning("threads")
    return render_template("threads.html", warning=warning, logged_in=False, results=None, searched=False)


@app.route("/login/threads")
def threads_login():
    warning = _config_warning("threads")
    if warning:
        return warning, 400

    state = secrets.token_urlsafe(16)
    session["threads_oauth_state"] = state

    cfg = CONFIG["threads"]
    params = {
        "client_id": cfg["app_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg.get("scope", "threads_basic,threads_keyword_search"),
        "response_type": "code",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return redirect(f"{THREADS_AUTHORIZE_URL}?{query}")


@app.route("/callback/threads")
def threads_callback():
    error = request.args.get("error")
    if error:
        return render_template(
            "error.html",
            title="Threads login failed",
            message=request.args.get("error_description", error),
            back_url=url_for("threads_home"),
        )

    state = request.args.get("state")
    if not state or state != session.get("threads_oauth_state"):
        return render_template(
            "error.html",
            title="Threads login failed",
            message="The state value did not match (CSRF check failed). Please start again.",
            back_url=url_for("threads_home"),
        )

    code = request.args.get("code")
    if not code:
        return render_template(
            "error.html",
            title="Threads login failed",
            message="No authorization code was received.",
            back_url=url_for("threads_home"),
        )

    cfg = CONFIG["threads"]
    resp = requests.post(
        THREADS_TOKEN_URL,
        data={
            "client_id": cfg["app_id"],
            "client_secret": cfg["app_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": cfg["redirect_uri"],
            "code": code,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return render_template(
            "error.html",
            title="Threads token exchange failed",
            message=f"Response {resp.status_code}: {resp.text[:500]}",
            back_url=url_for("threads_home"),
        )

    data = resp.json()
    session["threads_access_token"] = data.get("access_token")
    session["threads_user_id"] = data.get("user_id")
    return redirect(url_for("threads_profile"))


@app.route("/threads/profile")
def threads_profile():
    """threads_basic 데모: 로그인 직후 실제 프로필과 본인 게시물을 API로 조회해 표시한다."""
    access_token = session.get("threads_access_token")
    if not access_token:
        return redirect(url_for("threads_home"))

    profile, media, errors = None, [], []

    profile_resp = requests.get(
        f"{THREADS_GRAPH_BASE}/me",
        params={
            "fields": "id,username,name,threads_profile_picture_url,threads_biography",
            "access_token": access_token,
        },
        timeout=15,
    )
    if profile_resp.status_code == 200:
        profile = profile_resp.json()
    else:
        errors.append(f"Profile request failed (status {profile_resp.status_code}): {profile_resp.text[:500]}")

    media_resp = requests.get(
        f"{THREADS_GRAPH_BASE}/me/threads",
        params={
            "fields": "id,text,media_type,media_url,permalink,timestamp,username",
            "limit": 5,
            "access_token": access_token,
        },
        timeout=15,
    )
    if media_resp.status_code == 200:
        media = media_resp.json().get("data", [])
    else:
        errors.append(f"Own posts request failed (status {media_resp.status_code}): {media_resp.text[:500]}")

    return render_template("threads_profile.html", profile=profile, media=media, errors=errors)


@app.route("/threads/search", methods=["GET", "POST"])
def threads_search():
    access_token = session.get("threads_access_token")
    if not access_token:
        return redirect(url_for("threads_home"))

    if request.method == "GET":
        return render_template(
            "threads.html", warning=None, logged_in=True, results=None, error=None, keyword="", searched=False
        )

    keyword = (request.form.get("keyword") or "").strip()
    results, error = [], None

    if keyword:
        resp = requests.get(
            THREADS_KEYWORD_SEARCH_URL,
            params={
                "q": keyword,
                "search_type": "TOP",
                "fields": "id,text,media_type,permalink,timestamp,username",
                "access_token": access_token,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            results = resp.json().get("data", [])
        else:
            error = f"Search request failed (status {resp.status_code}): {resp.text[:500]}"

    return render_template(
        "threads.html",
        warning=None,
        logged_in=True,
        results=results,
        error=error,
        keyword=keyword,
        searched=True,
    )


# ---------------------------------------------------------------------------
# Instagram(Facebook Login) 데모
# ---------------------------------------------------------------------------

@app.route("/instagram")
def instagram_home():
    if session.get("fb_access_token"):
        if session.get("ig_user_id"):
            return redirect(url_for("instagram_search"))
        return redirect(url_for("instagram_pages"))
    warning = _config_warning("facebook")
    return render_template("instagram.html", warning=warning, logged_in=False, results=None, searched=False)


@app.route("/login/facebook")
def facebook_login():
    warning = _config_warning("facebook")
    if warning:
        return warning, 400

    state = secrets.token_urlsafe(16)
    session["fb_oauth_state"] = state

    cfg = CONFIG["facebook"]
    params = {
        "client_id": cfg["app_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg.get("scope", "instagram_basic,pages_show_list,pages_read_engagement,business_management"),
        "response_type": "code",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return redirect(f"{FACEBOOK_AUTHORIZE_URL}?{query}")


@app.route("/callback/facebook")
def facebook_callback():
    error = request.args.get("error")
    if error:
        return render_template(
            "error.html",
            title="Facebook login failed",
            message=request.args.get("error_description", error),
            back_url=url_for("instagram_home"),
        )

    state = request.args.get("state")
    if not state or state != session.get("fb_oauth_state"):
        return render_template(
            "error.html",
            title="Facebook login failed",
            message="The state value did not match (CSRF check failed). Please start again.",
            back_url=url_for("instagram_home"),
        )

    code = request.args.get("code")
    if not code:
        return render_template(
            "error.html",
            title="Facebook login failed",
            message="No authorization code was received.",
            back_url=url_for("instagram_home"),
        )

    cfg = CONFIG["facebook"]
    resp = requests.get(
        FACEBOOK_TOKEN_URL,
        params={
            "client_id": cfg["app_id"],
            "client_secret": cfg["app_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "code": code,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return render_template(
            "error.html",
            title="Facebook token exchange failed",
            message=f"Response {resp.status_code}: {resp.text[:500]}",
            back_url=url_for("instagram_home"),
        )

    session["fb_access_token"] = resp.json().get("access_token")
    session.pop("ig_user_id", None)  # 새로 로그인했으니 이전에 선택한 페이지/IG 계정은 초기화
    session.pop("ig_pages", None)
    return redirect(url_for("instagram_pages"))


def _fetch_managed_pages(access_token):
    """pages_show_list 데모: me/accounts로 로그인 사용자가 관리하는 페이지 목록을 조회한다."""
    resp = requests.get(
        f"{FACEBOOK_GRAPH_BASE}/me/accounts",
        params={"access_token": access_token, "fields": "id,name,instagram_business_account{id,username}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return [], f"Managed Pages request failed (status {resp.status_code}): {resp.text[:500]}"

    pages = []
    for page in resp.json().get("data", []):
        ig = page.get("instagram_business_account") or {}
        pages.append({
            "id": page.get("id"),
            "name": page.get("name"),
            "ig_id": ig.get("id"),
            "ig_username": ig.get("username"),
        })
    return pages, None


def _fetch_page_instagram_account(access_token, page_id):
    """페이지 ID로 연결된 Instagram 비즈니스 계정을 직접 조회한다."""
    resp = requests.get(
        f"{FACEBOOK_GRAPH_BASE}/{page_id}",
        params={"access_token": access_token, "fields": "instagram_business_account{id,username}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return None, None, f"Page request failed (status {resp.status_code}): {resp.text[:500]}"
    ig = resp.json().get("instagram_business_account") or {}
    return ig.get("id"), ig.get("username"), None


@app.route("/instagram/pages")
def instagram_pages():
    access_token = session.get("fb_access_token")
    if not access_token:
        return redirect(url_for("instagram_home"))

    pages, error = _fetch_managed_pages(access_token)
    fallback_used = False

    # 폴백: me/accounts가 비어 있을 때만 demo_config.json의 facebook.page_id를 사용한다.
    fallback_page_id = CONFIG.get("facebook", {}).get("page_id")
    if not pages and not _is_placeholder(fallback_page_id):
        ig_id, ig_username, fb_error = _fetch_page_instagram_account(access_token, fallback_page_id)
        if not fb_error:
            pages = [{"id": fallback_page_id, "name": f"Page {fallback_page_id}", "ig_id": ig_id, "ig_username": ig_username}]
            fallback_used = True
        else:
            error = (error + " / " if error else "") + fb_error

    session["ig_pages"] = {p["id"]: [p["ig_id"], p["name"], p["ig_username"]] for p in pages}
    return render_template("instagram_pages.html", pages=pages, error=error, fallback_used=fallback_used)


@app.route("/instagram/select-page", methods=["POST"])
def instagram_select_page():
    if not session.get("fb_access_token"):
        return redirect(url_for("instagram_home"))

    page_id = request.form.get("page_id", "")
    pages = session.get("ig_pages") or {}
    if page_id not in pages:
        return redirect(url_for("instagram_pages"))

    ig_user_id, page_name, ig_username = pages[page_id]
    if not ig_user_id:
        return render_template(
            "error.html",
            title="No Instagram account",
            message="The selected Page has no linked Instagram professional account.",
            back_url=url_for("instagram_pages"),
        )

    session["ig_user_id"] = ig_user_id
    session["ig_page_name"] = page_name
    session["ig_username"] = ig_username
    return redirect(url_for("instagram_search"))


@app.route("/instagram/search", methods=["GET", "POST"])
def instagram_search():
    access_token = session.get("fb_access_token")
    if not access_token:
        return redirect(url_for("instagram_home"))

    ig_user_id = session.get("ig_user_id")
    if not ig_user_id:
        return redirect(url_for("instagram_pages"))

    if request.method == "GET":
        return render_template(
            "instagram.html", warning=None, logged_in=True, results=None, error=None, keyword="", searched=False
        )

    keyword = (request.form.get("keyword") or "").strip()
    results, error = [], None

    if keyword:
        hashtag_resp = requests.get(
            f"{FACEBOOK_GRAPH_BASE}/ig_hashtag_search",
            params={"user_id": ig_user_id, "q": keyword, "access_token": access_token},
            timeout=15,
        )
        if hashtag_resp.status_code != 200:
            error = f"Hashtag search failed (status {hashtag_resp.status_code}): {hashtag_resp.text[:500]}"
        else:
            hashtag_data = hashtag_resp.json().get("data", [])
            if hashtag_data:
                media_resp = requests.get(
                    f"{FACEBOOK_GRAPH_BASE}/{hashtag_data[0]['id']}/top_media",
                    params={
                        "user_id": ig_user_id,
                        "fields": "id,caption,media_type,media_url,permalink,timestamp",
                        "access_token": access_token,
                    },
                    timeout=15,
                )
                if media_resp.status_code != 200:
                    error = f"Media request failed (status {media_resp.status_code}): {media_resp.text[:500]}"
                else:
                    results = media_resp.json().get("data", [])

    return render_template(
        "instagram.html",
        warning=None,
        logged_in=True,
        results=results,
        error=error,
        keyword=keyword,
        searched=True,
    )


if __name__ == "__main__":
    app.run(port=5000, debug=True)

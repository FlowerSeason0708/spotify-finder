import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import pandas as pd
import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

APP_TITLE = "全平台新歌发现器"
AUTH_MODE_EMAIL = "邮箱登录"
PLATFORM_OPTIONS = {
    "Spotify": {
        "slug": "spotify",
        "description": "适合导出到 Spotify，并继续用 TuneMyMusic 做迁移或导入。",
        "transfer_label": "打开 TuneMyMusic 导入页面",
        "transfer_title": "下一步：导入到 Spotify",
        "transfer_text": "选好最终歌单后，可以直接打开 TuneMyMusic，把刚下载的 TXT 或 CSV 导入并继续传到 Spotify。",
        "transfer_url": "https://www.tunemymusic.com/zh-CN/transfer",
        "txt_filename": "spotify_selected_tracks.txt",
        "csv_filename": "spotify_selected_tracks.csv",
    },
    "网易云音乐": {
        "slug": "netease",
        "description": "导出更适合中文平台搜索的歌单文本，再手动导入或搜索。",
        "transfer_label": "打开网易云音乐",
        "transfer_title": "下一步：导入到网易云音乐",
        "transfer_text": "你可以先下载歌单文本，再到网易云音乐里逐首搜索，或配合第三方迁移工具继续处理。",
        "transfer_url": "https://music.163.com/",
        "txt_filename": "netease_selected_tracks.txt",
        "csv_filename": "netease_selected_tracks.csv",
    },
    "QQ 音乐": {
        "slug": "qqmusic",
        "description": "导出文本后可在 QQ 音乐中逐首搜索，适合整理中文平台歌单。",
        "transfer_label": "打开 QQ 音乐",
        "transfer_title": "下一步：导入到 QQ 音乐",
        "transfer_text": "下载歌单后，可以到 QQ 音乐搜索同名歌曲，或配合第三方工具做后续导入。",
        "transfer_url": "https://y.qq.com/",
        "txt_filename": "qqmusic_selected_tracks.txt",
        "csv_filename": "qqmusic_selected_tracks.csv",
    },
    "酷狗音乐": {
        "slug": "kugou",
        "description": "导出歌单文本后，适合到酷狗音乐中做关键词搜索与收藏。",
        "transfer_label": "打开酷狗音乐",
        "transfer_title": "下一步：导入到酷狗音乐",
        "transfer_text": "下载后的歌单可以作为酷狗音乐搜索依据，适合手动逐首确认并加入歌单。",
        "transfer_url": "https://www.kugou.com/",
        "txt_filename": "kugou_selected_tracks.txt",
        "csv_filename": "kugou_selected_tracks.csv",
    },
    "通用导出": {
        "slug": "universal",
        "description": "输出标准歌单文本和 CSV，适合任何平台或后续自定义处理。",
        "transfer_label": "打开 TuneMyMusic",
        "transfer_title": "下一步：继续导入到其他平台",
        "transfer_text": "如果你还没决定平台，先导出通用文本和 CSV。之后可以再导入 Spotify、网易云、QQ 音乐或其他服务。",
        "transfer_url": "https://www.tunemymusic.com/zh-CN/transfer",
        "txt_filename": "universal_selected_tracks.txt",
        "csv_filename": "universal_selected_tracks.csv",
    },
}
DEFAULT_NAMESPACE = "my-presets"
DEFAULT_ARTISTS = """Taylor Swift
Drake
Fred again..
The Weeknd
Dua Lipa
SZA
Bad Bunny
Billie Eilish
Travis Scott
Calvin Harris"""

APP_SUBTITLE = "发现候选新歌，手动挑选，导出到 Spotify、网易云音乐、QQ 音乐、酷狗音乐等多个平台。"
CUSTOM_TEMPLATE_FILE = Path(__file__).with_name("user_artist_templates.json")
ARTIST_TEMPLATES = {
    "通用流行": """Taylor Swift
Drake
The Weeknd
Dua Lipa
SZA
Billie Eilish
Bad Bunny
Calvin Harris""",
    "Melodic Techno": """Anyma
Tale Of Us
ARTBAT
Massano
Adriatique
Mind Against
Kevin de Vries
Agents Of Time""",
    "House / EDM": """Fred again..
Calvin Harris
John Summit
Dom Dolla
FISHER
Meduza
David Guetta
Skrillex""",
    "Hip-Hop / Rap": """Drake
Travis Scott
Kendrick Lamar
Future
Lil Baby
21 Savage
Doja Cat
Nicki Minaj""",
    "Indie / Alternative": """Lana Del Rey
Arctic Monkeys
The 1975
Tame Impala
Phoebe Bridgers
Mitski
Clairo
Cigarettes After Sex""",
    "K-Pop": """BTS
BLACKPINK
NewJeans
LE SSERAFIM
Stray Kids
SEVENTEEN
aespa
IVE""",
}


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎧",
    layout="wide",
)


@st.cache_data(show_spinner=False, ttl=3600)
def search_itunes(artist: str, limit: int = 12) -> list[dict]:
    url = "https://itunes.apple.com/search"
    params = {
        "term": artist,
        "entity": "song",
        "media": "music",
        "limit": limit,
        "country": "US",
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("results", [])


def normalize_date(date_str: str):
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def build_playlist_text(dataframe: pd.DataFrame) -> str:
    return "\n".join(
        f"{row['艺人']} - {row['歌曲']}" for _, row in dataframe.iterrows()
    )


def build_platform_playlist_text(dataframe: pd.DataFrame, platform: str) -> str:
    if platform in {"网易云音乐", "QQ 音乐", "酷狗音乐"}:
        return "\n".join(
            f"{row['歌曲']} - {row['艺人']}" for _, row in dataframe.iterrows()
        )
    return build_playlist_text(dataframe)


def build_csv(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def build_track_id(row: pd.Series) -> str:
    return f"{row['艺人']}|{row['歌曲']}|{row['发布日期']}"


def exportable_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.drop(columns=["track_id"], errors="ignore")


def get_config_value(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except StreamlitSecretNotFoundError:
        pass
    return os.getenv(key, default)


def get_supabase_config() -> tuple[str, str]:
    return (
        get_config_value("SUPABASE_URL"),
        get_config_value("SUPABASE_ANON_KEY"),
    )


def has_remote_storage() -> bool:
    supabase_url, supabase_key = get_supabase_config()
    return bool(supabase_url and supabase_key)


def build_supabase_headers() -> dict[str, str]:
    supabase_url, supabase_key = get_supabase_config()
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase 未配置。")

    return {
        "apikey": supabase_key,
        "Content-Type": "application/json",
    }


def build_supabase_auth_headers() -> dict[str, str]:
    _, supabase_key = get_supabase_config()
    if not supabase_key:
        raise ValueError("Supabase 未配置。")

    return {
        "apikey": supabase_key,
        "Content-Type": "application/json",
    }


def is_uuid_like(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


def build_user_namespace(user: dict) -> str:
    user_id = str(user.get("id", "")).strip()
    email = str(user.get("email", "")).strip().lower()

    if user_id and is_uuid_like(user_id):
        return user_id
    if email:
        return f"user:{email}"
    return DEFAULT_NAMESPACE


def supabase_sign_up(email: str, password: str) -> tuple[bool, str]:
    supabase_url, _ = get_supabase_config()
    endpoint = f"{supabase_url.rstrip('/')}/auth/v1/signup"
    payload = {
        "email": email,
        "password": password,
    }
    response = requests.post(
        endpoint,
        headers=build_supabase_auth_headers(),
        json=payload,
        timeout=20,
    )

    if response.ok:
        return True, "注册成功。你现在可以直接登录；如果你启用了邮箱验证，请先验证邮箱。"

    try:
        detail = response.json()
        error_message = detail.get("msg") or detail.get("error_description") or detail.get("message")
    except ValueError:
        error_message = response.text

    return False, error_message or "注册失败。"


def supabase_sign_in(email: str, password: str) -> tuple[bool, dict | None, str]:
    supabase_url, _ = get_supabase_config()
    endpoint = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    payload = {
        "email": email,
        "password": password,
    }
    response = requests.post(
        endpoint,
        headers=build_supabase_auth_headers(),
        json=payload,
        timeout=20,
    )

    if response.ok:
        data = response.json()
        user = data.get("user", {}) or {}
        return True, {
            "email": user.get("email", email),
            "id": user.get("id", ""),
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
        }, "登录成功。"

    try:
        detail = response.json()
        error_message = detail.get("msg") or detail.get("error_description") or detail.get("message")
    except ValueError:
        error_message = response.text

    return False, None, error_message or "登录失败。"


def load_local_templates() -> dict[str, str]:
    if not CUSTOM_TEMPLATE_FILE.exists():
        return {}

    try:
        data = json.loads(CUSTOM_TEMPLATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        str(name): str(value).strip()
        for name, value in data.items()
        if str(name).strip() and str(value).strip()
    }


def save_local_templates(templates: dict[str, str]) -> None:
    CUSTOM_TEMPLATE_FILE.write_text(
        json.dumps(templates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_remote_templates(namespace: str) -> dict[str, str]:
    if not has_remote_storage():
        return {}

    supabase_url, _ = get_supabase_config()
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/artist_presets"
        f"?select=name,artists&namespace=eq.{quote(namespace, safe='')}&order=name.asc"
    )
    response = requests.get(endpoint, headers=build_supabase_headers(), timeout=15)
    response.raise_for_status()
    rows = response.json()
    return {
        str(row.get("name", "")).strip(): str(row.get("artists", "")).strip()
        for row in rows
        if str(row.get("name", "")).strip() and str(row.get("artists", "")).strip()
    }


def save_remote_template(namespace: str, name: str, artists: str) -> None:
    supabase_url, _ = get_supabase_config()
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/artist_presets"
        "?on_conflict=namespace,name"
    )
    payload = [
        {
            "namespace": namespace,
            "name": name,
            "artists": artists,
        }
    ]
    headers = build_supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
    response.raise_for_status()


def delete_remote_template(namespace: str, name: str) -> None:
    supabase_url, _ = get_supabase_config()
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/artist_presets"
        f"?namespace=eq.{quote(namespace, safe='')}&name=eq.{quote(name, safe='')}"
    )
    response = requests.delete(endpoint, headers=build_supabase_headers(), timeout=15)
    response.raise_for_status()


def load_custom_templates(namespace: str) -> dict[str, str]:
    if has_remote_storage():
        return load_remote_templates(namespace)
    return load_local_templates()


def save_custom_template(namespace: str, name: str, artists: str, cache: dict[str, str]) -> dict[str, str]:
    updated_templates = dict(cache)
    updated_templates[name] = artists

    if has_remote_storage():
        save_remote_template(namespace, name, artists)
    else:
        save_local_templates(updated_templates)

    return updated_templates


def delete_custom_template(namespace: str, name: str, cache: dict[str, str]) -> dict[str, str]:
    updated_templates = {
        template_name: value
        for template_name, value in cache.items()
        if template_name != name
    }

    if has_remote_storage():
        delete_remote_template(namespace, name)
    else:
        save_local_templates(updated_templates)

    return updated_templates


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(29, 185, 84, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(80, 160, 255, 0.12), transparent 24%),
                linear-gradient(180deg, #08110c 0%, #0e1712 18%, #111712 100%);
            color: #f7fbf7;
        }
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d1511 0%, #111915 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 0.85rem 1rem;
            box-shadow: 0 16px 30px rgba(0, 0, 0, 0.18);
        }
        div[data-testid="stMetric"] label {
            color: rgba(247, 251, 247, 0.72);
        }
        div[data-testid="stMetricValue"] {
            color: #ffffff;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        button[data-baseweb="tab"] {
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.06);
            padding: 0.45rem 1rem;
            color: rgba(245, 250, 246, 0.88) !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, #1db954 0%, #159947 100%);
            color: #041109 !important;
            font-weight: 700;
        }
        .stButton > button,
        .stDownloadButton > button {
            background: linear-gradient(135deg, #1ed760 0%, #169c48 100%);
            color: #041109 !important;
            border: none;
            font-weight: 700;
            border-radius: 14px;
            box-shadow: 0 12px 26px rgba(12, 75, 37, 0.32);
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: linear-gradient(135deg, #32e26f 0%, #18ad50 100%);
            color: #041109 !important;
        }
        .stButton > button[kind="secondary"] {
            background: rgba(255, 255, 255, 0.09);
            color: #f5faf6 !important;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .stTextInput label,
        .stTextArea label,
        .stSelectbox label,
        .stSlider label,
        .stNumberInput label,
        .stMultiSelect label,
        .stMarkdown,
        .stCaption,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p {
            color: #f3f7f3 !important;
        }
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div {
            background: rgba(7, 18, 12, 0.92) !important;
            color: #ffffff !important;
            border: 1px solid rgba(115, 255, 175, 0.24) !important;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
        }
        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: rgba(220, 230, 223, 0.52) !important;
        }
        .stTextArea textarea {
            line-height: 1.65 !important;
            caret-color: #6effab !important;
        }
        .stTextInput input {
            caret-color: #6effab !important;
            font-weight: 600 !important;
        }
        .stTextInput input:focus,
        .stTextArea textarea:focus {
            border: 1px solid rgba(110, 255, 171, 0.72) !important;
            box-shadow: 0 0 0 1px rgba(110, 255, 171, 0.22) !important;
        }
        .stTextInput div[data-baseweb="input"] {
            background: rgba(7, 18, 12, 0.92) !important;
            border-radius: 12px !important;
        }
        .stTextArea div[data-baseweb="textarea"] {
            background: rgba(7, 18, 12, 0.92) !important;
            border-radius: 14px !important;
        }
        .stAlert {
            color: #f5faf6;
        }
        .storage-chip {
            display: inline-block;
            margin-top: 0.35rem;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            color: #dfffea;
            font-size: 0.78rem;
        }
        .transfer-card {
            margin-top: 1rem;
            padding: 1rem 1.1rem;
            border-radius: 18px;
            background: linear-gradient(135deg, rgba(29, 185, 84, 0.14), rgba(62, 112, 255, 0.12));
            border: 1px solid rgba(255, 255, 255, 0.09);
        }
        .transfer-card-title {
            margin: 0 0 0.35rem 0;
            color: #ffffff;
            font-size: 1.05rem;
            font-weight: 700;
        }
        .transfer-card-text {
            margin: 0 0 0.9rem 0;
            color: rgba(245, 250, 246, 0.78);
            line-height: 1.6;
        }
        .transfer-link {
            display: inline-block;
            padding: 0.72rem 1rem;
            border-radius: 14px;
            background: #f6fbf7;
            color: #08110c !important;
            text-decoration: none !important;
            font-weight: 700;
        }
        .stExpander details {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
        }
        .stExpander summary {
            color: #f7fbf7 !important;
            font-weight: 700 !important;
        }
        .stExpander details p,
        .stExpander details li,
        .stExpander details div,
        .stExpander details span {
            color: rgba(244, 249, 245, 0.9) !important;
            line-height: 1.7 !important;
        }
        .stExpander details strong {
            color: #ffffff !important;
        }
        .hero {
            position: relative;
            overflow: hidden;
            padding: 2rem 2rem 1.6rem 2rem;
            border-radius: 28px;
            background:
                radial-gradient(circle at 20% 10%, rgba(29, 185, 84, 0.55), transparent 28%),
                radial-gradient(circle at 85% 15%, rgba(87, 143, 255, 0.28), transparent 20%),
                linear-gradient(135deg, #15271d 0%, #101510 45%, #0c0f0d 100%);
            border: 1px solid rgba(255, 255, 255, 0.09);
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
            margin-bottom: 1.2rem;
        }
        .hero::after {
            content: "";
            position: absolute;
            inset: auto -60px -80px auto;
            width: 220px;
            height: 220px;
            background: rgba(255, 255, 255, 0.04);
            border-radius: 50%;
            filter: blur(10px);
        }
        .hero-kicker {
            display: inline-block;
            margin-bottom: 0.85rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            color: #d6ffe4;
            font-size: 0.82rem;
            letter-spacing: 0.04em;
        }
        .hero-title {
            font-size: 2.35rem;
            font-weight: 800;
            line-height: 1.05;
            margin: 0 0 0.65rem 0;
            color: #ffffff;
        }
        .hero-text {
            max-width: 760px;
            margin: 0;
            font-size: 1rem;
            line-height: 1.7;
            color: rgba(244, 249, 245, 0.84);
        }
        .hero-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin-top: 1.4rem;
        }
        .hero-card {
            padding: 1rem 1.05rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.07);
            backdrop-filter: blur(4px);
        }
        .hero-card strong {
            display: block;
            margin-bottom: 0.3rem;
            color: #ffffff;
            font-size: 0.95rem;
        }
        .hero-card span {
            color: rgba(244, 249, 245, 0.72);
            font-size: 0.9rem;
            line-height: 1.5;
        }
        .section-label {
            margin-top: 1.4rem;
            margin-bottom: 0.5rem;
            color: #e8f5ea;
            font-size: 1.1rem;
            font-weight: 700;
        }
        @media (max-width: 900px) {
            .hero {
                padding: 1.4rem;
            }
            .hero-title {
                font-size: 1.8rem;
            }
            .hero-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-kicker">Multi-platform workflow</div>
            <div class="hero-title">{APP_TITLE}</div>
            <p class="hero-text">{APP_SUBTITLE} 先从艺人池里抓候选曲目，再在页面里试听、筛选、勾选，最后导出你真正想保留的歌单。</p>
            <div class="hero-grid">
                <div class="hero-card">
                    <strong>Step 1</strong>
                    <span>输入任意艺人名单，快速抓出最近发布的候选歌曲。</span>
                </div>
                <div class="hero-card">
                    <strong>Step 2</strong>
                    <span>按艺人浏览、试听预览、手动勾选想保留的曲目。</span>
                </div>
                <div class="hero-card">
                    <strong>Step 3</strong>
                    <span>导出最终歌单 TXT 或 CSV，直接进入后续导入流程。</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_transfer_card(platform: str) -> None:
    platform_config = PLATFORM_OPTIONS[platform]
    st.markdown(
        f"""
        <div class="transfer-card">
            <div class="transfer-card-title">{platform_config["transfer_title"]}</div>
            <p class="transfer-card-text">{platform_config["transfer_text"]}</p>
            <a class="transfer-link" href="{platform_config["transfer_url"]}" target="_blank">{platform_config["transfer_label"]}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fetch_recent_tracks(artists: list[str], days: int, limit: int) -> tuple[pd.DataFrame, list[str]]:
    cutoff = datetime.now().date() - timedelta(days=days)
    rows: list[dict] = []
    errors: list[str] = []

    for artist in artists:
        try:
            results = search_itunes(artist, limit=limit)
            for item in results:
                release_date = normalize_date(item.get("releaseDate", ""))
                if release_date and release_date >= cutoff:
                    rows.append(
                        {
                            "艺人": item.get("artistName", ""),
                            "歌曲": item.get("trackName", ""),
                            "专辑": item.get("collectionName", ""),
                            "类型": item.get("primaryGenreName", ""),
                            "发布日期": str(release_date),
                            "时长(分钟)": round(item.get("trackTimeMillis", 0) / 60000, 2)
                            if item.get("trackTimeMillis")
                            else None,
                            "封面": item.get("artworkUrl100", ""),
                            "预览": item.get("previewUrl", ""),
                            "商店链接": item.get("trackViewUrl", ""),
                        }
                    )
        except requests.RequestException as exc:
            errors.append(f"{artist} 抓取失败：{exc}")

    if not rows:
        return pd.DataFrame(), errors

    dataframe = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["艺人", "歌曲"])
        .sort_values(by=["发布日期", "艺人", "歌曲"], ascending=[False, True, True])
        .reset_index(drop=True)
    )
    dataframe["track_id"] = dataframe.apply(build_track_id, axis=1)
    return dataframe, errors


inject_styles()
render_hero()

if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()
if "warnings" not in st.session_state:
    st.session_state.warnings = []
if "last_search_meta" not in st.session_state:
    st.session_state.last_search_meta = {}
if "selected_track_ids" not in st.session_state:
    st.session_state.selected_track_ids = []
if "target_platform" not in st.session_state:
    st.session_state.target_platform = "Spotify"
if "artists_text" not in st.session_state:
    st.session_state.artists_text = DEFAULT_ARTISTS
if "custom_template_name" not in st.session_state:
    st.session_state.custom_template_name = ""
if "preset_namespace" not in st.session_state:
    st.session_state.preset_namespace = DEFAULT_NAMESPACE
if "preset_namespace_input" not in st.session_state:
    st.session_state.preset_namespace_input = st.session_state.preset_namespace
if "last_loaded_namespace" not in st.session_state:
    st.session_state.last_loaded_namespace = st.session_state.preset_namespace
if "custom_templates" not in st.session_state:
    st.session_state.custom_templates = load_custom_templates(st.session_state.preset_namespace)
if "save_template_success_message" not in st.session_state:
    st.session_state.save_template_success_message = ""
if "clear_custom_template_name" not in st.session_state:
    st.session_state.clear_custom_template_name = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "auth_message" not in st.session_state:
    st.session_state.auth_message = ""
if "auth_error" not in st.session_state:
    st.session_state.auth_error = ""
if "auth_email" not in st.session_state:
    st.session_state.auth_email = ""
if "auth_password" not in st.session_state:
    st.session_state.auth_password = ""

if st.session_state.clear_custom_template_name:
    st.session_state.custom_template_name = ""
    st.session_state.clear_custom_template_name = False

with st.sidebar:
    st.markdown("## 账号")
    if has_remote_storage():
        if st.session_state.auth_message:
            st.success(st.session_state.auth_message)
            st.session_state.auth_message = ""
        if st.session_state.auth_error:
            st.error(st.session_state.auth_error)
            st.session_state.auth_error = ""

        if st.session_state.auth_user:
            st.success(f"已登录：{st.session_state.auth_user['email']}")
            st.caption("登录后，你的预设会自动保存到个人账号空间。")
            if st.button("退出登录", use_container_width=True):
                st.session_state.auth_user = None
                st.session_state.custom_templates = load_custom_templates(DEFAULT_NAMESPACE)
                st.session_state.preset_namespace = DEFAULT_NAMESPACE
                st.session_state.preset_namespace_input = DEFAULT_NAMESPACE
                st.session_state.last_loaded_namespace = DEFAULT_NAMESPACE
                st.rerun()
        else:
            st.caption("登录后可把预设自动绑定到你的个人账号。")
            with st.form("auth_form"):
                st.text_input("邮箱", key="auth_email", placeholder="you@example.com")
                st.text_input("密码", key="auth_password", type="password", placeholder="至少 6 位")
                auth_action = st.radio(
                    "操作",
                    [AUTH_MODE_EMAIL, "注册账号"],
                    horizontal=True,
                )
                submitted = st.form_submit_button("继续")

            if submitted:
                email = st.session_state.auth_email.strip()
                password = st.session_state.auth_password.strip()
                if not email or not password:
                    st.session_state.auth_error = "请先输入邮箱和密码。"
                    st.rerun()
                elif len(password) < 6:
                    st.session_state.auth_error = "密码至少需要 6 位。"
                    st.rerun()
                elif auth_action == "注册账号":
                    success, message = supabase_sign_up(email, password)
                    if success:
                        st.session_state.auth_message = message
                    else:
                        st.session_state.auth_error = message
                    st.rerun()
                else:
                    success, user, message = supabase_sign_in(email, password)
                    if success and user:
                        user_namespace = build_user_namespace(user)
                        st.session_state.auth_user = user
                        st.session_state.auth_message = message
                        st.session_state.preset_namespace = user_namespace
                        st.session_state.preset_namespace_input = user_namespace
                        st.session_state.last_loaded_namespace = user_namespace
                        st.session_state.custom_templates = load_custom_templates(user_namespace)
                    else:
                        st.session_state.auth_error = message
                    st.rerun()
    else:
        st.info("当前未配置 Supabase，登录功能不可用，本地仍可正常使用。")

    st.markdown("## 参数设置")
    st.caption("控制抓取范围与候选池大小")
    target_platform = st.selectbox(
        "目标平台",
        list(PLATFORM_OPTIONS.keys()),
        key="target_platform",
        help="切换后，导出文件名、文案和跳转入口会随平台变化。",
    )
    st.caption(PLATFORM_OPTIONS[target_platform]["description"])
    days = st.slider("只保留最近多少天发布的歌", min_value=7, max_value=365, value=60)
    result_limit = st.slider("每位艺人最多抓取多少条候选结果", min_value=5, max_value=30, value=12)
    st.info("数据源为 iTunes Search API，适合做候选曲目初筛。")

    st.markdown("## 使用节奏")
    st.markdown(
        "1. 先抓任意艺人的候选歌曲\n"
        "2. 再去手动选歌\n"
        "3. 最后导出最终歌单"
    )

    st.markdown("## 艺人模板")
    selected_template = st.selectbox("快速载入一组常见艺人", list(ARTIST_TEMPLATES.keys()))
    template_col_1, template_col_2 = st.columns(2)
    with template_col_1:
        if st.button("载入模板", use_container_width=True):
            st.session_state.artists_text = ARTIST_TEMPLATES[selected_template]
            st.rerun()
    with template_col_2:
        if st.button("恢复默认", use_container_width=True):
            st.session_state.artists_text = DEFAULT_ARTISTS
            st.rerun()

    st.markdown("## 我的预设")
    storage_mode = "Supabase 云端同步" if has_remote_storage() else "本地文件保存"
    st.markdown(f'<div class="storage-chip">当前保存方式：{storage_mode}</div>', unsafe_allow_html=True)
    if st.session_state.save_template_success_message:
        st.success(st.session_state.save_template_success_message)
        st.session_state.save_template_success_message = ""
    if st.session_state.auth_user:
        namespace = build_user_namespace(st.session_state.auth_user)
        st.caption("当前使用登录账号的个人预设空间。")
        if st.button("刷新我的预设", use_container_width=True):
            try:
                st.session_state.custom_templates = load_custom_templates(namespace)
                st.session_state.last_loaded_namespace = namespace
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"刷新预设失败：{exc}")
    else:
        st.text_input(
            "预设空间名",
            key="preset_namespace_input",
            help="不同设备填写同一个预设空间名，就能看到同一组预设。",
        )
        namespace = st.session_state.preset_namespace_input.strip() or DEFAULT_NAMESPACE

        sync_col_1, sync_col_2 = st.columns(2)
        with sync_col_1:
            if st.button("加载这个空间", use_container_width=True):
                try:
                    st.session_state.preset_namespace = namespace
                    st.session_state.custom_templates = load_custom_templates(namespace)
                    st.session_state.last_loaded_namespace = namespace
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"刷新预设失败：{exc}")
        with sync_col_2:
            st.caption("跨设备时请保持同一个预设空间名")

    custom_templates = st.session_state.custom_templates
    custom_template_names = sorted(custom_templates.keys())

    if custom_template_names:
        selected_custom_template = st.selectbox(
            "已保存的自定义预设",
            custom_template_names,
            key="selected_custom_template",
        )
        custom_col_1, custom_col_2 = st.columns(2)
        with custom_col_1:
            if st.button("载入我的预设", use_container_width=True):
                st.session_state.artists_text = custom_templates[selected_custom_template]
                st.rerun()
        with custom_col_2:
            if st.button("删除我的预设", use_container_width=True):
                try:
                    st.session_state.custom_templates = delete_custom_template(
                        namespace,
                        selected_custom_template,
                        custom_templates,
                    )
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"删除预设失败：{exc}")
    else:
        st.caption("你还没有保存过自己的艺人预设。")

    st.text_input(
        "给当前艺人名单起个名字",
        key="custom_template_name",
        placeholder="例如：我的健身歌单艺人池",
    )
    if st.button("保存为我的预设", use_container_width=True):
        preset_name = st.session_state.custom_template_name.strip()
        preset_value = st.session_state.artists_text.strip()

        if not preset_name:
            st.warning("请先输入预设名称。")
        elif not preset_value:
            st.warning("当前艺人名单为空，无法保存预设。")
        else:
            try:
                if namespace != st.session_state.last_loaded_namespace:
                    st.session_state.custom_templates = load_custom_templates(namespace)
                    custom_templates = st.session_state.custom_templates
                st.session_state.custom_templates = save_custom_template(
                    namespace,
                    prese

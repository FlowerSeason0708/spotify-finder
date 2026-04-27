import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

APP_TITLE = "Spotify 新歌发现器"
TRANSFER_URL = "https://www.tunemymusic.com/zh-CN/transfer"
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

APP_SUBTITLE = "发现候选新歌，手动挑选，导出最终歌单。适合任何流派、任何艺人列表。"
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
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }


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
            <div class="hero-kicker">Spotify-ready workflow</div>
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


def render_transfer_card() -> None:
    st.markdown(
        f"""
        <div class="transfer-card">
            <div class="transfer-card-title">下一步：导入到 Spotify</div>
            <p class="transfer-card-text">选好最终歌单后，可以直接打开 TuneMyMusic，把刚下载的 TXT 或 CSV 导入并继续传到 Spotify。</p>
            <a class="transfer-link" href="{TRANSFER_URL}" target="_blank">打开 TuneMyMusic 导入页面</a>
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

with st.sidebar:
    st.markdown("## 参数设置")
    st.caption("控制抓取范围与候选池大小")
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
                    preset_name,
                    preset_value,
                    custom_templates,
                )
                st.session_state.preset_namespace = namespace
                st.session_state.last_loaded_namespace = namespace
                st.session_state["custom_template_name"] = ""
                st.session_state["save_template_success_message"] = f"已保存预设：{preset_name}"
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"保存预设失败：{exc}")

artists_text = st.text_area(
    "输入你想监控的艺人，一行一个",
    key="artists_text",
    height=240,
    placeholder="例如：Anyma",
)

search_clicked = st.button("抓取新歌", type="primary", use_container_width=True)

if search_clicked:
    artists = [artist.strip() for artist in artists_text.splitlines() if artist.strip()]

    if not artists:
        st.error("请先输入至少 1 位艺人。")
    else:
        with st.spinner("正在抓取最近发布的候选歌曲..."):
            results_df, warnings = fetch_recent_tracks(artists, days, result_limit)
            st.session_state.results_df = results_df
            st.session_state.warnings = warnings
            st.session_state.last_search_meta = {
                "artist_count": len(artists),
                "days": days,
                "result_limit": result_limit,
            }
            st.session_state.selected_track_ids = []

results_df = st.session_state.results_df
warnings = st.session_state.warnings
last_search_meta = st.session_state.last_search_meta

for warning in warnings:
    st.warning(warning)

if search_clicked or not results_df.empty:
    if results_df.empty:
        st.warning("没有抓到最近发布的候选歌曲。可以把天数调大一点，比如 180 天。")
    else:
        full_csv_bytes = build_csv(exportable_dataframe(results_df))
        selected_track_ids = set(st.session_state.selected_track_ids)

        metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
        metric_1.metric("监控艺人数", last_search_meta.get("artist_count", 0))
        metric_2.metric("候选歌曲数", len(results_df))
        metric_3.metric("时间范围", f"近 {last_search_meta.get('days', days)} 天")
        metric_4.metric("涉及流派数", results_df["类型"].nunique())
        metric_5.metric("已选歌曲数", len(selected_track_ids))

        st.markdown('<div class="section-label">结果筛选</div>', unsafe_allow_html=True)
        filter_col_1, filter_col_2 = st.columns([2, 1])
        all_artists = ["全部艺人"] + sorted(results_df["艺人"].dropna().unique().tolist())
        selected_artist = filter_col_1.selectbox("按艺人查看", all_artists)
        sort_option = filter_col_2.selectbox(
            "排序方式",
            ["发布日期（新到旧）", "发布日期（旧到新）", "艺人名称"],
        )

        filtered_df = results_df.copy()
        if selected_artist != "全部艺人":
            filtered_df = filtered_df[filtered_df["艺人"] == selected_artist]

        if sort_option == "发布日期（旧到新）":
            filtered_df = filtered_df.sort_values(by=["发布日期", "艺人", "歌曲"], ascending=[True, True, True])
        elif sort_option == "艺人名称":
            filtered_df = filtered_df.sort_values(by=["艺人", "发布日期", "歌曲"], ascending=[True, False, True])

        selection_df = filtered_df.copy()
        selection_df["入选"] = selection_df["track_id"].isin(selected_track_ids)

        tab_table, tab_cards, tab_picker, tab_playlist = st.tabs(
            ["表格视图", "卡片视图", "手动选歌", "歌单导出"]
        )

        with tab_table:
            st.dataframe(
                filtered_df.drop(columns=["track_id"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "封面": st.column_config.ImageColumn("封面", help="专辑封面"),
                    "预览": st.column_config.LinkColumn("试听预览"),
                    "商店链接": st.column_config.LinkColumn("商店链接"),
                },
            )

        with tab_cards:
            preview_rows = filtered_df.head(12).to_dict("records")
            if not preview_rows:
                st.info("当前筛选条件下没有可展示的歌曲。")
            else:
                for item in preview_rows:
                    cover_col, info_col = st.columns([1, 3])
                    with cover_col:
                        if item["封面"]:
                            st.image(item["封面"], use_container_width=True)
                    with info_col:
                        st.markdown(f"### {item['歌曲']}")
                        st.markdown(
                            f"**艺人**：{item['艺人']}  \n"
                            f"**专辑**：{item['专辑'] or '未知'}  \n"
                            f"**发布日期**：{item['发布日期']}  \n"
                            f"**类型**：{item['类型'] or '未知'}  \n"
                            f"**时长**：{item['时长(分钟)'] or '未知'} 分钟"
                        )
                        link_parts = []
                        if item["预览"]:
                            link_parts.append(f"[试听预览]({item['预览']})")
                        if item["商店链接"]:
                            link_parts.append(f"[商店页面]({item['商店链接']})")
                        if link_parts:
                            st.markdown(" | ".join(link_parts))
                    st.divider()

        with tab_picker:
            st.caption("勾选你真正想保留到最终歌单里的歌曲。")
            editable_df = st.data_editor(
                selection_df[
                    ["入选", "艺人", "歌曲", "专辑", "类型", "发布日期", "时长(分钟)", "预览", "商店链接", "track_id"]
                ],
                use_container_width=True,
                hide_index=True,
                disabled=["艺人", "歌曲", "专辑", "类型", "发布日期", "时长(分钟)", "预览", "商店链接", "track_id"],
                column_config={
                    "入选": st.column_config.CheckboxColumn("入选"),
                    "预览": st.column_config.LinkColumn("试听预览"),
                    "商店链接": st.column_config.LinkColumn("商店链接"),
                    "track_id": None,
                },
                key="track_picker_editor",
            )
            newly_selected_ids = editable_df.loc[editable_df["入选"], "track_id"].tolist()
            hidden_ids = set(results_df["track_id"]) - set(filtered_df["track_id"])
            preserved_ids = selected_track_ids.intersection(hidden_ids)
            st.session_state.selected_track_ids = sorted(set(newly_selected_ids).union(preserved_ids))

            picker_col_1, picker_col_2 = st.columns(2)
            with picker_col_1:
                if st.button("将当前筛选结果全部加入歌单", use_container_width=True):
                    st.session_state.selected_track_ids = sorted(
                        set(st.session_state.selected_track_ids).union(set(filtered_df["track_id"]))
                    )
                    st.rerun()
            with picker_col_2:
                if st.button("清空已选歌曲", use_container_width=True):
                    st.session_state.selected_track_ids = []
                    st.rerun()

        with tab_playlist:
            selected_df = results_df[results_df["track_id"].isin(st.session_state.selected_track_ids)].copy()
            selected_df = selected_df.sort_values(
                by=["发布日期", "艺人", "歌曲"], ascending=[False, True, True]
            )
            selected_playlist_text = build_playlist_text(selected_df)
            selected_csv_bytes = build_csv(exportable_dataframe(selected_df))

            if selected_df.empty:
                st.info("你还没有选择歌曲。先去“手动选歌”标签页勾选想保留的候选曲目。")
            else:
                st.success(f"当前最终歌单里已有 {len(selected_df)} 首歌。")

            st.text_area(
                "最终歌单文本",
                selected_playlist_text,
                height=240,
            )
            download_col_1, download_col_2, download_col_3 = st.columns(3)
            with download_col_1:
                st.download_button(
                    "下载最终歌单 TXT",
                    selected_playlist_text,
                    file_name="spotify_selected_tracks.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with download_col_2:
                st.download_button(
                    "下载最终歌单 CSV",
                    selected_csv_bytes,
                    file_name="spotify_selected_tracks.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with download_col_3:
                st.download_button(
                    "下载完整结果 CSV",
                    full_csv_bytes,
                    file_name="spotify_candidate_tracks.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            if not selected_df.empty:
                st.dataframe(
                    selected_df.drop(columns=["track_id"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "封面": st.column_config.ImageColumn("封面", help="专辑封面"),
                        "预览": st.column_config.LinkColumn("试听预览"),
                        "商店链接": st.column_config.LinkColumn("商店链接"),
                    },
                )

            render_transfer_card()

        with st.expander("查看本次抓取说明"):
            st.write(
                f"本次共监控 **{last_search_meta.get('artist_count', 0)}** 位艺人，"
                f"每位艺人最多抓取 **{last_search_meta.get('result_limit', result_limit)}** 条候选结果，"
                f"仅保留最近 **{last_search_meta.get('days', days)}** 天发布的歌曲。"
            )

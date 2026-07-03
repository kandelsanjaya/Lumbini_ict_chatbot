import os
import time

import streamlit as st
from dotenv import load_dotenv

from src.core import database as db
from src.ui import i18n
from src.ui.css import inject_css
from src.ui.themes import THEMES, DEFAULT_THEME
from src.core.rag import RagPipeline, sanitize_user_input
from src.tools import utils as chat_utils

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
TAVILY_KEY = os.getenv("TAVILY_API_KEY")

# ---- basic security tunables ----
RATE_LIMIT_MAX_MESSAGES = 15      # max messages...
RATE_LIMIT_WINDOW_SECONDS = 60    # ...per this many seconds, per session
MAX_MESSAGE_CHARS = 4000          # hard cap on a single message's length
SUMMARY_TRIGGER_EVERY = 12        # auto-summarize a conversation every N new messages


# =====================================================================
# PAGE CONFIG + DB INIT
# =====================================================================

st.set_page_config(
    page_title="DASA ai for web search ",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()

_chunks_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chunks.json")
if not os.path.exists(_chunks_path):
    try:
        from src.tools import search_index
        search_index.build_index()
    except Exception:
        pass  # optional TF-IDF index; the FAISS-based RAG pipeline works without it


# =====================================================================
# SESSION STATE
# =====================================================================

defaults = {
    "auth_user": None,
    "auth_mode": "login",
    "theme": DEFAULT_THEME,
    "dark_mode": True,
    "lang_code": "en",
    "active_conversation_id": None,
    "send_timestamps": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def T(key, **kwargs):
    return i18n.t(st.session_state.lang_code, key, **kwargs)


def _effective_theme_name():
    """Resolves the quick sun/moon dark_mode toggle against the chosen theme
    palette: if they disagree (e.g. toggle says light but a dark palette is
    selected), the toggle wins and swaps to the nearest matching palette."""
    current_is_dark = THEMES[st.session_state.theme]["is_dark"]
    if st.session_state.dark_mode and not current_is_dark:
        return DEFAULT_THEME
    if not st.session_state.dark_mode and current_is_dark:
        return "Nordic White"
    return st.session_state.theme


inject_css(THEMES[_effective_theme_name()])


# =====================================================================
# CACHED RAG PIPELINE
# =====================================================================

@st.cache_resource(show_spinner=False)
def get_pipeline():
    if not GROQ_KEY:
        return None
    return RagPipeline(
        groq_key=GROQ_KEY,
        tavily_key=TAVILY_KEY,
        data_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data.json"),
    )


# =====================================================================
# AUTH SCREENS
# =====================================================================

def _svg_icon(path_d: str, size: int = 20) -> str:
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true">'
        f'<path fill="currentColor" d="{path_d}"/></svg>'
    )


def _svg_user_badge() -> str:
    return _svg_icon(
        "M12 12c2.761 0 5-2.239 5-5S14.761 2 12 2 7 4.239 7 7s2.239 5 5 5zm0 2c-4.418 0-8 2.239-8 5v1h16v-1c0-2.761-3.582-5-8-5z",
        size=44,
    )


def _svg_badge_small() -> str:
    return _svg_icon(
        "M12 12c2.761 0 5-2.239 5-5S14.761 2 12 2 7 4.239 7 7s2.239 5 5 5zm0 2c-4.418 0-8 2.239-8 5v1h16v-1c0-2.761-3.582-5-8-5z"
    )


def _svg_at() -> str:
    return _svg_icon(
        "M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10c1.99 0 3.845-.58 5.405-1.583l-.955-1.687A7.965 7.965 0 0 1 12 20a8 8 0 1 1 8-8c0 1.06-.086 1.816-.31 2.316-.207.462-.462.622-.69.622-.35 0-.5-.278-.5-1V8.5h-1.8l-.13.9A3.49 3.49 0 0 0 12 8.5a3.5 3.5 0 1 0 2.36 6.09c.31.66.94 1.16 1.84 1.16 1.98 0 3.3-1.86 3.3-4.25C19.5 6.96 16.36 2 12 2zm0 12a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
    )


def _svg_key() -> str:
    return _svg_icon(
        "M7.5 14a4.5 4.5 0 1 1 4.23-6.01L22 8v4l-3 3h-3l-1.5 1.5-2-2L9.3 14H7.5zm2-4a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"
    )


def _svg_lock() -> str:
    return _svg_icon(
        "M17 9V7a5 5 0 0 0-10 0v2H5v15h14V9h-2zm-8 0V7a3 3 0 0 1 6 0v2H9zm3 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"
    )


def _uiverse_card_background() -> str:
    # starfield block (amir_6539) — used behind the main chat page only
    return """
    <div class="uiverse-stars-wrap" aria-hidden="true">
      <div class="container">
        <div id="stars"></div>
        <div id="stars2"></div>
        <div id="stars3"></div>
        <div></div>
      </div>
    </div>
    """


def render_field_label(icon_html: str, text: str):
    """Small icon + uppercase label chip sitting just above a text input —
    a clean, reliable stand-in for an 'icon inside the input' (which
    Streamlit's component model can't render, since markdown and widgets
    are always separate DOM siblings)."""
    st.markdown(
        f'<div class="agent-field"><span class="agent-input-icon">{icon_html}</span>{text}</div>',
        unsafe_allow_html=True,
    )


def _render_auth_left_panel(headline: str, sub: str):
    """Dark brand panel shown on the left of the split auth screen —
    logo lockup, headline/value-prop copy, and a footer line."""
    st.markdown(
        f"""
        <div class="auth-left">
            <div class="auth-left-wave"></div>
            <div class="auth-left-brand">
                <span class="mark">🎓</span>
                <span>LICT Campus Assistant</span>
            </div>
            <div class="auth-left-mid">
                <div class="auth-left-headline">{headline}</div>
                <div class="auth-left-sub">{sub}</div>
            </div>
            <div class="auth-left-footer">© 2026 LICT Campus Assistant. All rights reserved.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login():
    st.markdown('<div class="auth-shell">', unsafe_allow_html=True)
    left, right = st.columns([1, 1.15], gap="small")

    with left:
        _render_auth_left_panel(
            "Your AI guide to Lumbini ICT Campus.",
            "Ask questions, find resources, and get instant answers — "
            "sign in to pick up right where you left off.",
        )

    with right:
        st.markdown('<div class="auth-right">', unsafe_allow_html=True)
        st.markdown('<div class="auth-right-inner">', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="auth-right-heading">{T('login_title')}</div>
            <div class="auth-right-sub">{T('login_subtitle')}</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            render_field_label("", T("username"))
            username = st.text_input(
                T("username"), key="login_username", label_visibility="collapsed",
                placeholder=T("username"),
            )

            render_field_label("", T("password"))
            password = st.text_input(
                T("password"), key="login_password", type="password",
                label_visibility="collapsed", placeholder=T("password"),
            )

            submitted = st.form_submit_button(T("login_button"), use_container_width=True)

            if submitted:
                if not username.strip() or not password:
                    st.error("Please fill in all fields.")
                else:
                    user, message = db.verify_user(username, password)
                    if user:
                        st.session_state.auth_user = user
                        st.session_state.failed_login_count = 0
                        st.rerun()
                    else:
                        st.error(message)

        st.markdown('<div class="signin-wrap">', unsafe_allow_html=True)
        if st.button(T("switch_to_register"), key="go_to_register", use_container_width=False):
            st.session_state.auth_mode = "register"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # .auth-right-inner
        st.markdown('</div>', unsafe_allow_html=True)  # .auth-right

    st.markdown('</div>', unsafe_allow_html=True)  # .auth-shell


def render_register():
    st.markdown('<div class="auth-shell">', unsafe_allow_html=True)
    left, right = st.columns([1, 1.15], gap="small")

    with left:
        _render_auth_left_panel(
            "Join the LICT Campus community.",
            "Create an account to save your conversations and get "
            "personalized answers about courses, events, and campus life.",
        )

    with right:
        st.markdown('<div class="auth-right">', unsafe_allow_html=True)
        st.markdown('<div class="auth-right-inner">', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="auth-right-heading">{T('register_title')}</div>
            <div class="auth-right-sub">{T('register_subtitle')}</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("register_form", clear_on_submit=False):
            render_field_label("", T("display_name"))
            display_name = st.text_input(
                T("display_name"), key="reg_display_name", label_visibility="collapsed",
                placeholder=T("display_name"),
            )

            render_field_label("", T("username"))
            username = st.text_input(
                T("username"), key="reg_username", label_visibility="collapsed",
                placeholder=T("username"),
            )

            render_field_label("", T("password"))
            password = st.text_input(
                T("password"), key="reg_password", type="password",
                label_visibility="collapsed", placeholder=T("password"),
            )
            st.markdown('<div class="auth-hint">Minimum 6 characters.</div>', unsafe_allow_html=True)

            render_field_label("", T("confirm_password"))
            confirm = st.text_input(
                T("confirm_password"), key="reg_confirm", type="password",
                label_visibility="collapsed", placeholder=T("confirm_password"),
            )

            submitted = st.form_submit_button(T("register_button"), use_container_width=True)

            if submitted:
                if password != confirm:
                    st.error(T("register_error_mismatch"))
                else:
                    success, message = db.create_user(username, display_name, password)
                    if success:
                        user, _ = db.verify_user(username, password)
                        st.session_state.auth_user = user
                        st.rerun()
                    else:
                        st.error(message)

        st.markdown('<div class="signin-wrap">', unsafe_allow_html=True)
        if st.button(T("switch_to_login"), key="go_to_login", use_container_width=False):
            st.session_state.auth_mode = "login"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # .auth-right-inner
        st.markdown('</div>', unsafe_allow_html=True)  # .auth-right

    st.markdown('</div>', unsafe_allow_html=True)  # .auth-shell



def render_message(msg: dict):
    role = msg["role"]
    content = msg["content"]
    source = msg.get("source")
    score = msg.get("score")
    image_url = msg.get("image_url")
    blocked = bool(msg.get("blocked"))
    fetched_url = msg.get("fetched_url")

    css_role = "user" if role == "user" else "assistant"

    meta_html = ""
    if role == "assistant" and source:
        tag_class = {
            T("source_kb"): "source-tag-kb",
            T("source_web"): "source-tag-web",
            T("source_chat"): "source-tag-chat",
        }.get(source, "source-tag-img" if source in ("Image Search", "Web Fetch") else "source-tag-chat")
        no_score_sources = ("Image Search", "Blocked", "Web Fetch")
        score_html = f" · {T('similarity')}: {score:.2f}" if score is not None and source not in no_score_sources else ""
        # use real inline SVG icons instead of emoji
        if blocked:
            icon_svg = """
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" style="fill: currentColor;"> 
              <path d="M12 2l8 4v6c0 5-3.5 9.7-8 10-4.5-.3-8-5-8-10V6l8-4zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-1 11h2V11h-2v8z"/>
            </svg>
            """
        elif source == "Web Fetch":
            icon_svg = """
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" style="fill: currentColor;"> 
              <path d="M10 13h4l-1 8H11l-1-8zM6 7h12v4H6V7zm10-4a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"/>
            </svg>
            """
        else:
            icon_svg = """
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" style="fill: currentColor;">
              <circle cx="12" cy="12" r="4" />
            </svg>
            """

        meta_html = f'<div class="bubble-meta"><span class="{tag_class}">{icon_svg} {source}</span>{score_html}</div>'


    blocked_class = " blocked" if blocked else ""

    bubble_html = (
        f'<div class="chat-row {css_role}">'
        f'<div class="bubble {css_role}{blocked_class}">{content}{meta_html}</div>'
        f'</div>'
    )
    st.markdown(bubble_html, unsafe_allow_html=True)

    if image_url:
        st.markdown(
            f'<div class="img-card"><img src="{image_url}" alt="requested image"/></div>',
            unsafe_allow_html=True,
        )

    if fetched_url:
        st.markdown(
            f'<div class="glass-card" style="padding:0.7rem 1rem; margin-top:0.3rem;">'
            f'🔗 Source: <a href="{fetched_url}" target="_blank" rel="noopener noreferrer">{fetched_url}</a>'
            f'</div>',
            unsafe_allow_html=True,
        )


def make_conversation_title(first_message: str) -> str:
    title = first_message.strip().replace("\n", " ")
    return (title[:42] + "…") if len(title) > 42 else title


# =====================================================================
# MAIN CHAT APP
# =====================================================================

def render_app():
    pipeline = get_pipeline()
    user = st.session_state.auth_user

    # ---------------- Sidebar ----------------
    with st.sidebar:
        st.markdown(
            f"""<div style="text-align:center; padding: 0.5rem 0 1rem 0;">
                <div style="display:flex; align-items:center; justify-content:center; margin-bottom:0.15rem; color: inherit;">
                    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" style="fill: currentColor; color: var(--primary);">
                      <path d="M12 2s4 6 4 10a4 4 0 1 1-8 0c0-4 4-10 4-10zm0 18a6 6 0 0 0 6-6c0-6-6-14-6-14S6 8 6 14a6 6 0 0 0 6 6z"/>
                    </svg>
                </div>
                <div style="font-weight:700;">{user['display_name']}</div>
                <div style="font-size:0.75rem; opacity:0.7;">@{user['username']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

        if not GROQ_KEY:
            st.warning("⚠️ GROQ_API_KEY is not set — add it to your .env file to enable chat.")
        if not TAVILY_KEY:
            st.caption("ℹ️ TAVILY_API_KEY not set — live web search fallback is disabled.")

        if st.button(f"✦{T('new_chat')}", use_container_width=True):
            st.session_state.active_conversation_id = None
            st.rerun()

        st.markdown("---")

        lang_label = st.selectbox(
            T("language"),
            list(i18n.LANGUAGES.keys()),
            index=list(i18n.LANGUAGES.values()).index(st.session_state.lang_code),
        )
        new_lang_code = i18n.LANGUAGES[lang_label]
        if new_lang_code != st.session_state.lang_code:
            st.session_state.lang_code = new_lang_code
            st.rerun()

        theme_choice = st.selectbox(
            T("theme"), list(THEMES.keys()), index=list(THEMES.keys()).index(st.session_state.theme)
        )
        if theme_choice != st.session_state.theme:
            st.session_state.theme = theme_choice
            st.session_state.dark_mode = THEMES[theme_choice]["is_dark"]
            st.rerun()

        dark = st.toggle("🌙 " + T("theme"), value=st.session_state.dark_mode, key="dark_toggle_app")
        if dark != st.session_state.dark_mode:
            st.session_state.dark_mode = dark
            st.rerun()

        st.markdown("---")
        st.markdown(f"#### {T('history')}")

        conversations = db.list_conversations(user["id"])
        if conversations:
            for conv in conversations:
                is_active = conv["id"] == st.session_state.active_conversation_id
                cols = st.columns([5, 1])
                label = ("📍 " if is_active else "💬 ") + conv["title"]
                with cols[0]:
                    if st.button(label, key=f"conv_{conv['id']}", use_container_width=True):
                        st.session_state.active_conversation_id = conv["id"]
                        st.rerun()
                with cols[1]:
                    if st.button("🗑️", key=f"del_{conv['id']}", help=T("delete_chat")):
                        db.delete_conversation(conv["id"])
                        db.delete_summary(conv["id"])
                        if st.session_state.active_conversation_id == conv["id"]:
                            st.session_state.active_conversation_id = None
                        st.rerun()
        else:
            st.caption(T("no_history"))

        _export_history = db.get_messages(st.session_state.active_conversation_id) if st.session_state.active_conversation_id else []
        if _export_history:
            st.markdown("---")
            st.markdown("#### ⬇️ Export chat")
            exp_col1, exp_col2 = st.columns(2)
            md_export = chat_utils.export_chat_as_markdown(_export_history, title="LICT Campus Assistant Chat")
            json_export = chat_utils.export_chat_as_json(_export_history)
            with exp_col1:
                st.download_button("📄 .md", md_export, file_name="chat_export.md", use_container_width=True)
            with exp_col2:
                st.download_button("🧾 .json", json_export, file_name="chat_export.json", use_container_width=True)

        st.markdown("---")
        if st.button(f"🚪 {T('logout')}", use_container_width=True):
            st.session_state.auth_user = None
            st.session_state.active_conversation_id = None
            st.rerun()

    # background for chat page
    st.markdown(_uiverse_card_background(), unsafe_allow_html=True)

    # ---------------- Header ----------------
    st.markdown(
        f"""
        <div class="hero-title"> {T('title')}</div>
        <div class="hero-subtitle">{T('subtitle')}</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <span class="badge">⚡ CHAT BOT</span>
        <span class="badge">🎓 Lumbini ICT Campus KB</span>
       
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    # ---------------- Active conversation & message history ----------------
    conv_id = st.session_state.active_conversation_id
    history = db.get_messages(conv_id) if conv_id else []

    chat_container = st.container()
    with chat_container:
        if not history:
            st.markdown(
                f"""
                <div class="glass-card" style="text-align:center;">
                    <div style="font-size:2rem;">💬</div>
                    <p class="hero-subtitle">
                        {T('greeting_returning', name=user['display_name'])}
                    </p>
                    <p style="font-size:0.85rem; opacity:0.75;">
                        Try: "what programs does Lumbini ICT Campus offer?" · "show me an image of mountains" ·
                        paste a URL to summarize it · or just say hi
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif conv_id:
            summary = db.get_summary(conv_id)
            if summary:
                st.markdown(
                    f'<div class="summary-chip"><b>🧠 {T("history")} recap</b><br>{summary["summary"]}</div>',
                    unsafe_allow_html=True,
                )
        for msg in history:
            render_message(msg)

    # ---------------- Input box (voice + upload) ----------------
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    col1, col2 = st.columns([5, 1])
    with col1:
        st.markdown('<div class="glow-input-wrap">', unsafe_allow_html=True)
        question = st.text_input(
            T("ask_placeholder"),
            key="chat_input",

            placeholder=T("ask_placeholder"),
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # voice assistant (client-side speech-to-text)
        st.markdown(
            """
            <div class="agent-tools">
              <button type="button" class="agent-icon-btn" id="micBtn" onclick="window.__lctMicToggle && window.__lctMicToggle()">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-4.08A7 7 0 0 0 19 11h-2Z"/></svg>
                <span id="micLabel">Voice</span>
              </button>

              <div style="flex:1; min-width: 160px; text-align:right;">
                <span style="opacity:0.75; font-size:0.82rem;">Tip: mic fills the input automatically.</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # file upload (.txt/.md) merged into prompt as context
        uploaded = st.file_uploader("Attach knowledge (.txt / .md)", type=["txt", "md"], key="chat_upload")

        if uploaded is not None:
            st.caption(f"Attached: {uploaded.name} ({uploaded.size} bytes)")
            try:
                _uploaded_text = uploaded.read().decode("utf-8", errors="ignore")
            except Exception:
                _uploaded_text = ""
        else:
            _uploaded_text = None

        # inject JS for speech-to-text
        st.components.v1.html(
            """
            <script>
              (function(){
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if(!SpeechRecognition){
                  const el = document.getElementById('micLabel');
                  if(el) el.textContent = 'Voice not supported';
                  return;
                }
                let rec = new SpeechRecognition();
                rec.continuous = false;
                rec.interimResults = true;
                rec.lang = 'en-US';

                let isListening = false;

                function setLabel(on){
                  const btn = document.getElementById('micBtn');
                  const el = document.getElementById('micLabel');
                  if(btn){
                    btn.classList.toggle('listening-glow', on);
                  }
                  if(el){
                    el.textContent = on ? 'Listening...' : 'Voice';
                  }
                }

                function findInput(){
                  // Streamlit inputs are hard to target reliably; we use placeholder match as fallback.
                  // Primary: look for input with name containing "chat_input".
                  let input = document.querySelector('input[name="chat_input"]');
                  if(input) return input;
                  // fallback: first text input in the main view
                  const inputs = Array.from(document.querySelectorAll('input'));
                  for(const i of inputs){
                    if(i && i.type==='text' && (i.getAttribute('aria-label')||'').toLowerCase().includes('message')) return i;
                  }
                  return null;
                }

                rec.onresult = function(event){
                  let transcript = '';
                  for(let i=event.resultIndex; i<event.results.length; i++){
                    transcript += event.results[i][0].transcript;
                  }
                  const input = findInput();
                  if(input){
                    input.value = transcript;
                    input.dispatchEvent(new Event('input', { bubbles:true }));
                  }
                };

                rec.onend = function(){
                  isListening = false;
                  setLabel(false);
                };

                window.__lctMicToggle = function(){
                  if(!SpeechRecognition) return;
                  if(isListening){
                    try{ rec.stop(); }catch(e){}
                    isListening = false;
                    setLabel(false);
                    return;
                  }
                  isListening = true;
                  setLabel(true);
                  try{ rec.start(); }catch(e){
                    isListening = false;
                    setLabel(false);
                  }
                };

                setLabel(false);
              })();
            </script>
            """,
            height=0,
        )

    with col2:
        send_clicked = st.button(f"✨ {T('ask_button')}", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if send_clicked:
        if not question.strip() and _uploaded_text is None:
            st.warning(T("warning_empty"))
            st.stop()

        if pipeline is None:

            st.error("Chat is disabled until GROQ_API_KEY is configured in your .env file.")
            st.stop()

        # ---- basic per-session rate limiting (security: prevent spamming the LLM/API) ----
        now = time.time()
        recent = [t for t in st.session_state.get("send_timestamps", []) if now - t < RATE_LIMIT_WINDOW_SECONDS]
        if len(recent) >= RATE_LIMIT_MAX_MESSAGES:
            st.warning(
                f"You're sending messages too quickly — please wait a few seconds. "
                f"(limit: {RATE_LIMIT_MAX_MESSAGES} messages / {RATE_LIMIT_WINDOW_SECONDS}s)"
            )
            st.stop()
        recent.append(now)
        st.session_state.send_timestamps = recent

        # ---- sanitize before storing/rendering (security: prevent stored XSS) ----
        clean_question = sanitize_user_input(question)

        # merge uploaded file text into the prompt (txt/md only)
        if _uploaded_text:
            safe_file_text = sanitize_user_input(_uploaded_text)
            if safe_file_text:
                clean_question = (
                    f"{clean_question}\n\n[Attached file content]\n{safe_file_text[:12000]}"
                )

        if len(clean_question) > MAX_MESSAGE_CHARS:
            clean_question = clean_question[:MAX_MESSAGE_CHARS]


        if conv_id is None:
            conv_id = db.create_conversation(user["id"], title=make_conversation_title(clean_question))
            st.session_state.active_conversation_id = conv_id

        db.add_message(conv_id, "user", clean_question)

        with st.spinner(T("generating")):
            result = pipeline.answer(
                question=clean_question,
                history=history,
                lang_name=lang_label,
                user_name=user["display_name"],
            )

        source_label_map = {
            "Knowledge Base": T("source_kb"),
            "Web Search": T("source_web"),
            "Conversational": T("source_chat"),
            "Image Search": "Image Search",
            "Web Fetch": "Web Fetch",
            "Blocked": "Blocked",
        }
        source_label = source_label_map.get(result["source"], result["source"])

        db.add_message(
            conv_id,
            "assistant",
            result["answer"],
            source=source_label,
            score=result.get("score"),
            image_url=result.get("image_url"),
            fetched_url=result.get("fetched_url"),
            blocked=result.get("blocked", False),
        )

        # ---- auto-summarize long conversations (background-ish, best-effort) ----
        total_messages = db.get_message_count(conv_id)
        if total_messages % SUMMARY_TRIGGER_EVERY == 0:
            existing = db.get_summary(conv_id)
            already_covered = existing["message_count_at_summary"] if existing else 0
            if total_messages - already_covered >= SUMMARY_TRIGGER_EVERY:
                full_history = db.get_messages(conv_id)
                new_slice = full_history[already_covered:]
                try:
                    new_summary = pipeline.summarize_conversation(
                        new_slice, previous_summary=existing["summary"] if existing else None
                    )
                    db.upsert_summary(conv_id, new_summary, total_messages)
                except Exception:
                    pass  # summarization is a nice-to-have; never break the chat over it

        del st.session_state["chat_input"]
        st.rerun()

    st.markdown(f'<div class="footer-note">{T("footer")}</div>', unsafe_allow_html=True)


# =====================================================================
# ROUTER
# =====================================================================

if st.session_state.auth_user is None:
    if st.session_state.auth_mode == "register":
        render_register()
    else:
        render_login()
else:
    render_app()
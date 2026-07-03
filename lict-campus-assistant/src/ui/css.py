"""
css.py — CSS injection for the Hybrid AI Chatbot.

Builds one <style> block per rerun from the active theme dict (themes.py).
Includes: animated gradient/ember background, glassmorphism cards, ChatGPT-style
chat bubbles, image result cards, moderation/warning banners, sidebar styling,
and rich keyframe animation (flame flicker, shimmer, fade/slide entrances,
pulsing glow, bouncing typing dots, button hover-lift).
"""

import streamlit as st


def inject_css(theme: dict):
    c = theme

    css = f"""
    <style>

    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    .stApp {{
        background: {c['bg_grad']};
        background-attachment: fixed;
        position: relative;
        overflow-x: hidden;
    }}

    [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"] {{
        position: relative;
        z-index: 2;
    }}

    /* ---- ambient floating glow blobs ---- */
    .stApp::before, .stApp::after {{
        content: "";
        position: fixed;
        width: 520px;
        height: 520px;
        border-radius: 50%;
        filter: blur(100px);
        opacity: 0.30;
        z-index: 0;
        pointer-events: none;
        animation: float1 14s ease-in-out infinite alternate;
    }}
    .stApp::before {{
        background: {c['primary']};
        top: -140px;
        left: -120px;
    }}
    .stApp::after {{
        background: {c['accent']};
        bottom: -150px;
        right: -110px;
        animation: float2 17s ease-in-out infinite alternate;
    }}

    @keyframes float1 {{
        0%   {{ transform: translate(0, 0) scale(1); }}
        100% {{ transform: translate(70px, 90px) scale(1.2); }}
    }}
    @keyframes float2 {{
        0%   {{ transform: translate(0, 0) scale(1); }}
        100% {{ transform: translate(-60px, -70px) scale(1.15); }}
    }}
    @keyframes flicker {{
        0%, 100% {{ filter: drop-shadow(0 0 10px {c['glow']}) brightness(1); }}
        50%      {{ filter: drop-shadow(0 0 22px {c['glow']}) brightness(1.18); }}
    }}
    @keyframes fadeInUp {{
        0%   {{ opacity: 0; transform: translateY(16px); }}
        100% {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeInScale {{
        0%   {{ opacity: 0; transform: scale(0.94); }}
        100% {{ opacity: 1; transform: scale(1); }}
    }}
    @keyframes fadeInLeft {{
        0%   {{ opacity: 0; transform: translateX(-12px); }}
        100% {{ opacity: 1; transform: translateX(0); }}
    }}
    @keyframes fadeInRight {{
        0%   {{ opacity: 0; transform: translateX(12px); }}
        100% {{ opacity: 1; transform: translateX(0); }}
    }}
    @keyframes shimmer {{
        0%   {{ background-position: -400px 0; }}
        100% {{ background-position: 400px 0; }}
    }}
    @keyframes pulseGlow {{
        0%, 100% {{ box-shadow: 0 0 16px {c['glow']}; }}
        50%      {{ box-shadow: 0 0 34px {c['glow']}; }}
    }}
    @keyframes typingDot {{
        0%, 80%, 100% {{ opacity: 0.25; transform: translateY(0); }}
        40% {{ opacity: 1; transform: translateY(-4px); }}
    }}
    @keyframes shake {{
        0%, 100% {{ transform: translateX(0); }}
        20%, 60% {{ transform: translateX(-5px); }}
        40%, 80% {{ transform: translateX(5px); }}
    }}

    h1, h2, h3 {{ font-family: 'Sora', sans-serif !important; color: {c['text']} !important; }}

    .hero-title {{
        font-family: 'Sora', sans-serif;
        font-weight: 800;
        font-size: 2.5rem;
        background: linear-gradient(90deg, {c['primary']}, {c['primary2']}, {c['accent']});
        background-size: 300% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: shimmer 6s linear infinite, fadeInUp 0.6s ease;
        margin-bottom: 0.1rem;
    }}
    .hero-subtitle {{
        color: {c['subtext']};
        font-size: 1.0rem;
        margin-bottom: 1.2rem;
        animation: fadeInUp 0.8s ease;
    }}

    .glass-card {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 20px;
        padding: 1.6rem 1.8rem;
        backdrop-filter: blur(18px);
       
        animation: fadeInUp 0.5s ease in out ;
        margin-bottom: 1.2rem;
    }}

    .badge {{
        display: inline-block;
        padding: 0.32rem 0.95rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        color: white;
        background: linear-gradient(90deg, {c['primary']}, {c['primary2']});
        letter-spacing: 0.3px;
        animation: pulseGlow 2.6s ease-in-out infinite;
        margin-right: 0.4rem;
    }}

    /* ---- Chat bubbles ---- */
    .chat-row {{
        display: flex;
        margin-bottom: 0.9rem;
        animation: fadeInUp 0.35s ease;
    }}
    .chat-row.user {{ justify-content: flex-end; }}
    .chat-row.assistant {{ justify-content: flex-start; }}

    .bubble {{
        max-width: 78%;
        padding: 0.9rem 1.2rem;
        border-radius: 18px;
        line-height: 1.6;
        font-size: 0.97rem;
        box-shadow: {c['shadow']};
        animation: fadeInScale 0.3s ease;
    }}
    .bubble.user {{
        background: {c['user_bubble']};
        color: white;
        border-bottom-right-radius: 4px;
    }}
    .bubble.assistant {{
        background: {c['assistant_bubble']};
        color: {c['text']};
        border: 1px solid {c['card_border']};
        border-bottom-left-radius: 4px;
    }}
    .bubble.blocked {{
        border: 1.5px solid #ff4d4d !important;
        animation: shake 0.45s ease;
    }}

    .bubble-meta {{
        font-size: 0.7rem;
        opacity: 0.65;
        margin-top: 0.4rem;
    }}

    .typing-indicator {{
        display: inline-flex;
        gap: 4px;
        padding: 0.6rem 0.9rem;
    }}
    .typing-indicator span {{
        width: 6px; height: 6px;
        border-radius: 50%;
        background: {c['primary']};
        animation: typingDot 1.2s infinite;
    }}
    .typing-indicator span:nth-child(2) {{ animation-delay: 0.15s; }}
    .typing-indicator span:nth-child(3) {{ animation-delay: 0.3s; }}

    /* ---- image results ---- */
    .img-card {{
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid {c['card_border']};
        margin-top: 0.6rem;
        animation: fadeInScale 0.4s ease;
        box-shadow: {c['shadow']};
    }}
    .img-card img {{
        width: 100%;
        display: block;
        transition: transform 0.4s ease;
    }}
    .img-card:hover img {{ transform: scale(1.04); }}

    /* ---- moderation banner ---- */
    .mod-banner {{
        border-radius: 14px;
        padding: 0.9rem 1.2rem;
        background: linear-gradient(90deg, rgba(255,77,77,0.15), rgba(255,122,24,0.1));
        border: 1.5px solid #ff4d4d;
        color: {c['text']};
        animation: shake 0.5s ease, fadeInUp 0.4s ease;
        margin-bottom: 1rem;
        font-weight: 500;
    }}

    /* ---- Inputs ---- */
    .stTextInput input, .stTextArea textarea {{
        background: {c['input_bg']} !important;
        color: {c['text']} !important;
        border-radius: 14px !important;
        border: 1.5px solid {c['card_border']} !important;
        padding: 0.7rem 1rem !important;
        transition: all 0.25s ease;
    }}
    .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color: {c['primary']} !important;
        box-shadow: 0 0 0 3px {c['glow']} !important;
    }}

    /* ---- Buttons ---- */
    .stButton button {{
        background: linear-gradient(90deg, {c['primary']}, {c['primary2']});
        color: white;
        border: none;
        border-radius: 14px;
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        letter-spacing: 0.2px;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        box-shadow: 0 4px 14px {c['glow']};
    }}
    .stButton button:hover {{
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 8px 24px {c['glow']};
    }}
    .stButton button:active {{ transform: translateY(0px) scale(0.98); }}

    button[kind="secondary"] {{
        background: transparent !important;
        color: {c['text']} !important;
        border: 1px solid {c['card_border']} !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }}
    button[kind="secondary"]:hover {{
        background: {c['card_bg']} !important;
        border-color: {c['primary']} !important;
        transform: none !important;
    }}

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {{
        background: {c['card_bg']};
        backdrop-filter: blur(20px);
        border-right: 1px solid {c['card_border']};
    }}
    section[data-testid="stSidebar"] * {{ color: {c['text']} !important; }}

    div[data-baseweb="select"] > div {{
        background: {c['input_bg']} !important;
        border-radius: 12px !important;
        border: 1.5px solid {c['card_border']} !important;
        color: {c['text']} !important;
    }}

    [data-testid="stSlider"] [role="slider"] {{
        background: {c['primary']} !important;
        box-shadow: 0 0 10px {c['glow']} !important;
    }}
    [data-testid="stAlert"] {{
        border-radius: 14px !important;
        border: 1px solid {c['card_border']} !important;
        background: {c['card_bg']} !important;
    }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header[data-testid="stHeader"] {{background: transparent;}}

    .footer-note {{
        text-align: center;
        color: {c['subtext']};
        font-size: 0.8rem;
        margin-top: 2rem;
        opacity: 0.7;
    }}

    /* star background layer (Uiverse) */
    .uiverse-stars-wrap {{
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }}
    .uiverse-stars-wrap .container {{
        height: 100%;
        width: 100%;
    }}
    .uiverse-stars-wrap #stars,
    .uiverse-stars-wrap #stars2,
    .uiverse-stars-wrap #stars3 {{
        position: absolute;
        top: 0;
        left: 0;
    }}

    /* bring main UI above background */
    [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"],
    .stApp > div {{
        z-index: 2;
    }}


    .conv-active {{
        border-radius: 12px;
        background: linear-gradient(90deg, {c['primary']}22, {c['primary2']}22);
        border: 1px solid {c['primary']}55;
        padding: 0.1rem 0.4rem;
    }}

    .auth-icon {{
        font-size: 2.2rem;
        animation: flicker 2.2s ease-in-out infinite;
        color: {c['primary']};
        display: flex;
        align-items: center;
        justify-content: center;
        height: 54px;
    }}
    .auth-icon svg {{
        width: 44px;
        height: 44px;
        fill: currentColor;
    }}


    .source-tag-kb {{ color: {c['primary']}; font-weight: 600; }}
    .source-tag-web {{ color: {c['accent']}; font-weight: 600; }}
    .source-tag-chat {{ color: {c['primary2']}; font-weight: 600; }}
    .source-tag-img {{ color: {c['primary2']}; font-weight: 600; }}

    /* =====================================================================
       SUN/MOON DARK-MODE TOGGLE
       Reskins Streamlit's native st.toggle (a real checkbox under the hood)
       to look like the Uiverse "theme-switch" sun/moon design, so it's a
       fully working control (not just decorative HTML).
    ===================================================================== */
    div[data-testid="stToggle"] label[data-baseweb="checkbox"] {{
        transform: scale(1.15);
        transform-origin: left center;
    }}
    div[data-testid="stToggle"] [data-baseweb="checkbox"] > div:first-child {{
        background: linear-gradient(135deg, #3D7EAE, #5aa3d0) !important;
        border: none !important;
        width: 3.6em !important;
        height: 1.7em !important;
        border-radius: 999px !important;
        box-shadow: 0 0.06em 0.06em rgba(0,0,0,.25) inset, 0 0.06em 0.12em rgba(255,255,255,.5);
        position: relative;
        transition: background 0.4s ease;
    }}
    div[data-testid="stToggle"] input:checked ~ div:first-child {{
        background: linear-gradient(135deg, #1D1F2C, #2b2e42) !important;
    }}
    div[data-testid="stToggle"] [data-baseweb="checkbox"] > div:first-child::after {{
        content: "☀️";
        position: absolute;
        left: 0.18em;
        top: 50%;
        transform: translateY(-50%);
        font-size: 0.85em;
        width: 1.35em;
        height: 1.35em;
        border-radius: 50%;
        background: {c['card_bg']};
        display: flex;
        align-items: center;
        justify-content: center;
        transition: left 0.35s cubic-bezier(0,-0.02,0.4,1.25);
        box-shadow: 0 0.1em 0.2em rgba(0,0,0,.35);
    }}
    div[data-testid="stToggle"] input:checked ~ div:first-child::after {{
        content: "🌙";
        left: calc(100% - 1.53em);
    }}

    /* =====================================================================
       PILL / SEGMENTED NAV
       Reskins st.radio(horizontal=True) into a rounded pill switcher, like
       the Uiverse "radio-input" segmented control (Home/Profile/Settings).
    ===================================================================== */
    div[data-testid="stRadio"] > div {{
        display: inline-flex;
        gap: 0;
        background: {c['input_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 999px;
        padding: 4px;
        box-shadow: 0 8px 20px rgba(0,0,0,.15);
    }}
    div[data-testid="stRadio"] label {{
        padding: 0.5rem 1.2rem !important;
        border-radius: 999px !important;
        margin: 0 !important;
        cursor: pointer;
        transition: all 0.25s ease;
        font-weight: 600;
    }}
    div[data-testid="stRadio"] label:has(input:checked) {{
        background: linear-gradient(90deg, {c['primary']}, {c['primary2']}) !important;
        box-shadow: 0 4px 14px {c['glow']};
    }}
    div[data-testid="stRadio"] label:has(input:checked) p {{
        color: white !important;
    }}
    div[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {{
        margin: 0 !important;
    }}

    /* =====================================================================
       GLOW SEARCH / CHAT INPUT
       Wraps the chat text input in a rotating conic-gradient glow border,
       echoing the Uiverse "poda" search bar.
    ===================================================================== */
    .glow-input-wrap {{
        position: relative;
        border-radius: 16px;
        padding: 2px;
        background: conic-gradient(from 180deg, {c['primary']}, {c['accent']}, {c['primary2']}, {c['primary']});
        background-size: 200% 200%;
        animation: glowRotate 6s linear infinite;
        box-shadow: 0 0 24px {c['glow']};
    }}
    .glow-input-wrap > div {{
        background: {c['input_bg'] if c['is_dark'] else '#ffffff'};
        border-radius: 14px;
    }}
    @keyframes glowRotate {{
        0%   {{ background-position: 0% 50%; }}
        100% {{ background-position: 200% 50%; }}
    }}
    .glow-input-wrap .stTextInput input {{
        border: none !important;
        box-shadow: none !important;
    }}

    /* =====================================================================
       AUTH FORM CARD (login / register)
       Dark glass card with a cyan accent title + underline dot-pulse,
       echoing the Uiverse "form" component. Wraps around Streamlit's
       native st.form so the fields stay fully functional.
    ===================================================================== */
    .auth-form-card {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 22px;
        padding: 1.6rem 2rem 0.9rem 2rem;
        backdrop-filter: blur(18px);
        box-shadow: {c['shadow']};
        animation: fadeInScale 0.5s ease;
        position: relative;
        overflow: hidden;
    }}

    /* unique Uiverse-like login card glow frame */
    .auth-form-card::before {{
        content: "";
        position: absolute;
        inset: -2px;
        border-radius: 24px;
        background: conic-gradient(from 180deg, {c['primary']}, {c['accent']}, {c['primary2']}, {c['primary']});
        opacity: 0.35;
        filter: blur(0.2px);
        z-index: 0;
        animation: glowRotate 7s linear infinite;
    }}
    .auth-form-card > * {{
        position: relative;
        z-index: 1;
    }}

   
    /* Uiverse-like .form variant inside Streamlit card */
    .agent-form {{
        display: flex;
        flex-direction: column;
        gap: 12px;
    }}
    .agent-heading {{
        text-align: center;
        margin: 0.25rem 0 0.2rem 0;
        color: rgb(255, 255, 255);
        font-size: 1.12em;
        letter-spacing: 0.2px;
        font-weight: 800;
    }}
    .agent-field {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.55em;
        border-radius: 18px;
        padding: 0.65em 0.9em;
        border: none;
        outline: none;
        color: white;
        background-color: rgba(23,23,23,0.35);
        box-shadow: inset 2px 5px 10px rgba(0,0,0,0.35);
    }}
    .agent-input-icon {{
        height: 1.3em;
        width: 1.3em;
        fill: currentColor;
        color: {c['text']};
        opacity: 0.95;
        flex: 0 0 auto;
    }}
    .agent-input {{
        background: none !important;
        border: none !important;
        outline: none !important;
        width: 100%;
        color: {c['text']} !important;
        font-size: 0.98rem;
    }}

    /* make Streamlit text inputs blend into agent-input wrapper */
    .agent-field .stTextInput input,
    .agent-field input {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}

    .agent-actions {{
        display: flex;
        justify-content: center;
        flex-direction: row;
        gap: 10px;
        margin-top: 0.9rem;
        flex-wrap: wrap;
    }}

    .agent-button1,
    .agent-button2 {{
        padding: 0.55em 1.1em;
        border-radius: 12px;
        border: none;
        outline: none;
        transition: .28s ease-in-out;
        background-color: rgba(37,37,37,0.65);
        color: {c['text']};
        border: 1px solid {c['card_border']};
        box-shadow: 0 8px 22px rgba(0,0,0,0.15);
        font-weight: 700;
    }}
    .agent-button1:hover,
    .agent-button2:hover {{
        background-color: rgba(0,0,0,0.75);
        color: white;
        transform: translateY(-1px);
    }}

    .agent-button3 {{
        margin-top: 0.25rem;
        padding: 0.55em 1.1em;
        border-radius: 12px;
        border: none;
        outline: none;
        transition: .28s ease-in-out;
        background-color: rgba(37,37,37,0.65);
        color: {c['text']};
        border: 1px solid {c['card_border']};
        font-weight: 700;
    }}
    .agent-button3:hover {{
        background-color: rgba(255,0,0,0.18);
        color: white;
        border-color: rgba(255,77,77,0.7);
        transform: translateY(-1px);
    }}

    /* voice + upload UI */
    .agent-tools {{
        display: flex;
        align-items: center;
        gap: 10px;
        justify-content: space-between;
        flex-wrap: wrap;
        margin-top: 0.6rem;
    }}

    .agent-icon-btn {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 0.55em 0.95em;
        border-radius: 12px;
        border: 1px solid {c['card_border']};
        background: rgba(37,37,37,0.55);
        color: {c['text']};
        cursor: pointer;
        transition: .25s ease-in-out;
        font-weight: 700;
        box-shadow: 0 10px 26px rgba(0,0,0,0.12);
    }}
    .agent-icon-btn:hover {{
        transform: translateY(-1px);
        background: rgba(0,0,0,0.7);
        color: white;
        border-color: {c['primary2']};
    }}
    .agent-icon-btn svg {{ width: 18px; height: 18px; fill: currentColor; }}

    .listening-glow {{
        border-color: {c['primary']};
        box-shadow: 0 0 0 4px {c['primary']}22, 0 0 22px {c['glow']};
    }}

    /* typing dots (fake low-latency feedback) */
    .typing-dots {{
        display: inline-flex;
        gap: 6px;
        align-items: center;
    }}
    .typing-dots i {{
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: {c['primary']};
        animation: typingDot 1.2s infinite;
        opacity: 0.9;
    }}
    .typing-dots i:nth-child(2) {{ animation-delay: 0.15s; }}
    .typing-dots i:nth-child(3) {{ animation-delay: 0.3s; }}

    .auth-form-title {{
        font-family: 'Sora', sans-serif;
        font-size: 1.7rem;
        font-weight: 700;
        position: relative;
        padding-left: 1.6rem;
        color: {c['primary']};
        margin-bottom: 0.2rem;
    }}
    .auth-form-title::before, .auth-form-title::after {{
        content: "";
        position: absolute;
        left: 0;
        top: 50%;
        transform: translateY(-50%);
        width: 0.85rem;
        height: 0.85rem;
        border-radius: 50%;
        background: {c['primary']};
    }}
    .auth-form-title::after {{
        animation: pulseDot 1.4s linear infinite;
    }}
    @keyframes pulseDot {{
        from {{ transform: translateY(-50%) scale(0.9); opacity: 1; }}
        to   {{ transform: translateY(-50%) scale(1.9); opacity: 0; }}
    }}
    .auth-form-message {{
        color: {c['subtext']};
        font-size: 0.9rem;
        margin-bottom: 0.8rem;
    }}

    /* =====================================================================
       CONVERSATION SUMMARY CHIP
    ===================================================================== */
    .summary-chip {{
        background: linear-gradient(135deg, {c['primary']}18, {c['primary2']}18);
        border: 1px solid {c['primary']}44;
        border-radius: 14px;
        padding: 0.7rem 0.9rem;
        font-size: 0.78rem;
        line-height: 1.55;
        color: {c['text']};
        margin-bottom: 0.6rem;
        animation: fadeInUp 0.4s ease;
    }}
    .summary-chip b {{ color: {c['primary']}; }}

    /* =====================================================================
       MOBILE RESPONSIVENESS
    ===================================================================== */
    @media (max-width: 768px) {{
        .hero-title {{ font-size: 1.7rem !important; }}
        .hero-subtitle {{ font-size: 0.85rem !important; }}
        .glass-card {{ padding: 1.1rem 1.1rem !important; }}
        .bubble {{ max-width: 92% !important; font-size: 0.92rem !important; }}
        .auth-form-card {{ padding: 1.2rem 1.2rem 0.2rem 1.2rem !important; }}
        div[data-testid="stRadio"] label {{ padding: 0.4rem 0.75rem !important; font-size: 0.85rem; }}
        [data-testid="stSidebar"] {{ min-width: 100% !important; }}
        .badge {{ font-size: 0.68rem; padding: 0.24rem 0.7rem; }}
    }}
    @media (max-width: 480px) {{
        .hero-title {{ font-size: 1.4rem !important; }}
        .bubble {{ max-width: 96% !important; padding: 0.7rem 0.9rem !important; }}
        .auth-icon {{ font-size: 2.1rem !important; }}
    }}

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
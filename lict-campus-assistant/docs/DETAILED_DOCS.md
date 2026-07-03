# LICT Campus Assistant — Detailed Project Documentation

This document explains how every part of LICT Campus Assistant works under the hood — the theming
system in particular, since that's where the trickiest bugs live in a Streamlit app — plus
every other major feature, file by file.

---

## 1. The Theming System (in detail)

### 1.1 Why theming is hard in Streamlit specifically

Streamlit isn't a normal web framework — you don't control the HTML document directly.
Every `st.markdown(..., unsafe_allow_html=True)` call gets sanitized and injected into a
shared DOM that Streamlit itself manages, and two things trip people up constantly:

1. **`<script>` tags get silently stripped** from `st.markdown()` output. If you try to
   toggle a theme by running JavaScript that sets `document.documentElement.setAttribute
   ('data-theme', 'dark')`, that script never executes. There's no error — it just quietly
   does nothing, which is the worst kind of bug because the UI looks "almost right."
2. **`.streamlit/config.toml`'s `[theme] base` setting controls native widget chrome**
   (selectboxes, sliders, tabs, checkboxes, labels) independently of any custom CSS you
   write. If you hardcode `base = "dark"`, every native widget will render light text
   permanently, even when your custom CSS is trying to show a light theme. This is a
   separate theming layer from the one you control with CSS.

### 1.2 How LICT Campus Assistant actually solves it

Instead of fighting the DOM with JavaScript, the theme switch is handled **entirely in
Python, on every rerun**:

```python
def load_css():
    with open("style.css") as f:
        css = f.read()

    if st.session_state.theme == "dark":
        theme_vars = """
        :root {
            --bg-primary: #08090d; --bg-secondary: #0f1117; --bg-card: #14161e;
            --accent: #00f0ff; --accent-2: #8b5cf6; ...
        }
        """
    else:
        theme_vars = """
        :root {
            --bg-primary: #f4f6fb; --bg-secondary: #ffffff; --bg-card: #ffffff;
            --accent: #0091ff; --accent-2: #7c3aed; ...
        }
        """
    st.markdown(f"<style>{theme_vars}\n{css}</style>", unsafe_allow_html=True)
```

Key ideas:

- **`st.session_state.theme`** is the single source of truth — set once via the sidebar
  `st.toggle()`, persisted across reruns automatically by Streamlit's session state.
- Every rerun, Python decides which set of CSS custom properties (`--bg-primary`,
  `--accent`, `--user-bubble`, etc.) to print into a `<style>` block. CSS variables, unlike
  attribute selectors, don't depend on any JS running — they're just text in a stylesheet
  that the browser parses immediately.
- `style.css` itself never hardcodes a color. Every rule references `var(--something)`,
  so the *same* stylesheet renders correctly in both modes — the only thing that changes
  is which values those variables resolve to.
- `.streamlit/config.toml` deliberately has **no `[theme]` section** at all, so Streamlit
  falls back to letting CSS fully own the native widget colors. To make that work, `style.css`
  includes explicit overrides for native components Streamlit renders outside your control:
  `[data-baseweb="select"]`, `[data-testid="stSlider"]`, `[data-baseweb="tab-list"]`,
  `[data-testid="stAlert"]`, `[data-testid="stCaptionContainer"]`, input/textarea elements,
  and so on — each pinned to the theme variables with `!important` where Streamlit's own
  specificity would otherwise win.

### 1.3 The visual language

| Element | Dark mode | Light mode |
|---|---|---|
| Background | near-black (`#08090d`) with a faint radial cyan/violet glow | off-white (`#f4f6fb`), no glow |
| Accent gradient | cyan → violet (`#00f0ff` → `#8b5cf6`) | blue → violet (`#0091ff` → `#7c3aed`) |
| Bot bubble | dark card (`#14161e`) with a 1px border | light gray card (`#eef1f7`) |
| User bubble | gradient fill, glowing cyan shadow | gradient fill, softer blue shadow |
| Headings | Space Grotesk, gradient text-fill on brand name | same |
| Body text | Inter | same |

Light mode is **not** just a CSS invert of dark mode — it uses its own deliberately chosen
palette so contrast and "vibe" both stay correct (inverting dark themes naively usually
produces washed-out, low-contrast UIs).

### 1.4 Animations tied to theme

All animations are theme-agnostic (they reference `var(--accent)` etc. so they automatically
match whichever theme is active):

- `pulseGlow` — breathing glow on the logo mark and auth-screen icon (`filter: drop-shadow`)
- `fadeInDown` — entrance animation for headers, hero text, and the empty-state screen
- `bubbleIn` — each new chat message slides up + fades in
- `typingBounce` — three dots bouncing in sequence while the bot "thinks"
- Button hover — subtle `translateY(-1px)` lift plus a glow-colored box-shadow

### 1.5 How to extend the theme system yourself

If you want to add a third theme (say, a high-contrast mode) or change the palette:

1. Add a new branch in `load_css()` with its own `theme_vars` block.
2. Make sure every new color has a fallback meaning in both contexts (a `--success` and
   `--danger` variable exist specifically so alerts/errors look right in either mode).
3. Never write a raw hex color directly into `style.css` — always go through a variable,
   or the new theme will have rules that silently don't change.

---

## 2. Authentication & Database

- **`database.py`** owns a single SQLite file (`users.db`) with three tables:
  - `users` — `username`, `email`, `full_name`, `salt`, `password_hash`, `theme`, `created_at`
  - `sessions` — one row per chat conversation (`session_id`, `user_id`, `title`, timestamps)
  - `chats` — every individual message (`role`, `content`, linked to `session_id`/`user_id`)
- Passwords are never stored in plaintext. Each registration generates a random 16-byte
  salt (`secrets.token_hex(16)`) and runs `hashlib.pbkdf2_hmac("sha256", password, salt,
  100_000)` — 100,000 iterations of key stretching, which is the OWASP-recommended minimum
  for PBKDF2-SHA256 as of this writing.
- Login compares hashes using `secrets.compare_digest()` — a constant-time comparison that
  avoids leaking timing information an attacker could use to guess passwords character by
  character.
- **Guest mode** bypasses the database entirely (`user_id = 0`), so guest conversations
  exist only in `st.session_state` and vanish when the browser tab closes.

---

## 3. Chat Engine

### 3.1 Streaming

`groq_client.py` calls Groq's OpenAI-compatible endpoint with `"stream": True` and reads
Server-Sent Events line by line, yielding only the incremental `content` deltas. `app.py`
appends each chunk to a running string and re-renders the same placeholder bubble on every
chunk, with a trailing `▌` cursor character — which is what produces the "typing in real
time" effect rather than a single blocking response.

### 3.2 Greeting short-circuit

`utils.detect_greeting()` strips punctuation, lowercases, and checks the message against a
dictionary of greeting patterns (`hi`, `hii`, `hello`, `helo`, `hey`, `namaste`, `bye`,
`thanks`, etc.), including common typos. If matched, the app **never calls the LLM** — it
picks a random pre-written response from `data.json`'s `greetings` object and streams it
character-by-character locally. This makes small talk instant and free, and avoids burning
API quota on "hi."

### 3.3 Knowledge grounding

Before calling Groq, `utils.search_lict_knowledge()` does a cheap keyword match against the
`knowledge_base` and `faq` sections of `data.json`. If the user's message looks
campus-related, relevant facts get assembled into a context string and prepended to the
system prompt — so the model answers from real, locally-stored facts instead of guessing.

### 3.4 Optional live web search

If the user enables the sidebar toggle and `TAVILY_API_KEY` is present, `tavily_client.py`
fires a search request and formats the top results (titles, snippets, source URLs) into
another context block appended to the same system prompt. Both the knowledge-base context
and the web-search context are additive — they can both be present at once.

### 3.5 Memory window

Only the last 12 messages are replayed to the model on each call, to keep token usage and
latency bounded as conversations grow long, while still preserving recent context.

---

## 4. Persistence Strategy (two layers, on purpose)

| Layer | What it stores | Why |
|---|---|---|
| SQLite (`users.db`) | Full structured chat history per user/session | Source of truth — used to reload past chats, delete sessions, etc. |
| `data.json` (`interaction_log`) | Flat rolling log of the last 500 messages across all users | Lightweight, human-readable audit trail; also doubles as the seed file you asked to be populated with real Lumbini ICT Campus data |

`data.json` additionally holds two static sections that never change at runtime:
`knowledge_base` (the campus facts) and `greetings` (the canned responses) — these are
read-only data the app queries but doesn't append to.

---

## 5. UI Layout Breakdown

**Sidebar (top to bottom):**
1. Brand row (pulsing logo + gradient wordmark)
2. "New chat" button
3. Recent chats list — clickable session cards, 🟢 marks the active one, ✕ deletes
4. Settings — dark mode toggle, model picker, temperature slider, web-search toggle
5. API key status warnings (if `.env` values are missing) — no input fields, ever
6. Export buttons (Markdown / JSON) — only shown once a conversation exists
7. User card (avatar initial + name/handle) + Logout button

**Main panel:**
1. Top bar — animated title + subtitle, plus a small badge showing the active model
2. Empty state (only when the current chat has zero messages) — glowing hero + 3 suggestion
   chips that pre-fill the chat input when clicked
3. Message stream — avatar + bubble rows, right-aligned gradient bubbles for the user,
   left-aligned card bubbles for the bot
4. Sticky chat input at the bottom (Streamlit's native `st.chat_input`, restyled via CSS to
   match the glow/border theme)

---

## 6. Security Notes (intentionally scoped for a learning project)

- API keys live only in `.env`, loaded via `python-dotenv`, never rendered in any UI element
  or written to `data.json`/SQLite.
- Passwords are salted + hashed (never plaintext, never reversible).
- This is **not** hardened for public internet deployment as-is — there's no rate limiting,
  no email verification, no CSRF protection, and SQLite isn't built for concurrent
  multi-process write load. For a real production deployment you'd want a managed Postgres
  database, a proper secrets manager instead of a flat `.env` file, and a reverse proxy with
  rate limiting in front of it.

---

## 7. File-by-File Summary

| File | Responsibility |
|---|---|
| `app.py` | Page config, session state, theme injection, sidebar, main chat loop, Groq/Tavily orchestration |
| `auth.py` | Login + register forms (Streamlit tabs), guest mode entry point |
| `database.py` | All SQLite schema + queries (users, sessions, chats) |
| `groq_client.py` | Streaming + non-streaming Groq API wrappers, model list |
| `tavily_client.py` | Tavily search wrapper + context formatter |
| `utils.py` | data.json I/O, greeting detection, knowledge-base search, chat export (md/json) |
| `style.css` | All visual styling — variables consumed, never defined, here |
| `data.json` | Seeded knowledge base, greetings, rolling interaction log |
| `.env.example` | Template for `GROQ_API_KEY` / `TAVILY_API_KEY` |
| `.streamlit/config.toml` | Minimal, theme-neutral server config |
| `requirements.txt` | streamlit, requests, python-dotenv |

---

*This document is meant to live alongside the project as `DETAILED_DOCS.md` so future-you
(or anyone else extending the app) understands not just what the code does, but why it's
structured this way — especially the theming approach, which fixes a genuinely
non-obvious Streamlit gotcha.*

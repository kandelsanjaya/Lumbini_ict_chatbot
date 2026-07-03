# TODO: UI + Agent Upgrades (Login, Chat, Voice, Upload)

## Phase 1 — Visual foundation (must be done first)
- [x] Add Uiverse starfield background markup for both auth + chat screens
- [ ] Replace emoji icons in login/register with inline SVG icons
- [ ] Convert login screen into a single unified modern card
- [ ] Update CSS to support background layer, unique card border, SVG icon styling
- [ ] Replace emoji icons in chat (meta icons, sidebar header)


## Phase 2 — Agent UX improvements
- [ ] Add mic button (Web Speech API speech-to-text) + transcript into chat input
- [ ] Add perceived low-latency UX (typing dots + disable actions while generating/listening)

## Phase 3 — File upload (runnable)
- [ ] Add file uploader inside chat input card
- [ ] Support `.txt` and `.md` only; append content into prompt as extra context
- [ ] Enforce max upload size + show UI chip for attached file

## Phase 4 — Docs
- [ ] Update README with new features + run instructions

## Testing checklist
- [ ] `streamlit run app.py` starts without errors
- [ ] Login page shows one card + starfield background
- [ ] Chat page shows starfield background
- [ ] Mic button fills the input
- [ ] Upload `.txt` works and response includes context


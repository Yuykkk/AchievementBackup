(function () {
    "use strict";

    if (window.__AchievementBackupPanelV3) return;
    window.__AchievementBackupPanelV3 = true;

    const API = "http://localhost:9999";
    const ids = {
        fab: "achievementbackup-launcher",
        overlay: "achievementbackup-workspace",
        style: "achievementbackup-workspace-style",
    };

    const state = {
        tab: "overview",
        settings: {},
        backups: [],
        snapshots: [],
        apps: [],
        query: "",
        ignoredQuery: "",
        captureGame: "",
        saveTimer: 0,
        busy: false,
        pendingPromptOpen: false,
        pendingPromptKey: "",
        liveTimer: 0,
        editingUntil: 0,
    };

    const icon = {
        close: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
        refresh: '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 1-15.5 6.2M3 12A9 9 0 0 1 18.5 5.8"/><path d="M21 4v6h-6M3 20v-6h6"/></svg>',
        save: '<svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>',
        restore: '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/></svg>',
        trash: '<svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15"/></svg>',
        info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
        folder: '<svg viewBox="0 0 24 24"><path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>',
        edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
        upload: '<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M5 21h14"/></svg>',
        download: '<svg viewBox="0 0 24 24"><path d="M12 21V9"/><path d="m7 16 5 5 5-5"/><path d="M5 3h14"/></svg>',
        game: '<svg viewBox="0 0 24 24"><path d="M6 12h4M8 10v4"/><path d="M15 13h.01M18 11h.01"/><path d="M5.5 8h13a3 3 0 0 1 2.9 2.3l1 4.2a3.2 3.2 0 0 1-5.4 3L15 15H9l-2 2.5a3.2 3.2 0 0 1-5.4-3l1-4.2A3 3 0 0 1 5.5 8Z"/></svg>',
        shield: '<svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-5"/></svg>',
    };

    function ensureStyles() {
        if (document.getElementById(ids.style)) return;
        const style = document.createElement("style");
        style.id = ids.style;
        style.textContent = `
            :root {
                --ab-bg: #050d11;
                --ab-panel: #0c171d;
                --ab-panel-2: #10242c;
                --ab-line: #1a3c47;
                --ab-text: #ecfeff;
                --ab-muted: #8ca7b4;
                --ab-accent: #13b8c8;
                --ab-accent-2: #2dd4bf;
                --ab-accent-rgb: 19,184,200;
                --ab-accent-2-rgb: 45,212,191;
                --ab-accent-dark: #06343d;
                --ab-danger: #ef476f;
                --ab-ok: #27c98b;
                --ab-warn: #f59e0b;
            }
            [data-ab-theme="red"] {
                --ab-line: #563044; --ab-accent: #ef476f; --ab-accent-2: #f9738b;
                --ab-accent-rgb: 239,71,111; --ab-accent-2-rgb: 249,115,139; --ab-accent-dark:#4a1426;
            }
            [data-ab-theme="purple"] {
                --ab-line: #42335f; --ab-accent: #a78bfa; --ab-accent-2: #c084fc;
                --ab-accent-rgb: 167,139,250; --ab-accent-2-rgb: 192,132,252; --ab-accent-dark:#24154a;
            }
            [data-ab-theme="green"] {
                --ab-line: #244a3d; --ab-accent: #22c55e; --ab-accent-2: #2dd4bf;
                --ab-accent-rgb: 34,197,94; --ab-accent-2-rgb: 45,212,191; --ab-accent-dark:#0d3b25;
            }
            [data-ab-theme="blue"] {
                --ab-line: #1a3c47; --ab-accent: #13b8c8; --ab-accent-2: #2dd4bf;
                --ab-accent-rgb: 19,184,200; --ab-accent-2-rgb: 45,212,191; --ab-accent-dark:#06343d;
            }
            #${ids.fab} {
                position: fixed; right: 26px; bottom: 26px; width: 54px; height: 54px;
                border-radius: 16px; border: 1px solid rgba(var(--ab-accent-2-rgb),.55);
                color: var(--ab-text); background: linear-gradient(145deg, var(--ab-accent-dark), var(--ab-accent));
                box-shadow: 0 14px 34px rgba(var(--ab-accent-rgb),.25);
                z-index: 2147483646; display: grid; place-items: center; cursor: pointer;
                font: 900 15px/1 "Motiva Sans", Arial, sans-serif; letter-spacing: .04em;
                overflow:hidden; padding:0;
            }
            #${ids.fab}:hover { transform: translateY(-2px); filter: brightness(1.08); }
            #${ids.fab} img { width:44px; height:44px; object-fit:contain; display:block; filter:drop-shadow(0 7px 10px rgba(0,0,0,.4)); transform:translateY(2px); }
            #${ids.overlay} {
                position: fixed; inset: 0; z-index: 2147483647; display: grid; place-items: center;
                background:
                    radial-gradient(circle at 12% 16%, rgba(var(--ab-accent-rgb),.24), transparent 360px),
                    radial-gradient(circle at 90% 84%, rgba(var(--ab-accent-2-rgb),.16), transparent 360px),
                    rgba(2, 6, 9, .84);
                color: var(--ab-text);
                font-family: "Motiva Sans", "Segoe UI", Arial, sans-serif;
            }
            .ab-shell {
                width: min(1220px, calc(100vw - 28px)); height: min(780px, calc(100vh - 28px));
                display: grid; grid-template-columns: 238px 1fr; overflow: hidden; min-height:0;
                border: 1px solid rgba(var(--ab-accent-2-rgb),.34); background: linear-gradient(145deg, rgba(var(--ab-accent-rgb),.08), #061015 34%, #050b0f);
                box-shadow: 0 30px 80px rgba(0,0,0,.55), 0 0 38px rgba(var(--ab-accent-rgb),.1), inset 0 1px 0 rgba(255,255,255,.04);
            }
            .ab-side { position:relative; background: #08121a; border-right: 1px solid var(--ab-line); padding: 22px 14px; display: flex; flex-direction: column; gap: 14px; min-height:0; }
            .ab-brand { padding: 6px 10px 18px; border-bottom: 1px solid var(--ab-line); }
            .ab-brand strong { display:block; font-size: 18px; letter-spacing: .02em; color:#d7fffb; }
            .ab-brand span { display:block; margin-top: 6px; color: var(--ab-muted); font-size: 12px; }
            .ab-nav { display: grid; gap: 6px; }
            .ab-nav button, .ab-command, .ab-icon {
                border: 1px solid transparent; color: var(--ab-text); background: transparent; cursor: pointer;
                font: 700 13px/1 "Motiva Sans", Arial, sans-serif;
            }
            .ab-nav button { text-align: left; padding: 12px; border-radius: 8px; color: var(--ab-muted); display:flex; align-items:center; gap:9px; }
            .ab-nav button.active, .ab-nav button:hover { background: linear-gradient(90deg, rgba(var(--ab-accent-rgb),.22), rgba(var(--ab-accent-2-rgb),.08)); border-color: rgba(var(--ab-accent-2-rgb),.38); color: var(--ab-text); }
            .ab-side-info { margin-top:auto; display:grid; gap:8px; padding: 0 2px; position:relative; }
            .ab-about-button { width:100%; min-height:36px; justify-content:center; }
            .ab-main { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; min-height:0; }
            .ab-top { display:flex; align-items:center; justify-content:space-between; gap: 12px; padding: 18px 22px; border-bottom: 1px solid var(--ab-line); background: rgba(16,31,43,.7); }
            .ab-top h1 { margin:0; font-size: 19px; }
            .ab-top p { margin:5px 0 0; color: var(--ab-muted); font-size: 12px; }
            .ab-toolbar { display:flex; align-items:center; gap: 8px; }
            .ab-command { min-height: 34px; padding: 0 12px; border-radius: 7px; border-color: var(--ab-line); background: #0d1a24; display:inline-flex; align-items:center; gap:8px; }
            .ab-command.primary { background: linear-gradient(145deg, var(--ab-accent), var(--ab-accent-dark)); border-color: rgba(var(--ab-accent-2-rgb),.62); box-shadow:0 8px 20px rgba(var(--ab-accent-rgb),.18); }
            .ab-command.danger { color: #ffd6df; border-color: rgba(239,71,111,.45); }
            .ab-icon { width: 34px; height: 34px; display:grid; place-items:center; border-radius: 7px; border-color: var(--ab-line); background:#0d1a24; }
            .ab-icon svg, .ab-command svg { width: 16px; height:16px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
            .ab-content { min-height:0; overflow-y:auto; overflow-x:hidden; padding: 20px 22px 26px; background: radial-gradient(circle at top right, rgba(var(--ab-accent-rgb),.08), transparent 320px); scrollbar-color: #42606b #071016; }
            .ab-grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
            .ab-grid.two { grid-template-columns: 1fr 1fr; margin-top:16px; }
            .ab-card, .ab-row, .ab-section { border:1px solid var(--ab-line); background: var(--ab-panel); border-radius: 8px; }
            .ab-card { padding: 14px; min-height: 92px; background: linear-gradient(180deg, rgba(var(--ab-accent-rgb),.12), rgba(12,23,29,.92)); }
            .ab-card span { color: var(--ab-muted); font-size: 11px; text-transform: uppercase; letter-spacing:.08em; }
            .ab-card strong { display:block; margin-top: 10px; font-size: 20px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-card small { display:block; margin-top:6px; color:var(--ab-muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-section { margin-top: 16px; overflow:hidden; }
            .ab-section-head { display:flex; align-items:center; justify-content:space-between; gap: 12px; padding: 13px 14px; border-bottom:1px solid var(--ab-line); min-width:0; }
            .ab-section-head strong { font-size: 14px; }
            .ab-list { display:grid; }
            .ab-row { border-width: 0 0 1px 0; border-radius: 0; padding: 13px 14px; display:grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items:center; min-width:0; overflow:hidden; }
            .ab-row > div { min-width:0; }
            .ab-row:last-child { border-bottom: 0; }
            .ab-row-title { font-weight: 800; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-row-meta { margin-top: 5px; color: var(--ab-muted); font-size: 12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-row-copy { margin-top:7px; color:#b7d1d9; font-size:12px; line-height:1.45; }
            .ab-chipline { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
            .ab-chip { display:inline-flex; align-items:center; min-height:22px; padding:0 8px; border-radius:999px; border:1px solid rgba(var(--ab-accent-2-rgb),.3); background:rgba(var(--ab-accent-rgb),.09); color:#c7eef2; font-size:11px; }
            .ab-chip.warn { border-color:rgba(245,158,11,.38); background:rgba(245,158,11,.09); color:#f7d391; }
            .ab-backup-summary { display:grid; gap:2px; min-width:0; }
            .ab-media-row { display:grid; grid-template-columns:86px minmax(0,1fr) auto; gap:13px; align-items:center; min-width:0; }
            .ab-media-row > div { min-width:0; }
            .ab-thumb { width:86px; height:50px; border-radius:8px; border:1px solid var(--ab-line); background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.3), rgba(7,16,22,.95)); display:grid; place-items:center; color:#d7fffb; font-weight:900; overflow:hidden; }
            .ab-thumb.backup { position:relative; background:linear-gradient(145deg, rgba(var(--ab-accent-rgb),.22), rgba(var(--ab-accent-2-rgb),.08) 46%, rgba(7,16,22,.96)); box-shadow:inset 0 1px 0 rgba(255,255,255,.05); }
            .ab-thumb.backup:before { content:""; position:absolute; inset:8px 12px; border:1px solid rgba(var(--ab-accent-2-rgb),.26); border-radius:6px; background:linear-gradient(180deg, rgba(var(--ab-accent-rgb),.1), rgba(0,0,0,.12)); }
            .ab-thumb.backup svg { position:relative; width:24px; height:24px; fill:none; stroke:var(--ab-accent-2); stroke-width:2; stroke-linecap:round; stroke-linejoin:round; filter:drop-shadow(0 4px 8px rgba(0,0,0,.4)); }
            .ab-thumb img { width:100%; height:100%; object-fit:cover; object-position:center; display:block; }
            .ab-thumb span { font-size:16px; letter-spacing:.04em; }
            .ab-actions { display:flex; align-items:center; gap: 8px; flex:0 0 auto; min-width:max-content; }
            .ab-section-head > .ab-actions { flex-wrap:wrap; justify-content:flex-end; min-width:0; }
            .ab-search { width: min(360px, 100%); background:#071016; border:1px solid var(--ab-line); color:var(--ab-text); border-radius:7px; padding:10px 11px; outline:none; }
            .ab-badge { display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border:1px solid var(--ab-line); border-radius:999px; color:var(--ab-muted); font-size:11px; }
            .ab-badge svg, .ab-game-card svg { width:14px; height:14px; flex:0 0 auto; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
            .ab-cover { width:96px; height:45px; border-radius:6px; object-fit:cover; background:#071016; border:1px solid var(--ab-line); }
            .ab-mini-cover { width:64px; height:30px; border-radius:5px; object-fit:cover; background:#071016; border:1px solid var(--ab-line); }
            .ab-cover-tile { width:96px; height:45px; border-radius:6px; border:1px solid var(--ab-line); background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.26), rgba(7,16,22,.96)); overflow:hidden; display:grid; place-items:center; color:#d7fffb; font-weight:900; flex:0 0 auto; }
            .ab-cover-tile.mini { width:64px; height:30px; border-radius:5px; }
            .ab-cover-tile img { width:100%; height:100%; object-fit:cover; object-position:center; display:block; grid-area:1/1; }
            .ab-cover-tile span { grid-area:1/1; display:none; width:100%; height:100%; place-items:center; font-size:13px; letter-spacing:.04em; }
            .ab-cover-tile.mini span { font-size:10px; }
            .ab-option { border:1px solid var(--ab-line); background:linear-gradient(180deg, rgba(16,36,44,.75), rgba(7,16,22,.72)); border-radius:8px; padding:13px; display:grid; grid-template-columns: 1fr auto; gap:12px; align-items:center; }
            .ab-option strong { display:block; font-size:13px; }
            .ab-option p { margin:6px 0 0; color:var(--ab-muted); font-size:12px; line-height:1.45; }
            .ab-path-code { display:block; margin-top:8px; padding:8px 9px; border:1px solid var(--ab-line); border-radius:7px; color:#d7fffb; background:#071016; font:700 11px/1.35 Consolas, monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-toggle { width:42px; height:24px; appearance:none; border:1px solid var(--ab-line); background:#071016; border-radius:999px; position:relative; cursor:pointer; }
            .ab-toggle:before { content:""; position:absolute; width:18px; height:18px; left:2px; top:2px; border-radius:50%; background:#7997a3; transition:.16s; }
            .ab-toggle:checked { background:var(--ab-accent-dark); border-color:rgba(var(--ab-accent-2-rgb),.78); }
            .ab-toggle:checked:before { transform:translateX(18px); background:#ecfeff; }
            .ab-empty { padding: 32px 14px; color: var(--ab-muted); text-align:center; }
            .ab-form { display:grid; gap: 14px; max-width: 860px; }
            .ab-field { display:grid; gap: 7px; }
            .ab-field label { color: var(--ab-muted); font-size: 12px; font-weight: 800; }
            .ab-field input, .ab-field select, .ab-field textarea {
                background:#071016; border:1px solid var(--ab-line); color:var(--ab-text);
                border-radius:7px; padding: 10px 11px; outline:none;
            }
            .ab-check { display:flex; align-items:center; gap:10px; color:var(--ab-text); font-weight:700; }
            .ab-check input { width: 18px; height:18px; accent-color: var(--ab-accent); }
            .ab-mode-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:10px; }
            .ab-mode-card { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:13px; color:var(--ab-text); text-align:left; cursor:pointer; min-height:118px; display:grid; gap:8px; align-content:start; position:relative; }
            .ab-mode-card:before { content:""; width:16px; height:16px; border-radius:50%; border:1px solid #5f7d88; position:absolute; right:12px; top:12px; }
            .ab-mode-card.active:before { background:var(--ab-accent-2); box-shadow:inset 0 0 0 4px var(--ab-panel); border-color:var(--ab-accent-2); }
            .ab-mode-card strong { display:block; font-size:13px; padding-right:26px; }
            .ab-mode-card em { font-style:normal; color:var(--ab-accent-2); font-size:10px; text-transform:uppercase; letter-spacing:.08em; }
            .ab-mode-card span { display:block; color:var(--ab-muted); font-size:12px; line-height:1.4; }
            .ab-mode-card.active, .ab-mode-card:hover { border-color:rgba(var(--ab-accent-2-rgb),.72); background:linear-gradient(180deg, rgba(var(--ab-accent-rgb),.18), rgba(7,16,22,.85)); }
            .ab-theme-grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; }
            .ab-theme-card { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:11px; color:var(--ab-text); text-align:left; cursor:pointer; display:flex; align-items:center; gap:10px; min-height:54px; }
            .ab-theme-card.active, .ab-theme-card:hover { border-color:var(--ab-accent-2); background:linear-gradient(180deg, rgba(var(--ab-accent-rgb),.16), rgba(7,16,22,.86)); }
            .ab-swatch { width:22px; height:22px; border-radius:999px; border:1px solid rgba(255,255,255,.22); box-shadow:0 0 0 3px rgba(255,255,255,.04); flex:0 0 auto; }
            .ab-swatch.blue { background:linear-gradient(135deg, #13b8c8, #2dd4bf); }
            .ab-swatch.purple { background:linear-gradient(135deg, #8b5cf6, #c084fc); }
            .ab-swatch.green { background:linear-gradient(135deg, #22c55e, #2dd4bf); }
            .ab-swatch.red { background:linear-gradient(135deg, #ef476f, #f9738b); }
            .ab-protect-grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; }
            .ab-source-card { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:12px; min-height:86px; }
            .ab-source-card strong { display:block; font-size:13px; color:var(--ab-text); }
            .ab-source-card span { display:block; margin-top:7px; color:var(--ab-muted); font-size:12px; line-height:1.4; }
            .ab-hero-panel { border:1px solid var(--ab-line); background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.17), rgba(12,23,29,.92)); border-radius:8px; padding:16px; display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; margin-bottom:12px; }
            .ab-hero-panel h2 { margin:0; font-size:18px; }
            .ab-hero-panel p { margin:7px 0 0; color:var(--ab-muted); font-size:12px; line-height:1.5; }
            .ab-close-prompt { display:grid; gap:12px; }
            .ab-close-game { border:1px solid var(--ab-line); border-radius:8px; background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.16), rgba(7,16,22,.92)); padding:14px; }
            .ab-close-game strong { display:block; color:var(--ab-text); font-size:16px; }
            .ab-close-game span { display:block; margin-top:5px; color:var(--ab-muted); font-size:12px; }
            .ab-close-preview { display:grid; grid-template-columns:132px minmax(0, 1fr); gap:14px; align-items:stretch; border:1px solid var(--ab-line); border-radius:8px; padding:12px; background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.16), rgba(7,16,22,.92)); }
            .ab-close-cover { width:132px; min-height:74px; border-radius:7px; border:1px solid rgba(var(--ab-accent-2-rgb),.35); background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.26), rgba(7,16,22,.96)); overflow:hidden; display:grid; place-items:center; color:#d7fffb; font-weight:900; }
            .ab-close-cover img { width:100%; height:100%; object-fit:cover; display:block; }
            .ab-close-cover span { font-size:18px; }
            .ab-close-copy { min-width:0; display:grid; align-content:center; gap:6px; }
            .ab-close-copy strong { font-size:18px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-close-copy p { margin:0; color:var(--ab-muted); font-size:12px; line-height:1.45; }
            .ab-save-list { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
            .ab-save-item { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:10px; min-height:74px; }
            .ab-save-item b { display:block; color:#d7fffb; font-size:12px; }
            .ab-save-item span { display:block; margin-top:6px; color:var(--ab-muted); font-size:11px; line-height:1.35; }
            .ab-restore-choice { display:grid; gap:12px; }
            .ab-restore-card { border:1px solid var(--ab-line); background:linear-gradient(135deg, rgba(var(--ab-accent-rgb),.14), rgba(7,16,22,.92)); border-radius:8px; padding:14px; }
            .ab-restore-card strong { display:block; color:var(--ab-text); font-size:16px; }
            .ab-restore-card span { display:block; margin-top:6px; color:var(--ab-muted); font-size:12px; line-height:1.45; }
            .ab-restore-steps { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
            .ab-restore-step { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:10px; min-height:68px; }
            .ab-restore-step b { display:block; color:#d7fffb; font-size:12px; }
            .ab-restore-step span { display:block; margin-top:6px; color:var(--ab-muted); font-size:11px; line-height:1.35; }
            .ab-restore-warning { border:1px solid rgba(245,158,11,.35); background:rgba(245,158,11,.08); color:#f7d391; border-radius:8px; padding:11px; font-size:12px; line-height:1.45; }
            .ab-modal-lite { position:fixed; inset:0; z-index:2147483647; display:grid; place-items:center; background:rgba(2,6,9,.72); padding:14px; }
            .ab-dialog { width:min(760px, calc(100vw - 28px)); max-height:calc(100vh - 28px); display:grid; grid-template-rows:auto minmax(0, 1fr) auto; border:1px solid var(--ab-line); background:var(--ab-panel); border-radius:8px; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.55); }
            .ab-dialog-head { padding:15px 16px; border-bottom:1px solid var(--ab-line); display:flex; justify-content:space-between; align-items:center; }
            .ab-dialog-head p { margin:5px 0 0; color:var(--ab-muted); font-size:12px; }
            .ab-dialog-body { padding:16px; color:var(--ab-muted); line-height:1.55; overflow:auto; min-height:0; }
            .ab-dialog-body strong { color:var(--ab-text); }
            .ab-detail-list { display:grid; gap:8px; margin-top:12px; }
            .ab-detail-item { border:1px solid var(--ab-line); background:#071016; border-radius:7px; padding:10px; }
            .ab-detail-item div { color:var(--ab-muted); font-size:12px; margin-top:4px; }
            .ab-dialog-actions { padding:14px 16px; border-top:1px solid var(--ab-line); display:flex; justify-content:flex-end; gap:8px; }
            .ab-toast { position:fixed; right:24px; top:24px; z-index:2147483647; max-width:360px; padding:12px 14px; background:#0d1a24; border:1px solid var(--ab-line); border-radius:8px; box-shadow:0 18px 44px rgba(0,0,0,.4); }
            .ab-status-line { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
            .ab-split { display:grid; grid-template-columns: minmax(340px, .9fr) minmax(0, 1.25fr); gap:14px; }
            .ab-game-list { display:grid; gap:8px; }
            .ab-game-card { border:1px solid var(--ab-line); border-radius:8px; background:#071016; padding:10px; cursor:pointer; display:flex; align-items:center; gap:10px; color:var(--ab-text); min-width:0; }
            .ab-game-card small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .ab-game-card.active, .ab-game-card:hover { border-color:rgba(var(--ab-accent-2-rgb),.58); background:rgba(var(--ab-accent-rgb),.12); }
            .ab-save-note { color:var(--ab-muted); font-size:12px; min-height:18px; }
            .ab-about-list { display:grid; gap:10px; margin-top:10px; }
            .ab-about-list a { color:#d7fffb; text-decoration:none; border-bottom:1px solid rgba(var(--ab-accent-2-rgb),.45); }
            .ab-about-tip { border:1px solid var(--ab-line); background:#071016; border-radius:8px; padding:10px; color:#b7d1d9; font-size:12px; line-height:1.45; }
            @media (max-width: 820px) {
                .ab-shell { grid-template-columns: 1fr; }
                .ab-side { display:none; }
                .ab-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .ab-grid.two, .ab-split, .ab-mode-grid, .ab-theme-grid, .ab-protect-grid, .ab-hero-panel, .ab-restore-steps, .ab-close-preview, .ab-save-list { grid-template-columns: 1fr; }
                .ab-media-row { grid-template-columns:1fr; align-items:start; }
                .ab-top { align-items:flex-start; }
            }
        `;
        document.head.appendChild(style);
    }

    function json(path, options) {
        const opts = Object.assign({ cache: "no-store" }, options || {});
        return fetch(API + path, opts).then(async (response) => {
            const text = await response.text();
            let data = {};
            try { data = text ? JSON.parse(text) : {}; } catch (e) { data = { raw: text }; }
            if (!response.ok) throw new Error(data.message || response.statusText || "Falha na requisicao");
            return data;
        });
    }

    function post(path, body) {
        return json(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
        });
    }

    function fmtBytes(value) {
        let size = Number(value || 0);
        const units = ["B", "KB", "MB", "GB", "TB"];
        let idx = 0;
        while (size >= 1024 && idx < units.length - 1) {
            size /= 1024;
            idx += 1;
        }
        return `${size.toFixed(idx ? 1 : 0)} ${units[idx]}`;
    }

    function appCover(appid) {
        return `${API}/asset/app/${encodeURIComponent(appid || "")}`;
    }

    function remoteCoverSources(appid) {
        const id = encodeURIComponent(appid || "");
        return [
            `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/capsule_sm_120.jpg`,
            `https://cdn.cloudflare.steamstatic.com/steam/apps/${id}/header.jpg`,
            `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${id}/header.jpg`,
            `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${id}/library_600x900.jpg`,
        ];
    }

    function snapshotId(item) {
        return item.id || item.folder || "";
    }

    function snapshotGameName(item) {
        return item.gameName || item.game_name || item.game || String(snapshotId(item)).split("/")[0] || "Jogo";
    }

    function snapshotsByGame() {
        const groups = new Map();
        state.snapshots.forEach((item) => {
            const key = String(item.appid || snapshotGameName(item));
            if (!groups.has(key)) {
                groups.set(key, {
                    key,
                    appid: item.appid || "",
                    name: snapshotGameName(item),
                    items: [],
                    size: 0,
                });
            }
            const group = groups.get(key);
            group.items.push(item);
            group.size += Number(item.size || 0);
        });
        return Array.from(groups.values()).sort((a, b) => a.name.localeCompare(b.name));
    }

    function formatDateText(raw) {
        const text = String(raw || "").replace(/_/g, " ");
        const match = text.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2})-(\d{2})(?:-(\d{2}))?/);
        if (!match) return raw || "";
        return `${match[3]}/${match[2]}/${match[1]} ${match[4]}:${match[5]}`;
    }

    function backupTitle(item) {
        if (item.nickname) return item.nickname;
        return `Backup Steam completo${item.timestamp ? ` - ${formatDateText(item.timestamp)}` : ""}`;
    }

    function snapshotTitle(item) {
        if (item.nickname) return item.nickname;
        return `Captura de ${snapshotGameName(item)}${item.timestamp ? ` - ${formatDateText(item.timestamp)}` : ""}`;
    }

    function backupDescription() {
        return "Restaura o pacote amplo da Steam: conquistas e estatísticas em appcache/stats, saves e configurações em userdata, lista/configuração de jogos em config/stplug-in e saves externos detectados quando habilitados.";
    }

    function backupShortDescription() {
        return "Backup completo manual. Use detalhes para ver jogos e fontes protegidas.";
    }

    function backupChips() {
        const labels = ["appcache/stats", "userdata", "config/stplug-in"];
        if ((state.settings || {}).backup_all_external_saves) labels.push("saves externos");
        return `<div class="ab-chipline">${labels.map((label) => `<span class="ab-chip">${esc(label)}</span>`).join("")}</div>`;
    }

    function itemHasExternalSaves(item) {
        if (!item) return false;
        if (item.hasExternalSaves) return true;
        const files = Array.isArray(item.files) ? item.files : [];
        return files.some((file) => {
            const bucket = String(file.bucket || "").toLowerCase();
            const category = String(file.category || "").toLowerCase();
            return bucket.includes("external") && !["ludusavi-manifest", "game-save"].includes(category);
        });
    }

    function itemHasKnownSaves(item) {
        if (!item) return false;
        if (item.hasKnownSaves) return true;
        const files = Array.isArray(item.files) ? item.files : [];
        return files.some((file) => ["ludusavi-manifest", "game-save"].includes(String(file.category || "").toLowerCase()));
    }

    function dataChips(item, kind) {
        const chips = kind === "backup"
            ? ["appcache/stats", "userdata", "config/stplug-in"]
            : ["stats", "userdata", "AppID"];
        if (itemHasKnownSaves(item)) chips.push("caminhos conhecidos");
        if (itemHasExternalSaves(item)) chips.push("busca extra");
        return `<div class="ab-chipline">${chips.map((label) => `<span class="ab-chip ${label === "busca extra" ? "warn" : ""}">${esc(label)}</span>`).join("")}</div>`;
    }

    function initials(name) {
        return String(name || "AB").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "AB";
    }

    function mediaThumb(item, kind) {
        const appid = item && item.appid;
        if (appid) {
            return `<div class="ab-thumb"><img src="${appCover(appid)}" onerror="this.remove(); this.parentNode.innerHTML='<span>${esc(initials(item.game_name || item.gameName || item.name))}</span>'"></div>`;
        }
        if (kind === "backup") {
            return `<div class="ab-thumb backup" title="Backup completo">${icon.save}</div>`;
        }
        const label = initials(snapshotGameName(item || {}));
        return `<div class="ab-thumb"><span>${esc(label)}</span></div>`;
    }

    function gameCoverTile(appid, name, mini) {
        const cls = mini ? "ab-cover-tile mini" : "ab-cover-tile";
        return `<div class="${cls}"><img src="${appCover(appid)}" data-cover-sources="${esc(remoteCoverSources(appid).join("|"))}"><span>${esc(initials(name))}</span></div>`;
    }

    function modeNote(mode) {
        return {
            semi: "Vai perguntar ao fechar cada jogo e, se você aceitar, cria uma captura leve daquele AppID. Backup completo continua manual.",
            manual: "Não aparece pergunta ao fechar jogos. Você decide quando criar captura ou backup completo pelos botões.",
            auto: "Cria capturas sozinho ao fechar jogos. É prático, mas pode ocupar disco se você jogar muita coisa.",
        }[mode] || "Backup completo continua manual para evitar gastar HD sem você pedir.";
    }

    function snapshotDescription(item) {
        const known = itemHasKnownSaves(item) ? ", saves de caminhos conhecidos" : "";
        const external = itemHasExternalSaves(item) ? " e arquivos da busca extra" : "";
        return `Restaura somente ${snapshotGameName(item)}: conquistas/stats, saves Steam do AppID${known}, configurações ligadas ao jogo${external}.`;
    }

    function sourceCards(kind) {
        const items = [
            ["Conquistas e stats", "appcache/stats", "Progresso de achievements e estatísticas locais dos jogos."],
            ["Saves Steam", "userdata/<id>", "Saves, preferências e dados pessoais vinculados à sua conta Steam."],
            ["Config dos jogos", "config/stplug-in", "Lista, estado e configurações locais usadas pela Steam para os jogos."],
            ["Saves externos", "AppData e Documentos", kind === "snapshot" ? "Pastas externas conhecidas deste jogo, sem misturar outros AppIDs." : "Caminhos conhecidos pelo manifest quando ativados."],
        ];
        return `<div class="ab-protect-grid">${items.map(([title, path, copy]) => `
            <div class="ab-source-card"><strong>${esc(title)}</strong><span>${esc(path)}<br>${esc(copy)}</span></div>
        `).join("")}</div>`;
    }

    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
        }[char]));
    }

    function toast(message) {
        const old = document.querySelector(".ab-toast");
        if (old) old.remove();
        const el = document.createElement("div");
        el.className = "ab-toast";
        el.dataset.abTheme = currentTheme();
        el.textContent = message;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 3200);
    }

    function confirmDialog(title, message, confirmText) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "ab-modal-lite";
            overlay.dataset.abTheme = currentTheme();
            overlay.innerHTML = `
                <div class="ab-dialog">
                    <div class="ab-dialog-head"><strong>${esc(title)}</strong><button class="ab-icon" data-no>${icon.close}</button></div>
                    <div class="ab-dialog-body">${esc(message)}</div>
                    <div class="ab-dialog-actions">
                        <button class="ab-command" data-no>Cancelar</button>
                        <button class="ab-command primary" data-yes>${esc(confirmText || "Confirmar")}</button>
                    </div>
                </div>
            `;
            overlay.querySelectorAll("[data-no]").forEach((btn) => btn.addEventListener("click", () => { overlay.remove(); resolve(false); }));
            overlay.querySelector("[data-yes]").addEventListener("click", () => { overlay.remove(); resolve(true); });
            document.body.appendChild(overlay);
        });
    }

    function progressDialog(title, message) {
        const overlay = document.createElement("div");
        overlay.className = "ab-modal-lite";
        overlay.dataset.abTheme = currentTheme();
        overlay.innerHTML = `
            <div class="ab-dialog" style="width:min(520px, calc(100vw - 28px));">
                <div class="ab-dialog-head"><div><strong>${esc(title)}</strong><p data-progress-subtitle>${esc(message || "Preparando...")}</p></div></div>
                <div class="ab-dialog-body">
                    <div class="ab-row-copy" style="margin-top:0;" data-progress-text>${esc(message || "Preparando...")}</div>
                    <div style="height:8px; border:1px solid var(--ab-line); border-radius:999px; overflow:hidden; background:#071016; margin-top:12px;">
                        <div data-progress-bar style="width:0%; height:100%; background:linear-gradient(90deg, var(--ab-accent), var(--ab-accent-2)); transition:width .2s;"></div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        return {
            update(text, percent) {
                const subtitle = overlay.querySelector("[data-progress-subtitle]");
                const body = overlay.querySelector("[data-progress-text]");
                const bar = overlay.querySelector("[data-progress-bar]");
                if (subtitle) subtitle.textContent = text;
                if (body) body.textContent = text;
                if (bar && Number.isFinite(percent)) bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
            },
            close() {
                overlay.remove();
            },
        };
    }

    function capturePromptDialog(gameName, appid) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "ab-modal-lite";
            overlay.dataset.abTheme = currentTheme();
            const cover = appid
                ? `<div class="ab-close-cover"><img src="${appCover(appid)}" onerror="this.remove(); this.parentNode.innerHTML='<span>${esc(initials(gameName || "Jogo"))}</span>'"></div>`
                : `<div class="ab-close-cover"><span>${esc(initials(gameName || "Jogo"))}</span></div>`;
            overlay.innerHTML = `
                <div class="ab-dialog">
                    <div class="ab-dialog-head">
                        <div><strong>Jogo fechado</strong><p>Captura leve por jogo</p></div>
                        <button class="ab-icon" data-no>${icon.close}</button>
                    </div>
                    <div class="ab-dialog-body">
                        <div class="ab-close-prompt">
                            <div class="ab-close-preview">
                                ${cover}
                                <div class="ab-close-copy">
                                    <strong>${esc(gameName || "Jogo atual")}</strong>
                                    <p>${appid ? `AppID ${esc(appid)}` : "Jogo detectado pela Steam"}</p>
                                    <p>Cria uma captura focada só neste jogo. É mais leve que backup completo e serve para restaurar este AppID sem mexer no restante da biblioteca.</p>
                                </div>
                            </div>
                            <div class="ab-save-list">
                                <div class="ab-save-item"><b>Conquistas e stats</b><span>Arquivos de progresso local em appcache/stats.</span></div>
                                <div class="ab-save-item"><b>Saves Steam</b><span>Dados do AppID dentro de userdata e configurações ligadas ao jogo.</span></div>
                                <div class="ab-save-item"><b>Saves conhecidos</b><span>Caminhos Windows encontrados pela API Ludusavi/PCGamingWiki, se ativada.</span></div>
                            </div>
                            <div class="ab-row-copy">Backup completo continua manual para não ocupar disco sem você pedir.</div>
                        </div>
                    </div>
                    <div class="ab-dialog-actions">
                        <button class="ab-command" data-no>Agora não</button>
                        <button class="ab-command primary" data-yes>Criar captura</button>
                    </div>
                </div>
            `;
            overlay.querySelectorAll("[data-no]").forEach((btn) => btn.addEventListener("click", () => { overlay.remove(); resolve(false); }));
            overlay.querySelector("[data-yes]").addEventListener("click", () => { overlay.remove(); resolve(true); });
            document.body.appendChild(overlay);
        });
    }

    function restoreSnapshotDialog(item) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "ab-modal-lite";
            overlay.dataset.abTheme = currentTheme();
            overlay.innerHTML = `
                <div class="ab-dialog">
                    <div class="ab-dialog-head">
                        <div><strong>Restaurar captura</strong><p>${esc(snapshotGameName(item || {}))}</p></div>
                        <button class="ab-icon" data-no>${icon.close}</button>
                    </div>
                    <div class="ab-dialog-body">
                        <div class="ab-restore-choice">
                            <div class="ab-restore-card">
                                <strong>${esc(snapshotTitle(item || {}))}</strong>
                                <span>Restaura somente este jogo. O plugin fecha a Steam, aplica os arquivos capturados e tenta abrir a Steam novamente no final.</span>
                                ${dataChips(item || {}, "snapshot")}
                            </div>
                            <div class="ab-restore-steps">
                                <div class="ab-restore-step"><b>1. Fecha a Steam</b><span>Evita que ela sobrescreva os arquivos durante o restore.</span></div>
                                <div class="ab-restore-step"><b>2. Aplica a captura</b><span>Volta conquistas/stats, userdata/AppID, configs e saves conhecidos desta captura.</span></div>
                                <div class="ab-restore-step"><b>3. Abre de novo</b><span>Uma janela mostra o progresso e confirma se a Steam voltou.</span></div>
                            </div>
                            <div class="ab-restore-warning">Segurança automática: antes de sobrescrever, o plugin guarda uma cópia dos arquivos atuais. Se o Windows bloquear Documentos ou AppData, libere o acesso controlado a pastas e tente novamente.</div>
                        </div>
                    </div>
                    <div class="ab-dialog-actions">
                        <button class="ab-command" data-no>Cancelar</button>
                        <button class="ab-command primary" data-yes>${icon.restore} Restaurar</button>
                    </div>
                </div>
            `;
            overlay.querySelectorAll("[data-no]").forEach((btn) => btn.addEventListener("click", () => { overlay.remove(); resolve(null); }));
            overlay.querySelector("[data-yes]").addEventListener("click", () => {
                overlay.remove();
                resolve({ createSafetyBackup: true });
            });
            document.body.appendChild(overlay);
        });
    }

    function inputDialog(title, label, value) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "ab-modal-lite";
            overlay.dataset.abTheme = currentTheme();
            overlay.innerHTML = `
                <div class="ab-dialog">
                    <div class="ab-dialog-head"><strong>${esc(title)}</strong><button class="ab-icon" data-no>${icon.close}</button></div>
                    <div class="ab-dialog-body">
                        <div class="ab-field"><label>${esc(label)}</label><input data-input value="${esc(value || "")}"></div>
                    </div>
                    <div class="ab-dialog-actions">
                        <button class="ab-command" data-no>Cancelar</button>
                        <button class="ab-command primary" data-yes>Salvar</button>
                    </div>
                </div>
            `;
            const input = overlay.querySelector("[data-input]");
            overlay.querySelectorAll("[data-no]").forEach((btn) => btn.addEventListener("click", () => { overlay.remove(); resolve(null); }));
            overlay.querySelector("[data-yes]").addEventListener("click", () => { const out = input.value.trim(); overlay.remove(); resolve(out); });
            document.body.appendChild(overlay);
            input.focus();
            input.select();
        });
    }

    function aboutDialog() {
        const overlay = document.createElement("div");
        overlay.className = "ab-modal-lite";
        overlay.dataset.abTheme = currentTheme();
        overlay.innerHTML = `
            <div class="ab-dialog">
                <div class="ab-dialog-head">
                    <div><strong>Sobre o AchievementBackup</strong><p>Plugin criado por Yuki para proteger dados locais da Steam.</p></div>
                    <button class="ab-icon" data-close-about>${icon.close}</button>
                </div>
                <div class="ab-dialog-body">
                    <div class="ab-row-copy" style="margin-top:0;">
                        O AchievementBackup cria backups completos e capturas por jogo para guardar conquistas/stats, userdata do AppID, configurações locais da Steam e saves externos conhecidos quando essa opção estiver ativa.
                    </div>
                    <div class="ab-about-list">
                        <div class="ab-about-tip"><strong>Backup completo</strong><br>Use quando quiser guardar o pacote geral da Steam antes de formatar, mexer em arquivos ou trocar instalação.</div>
                        <div class="ab-about-tip"><strong>Captura por jogo</strong><br>Use para salvar/restaurar só um AppID sem mexer no resto da sua biblioteca.</div>
                        <div class="ab-about-tip"><strong>Apps ignorados</strong><br>Marque jogos que não devem disparar captura automática ao fechar.</div>
                        <div class="ab-about-tip"><strong>Dica</strong><br>Use Exportar tudo antes de formatar ou trocar de PC. O plugin cria um ZIP com backups e capturas para importar depois.</div>
                    </div>
                    <div class="ab-row-copy">
                        Criado por <strong>Yuykkk / Yuki</strong><br>
                        GitHub: <a href="https://github.com/Yuykkk" target="_blank" rel="noreferrer">github.com/Yuykkk</a><br>
                        Discord: <strong>@yukiyot</strong>
                    </div>
                </div>
                <div class="ab-dialog-actions"><button class="ab-command primary" data-close-about>Fechar</button></div>
            </div>
        `;
        overlay.querySelectorAll("[data-close-about]").forEach((btn) => btn.onclick = () => overlay.remove());
        document.body.appendChild(overlay);
    }

    async function refreshData() {
        const [settings, backups, snapshots, stats, session, apps] = await Promise.all([
            json("/settings").catch(() => ({})),
            json("/list").catch(() => []),
            json("/achievements/list").catch(() => []),
            json("/stats").catch(() => ({})),
            json("/session").catch(() => ({})),
            json("/installed-apps").catch(() => ({ apps: [] })),
        ]);
        const lockedTheme = currentTheme();
        const incomingSettings = settings || {};
        if (Date.now() < (state.editingUntil || 0) && (state.settings || {}).theme) {
            incomingSettings.theme = lockedTheme;
        }
        state.settings = incomingSettings;
        state.backups = Array.isArray(backups) ? backups : [];
        state.snapshots = Array.isArray(snapshots) ? snapshots : [];
        state.stats = stats || {};
        state.session = session || {};
        state.apps = Array.isArray(apps.apps) ? apps.apps : [];
    }

    function currentTheme() {
        const theme = String((state.settings || {}).theme || "blue").toLowerCase();
        return ["blue", "purple", "green", "red"].includes(theme) ? theme : "blue";
    }

    function applyTheme(theme) {
        const chosen = ["blue", "purple", "green", "red"].includes(String(theme || "").toLowerCase())
            ? String(theme).toLowerCase()
            : currentTheme();
        document.documentElement.dataset.abTheme = chosen;
        document.body.dataset.abTheme = chosen;
        document.querySelectorAll(`#${ids.overlay}, .ab-modal-lite, .ab-toast`).forEach((node) => {
            node.dataset.abTheme = chosen;
        });
    }

    function shell() {
        const tabs = [
            ["overview", "Visão geral"],
            ["backups", "Backups"],
            ["captures", "Capturas"],
            ["games", "Jogos"],
            ["ignored", "Ignorados"],
            ["settings", "Configurações"],
        ];
        return `
            <div class="ab-shell">
                <aside class="ab-side">
                    <div class="ab-brand"><strong>AchievementBackup</strong><span>Painel local da Steam</span></div>
                    <nav class="ab-nav">
                        ${tabs.map(([id, label]) => `<button class="${state.tab === id ? "active" : ""}" data-tab="${id}">${label}</button>`).join("")}
                    </nav>
                    <div class="ab-side-info">
                        <button class="ab-command ab-about-button" data-about type="button">${icon.info} Sobre o plugin</button>
                    </div>
                </aside>
                <main class="ab-main">
                    <header class="ab-top">
                        <div><h1>${titleForTab()}</h1><p>${subtitleForTab()}</p></div>
                        <div class="ab-toolbar">
                            <button class="ab-icon" data-close title="Fechar">${icon.close}</button>
                        </div>
                    </header>
                    <section class="ab-content">${contentForTab()}</section>
                </main>
            </div>
        `;
    }

    function titleForTab() {
        return { overview: "Visão geral", backups: "Backups completos", captures: "Capturas por jogo", games: "Jogos instalados", ignored: "Apps ignorados", settings: "Configurações" }[state.tab] || "AchievementBackup";
    }

    function subtitleForTab() {
        return {
            overview: "Status do monitor, espaço usado e atalhos principais.",
            backups: "Backups completos da Steam para restaurar, exportar ou remover.",
            captures: "Capturas leves separadas por jogo e AppID.",
            games: "Jogos instalados detectados pela Steam.",
            ignored: "Apps que não devem gerar captura automática.",
            settings: "Preferências do plugin salvas automaticamente.",
        }[state.tab] || "";
    }

    function contentForTab() {
        if (state.tab === "backups") return backupsView();
        if (state.tab === "captures") return capturesView();
        if (state.tab === "games") return gamesView();
        if (state.tab === "ignored") return ignoredView();
        if (state.tab === "settings") return settingsView();
        return overviewView();
    }

    function overviewView() {
        const activeGame = state.session.active ? `${state.session.currentGame || "Jogo"} (${state.session.currentAppID || ""})` : "Nenhum";
        const lastBackup = state.backups[0];
        const lastSnapshot = state.snapshots[0];
        const ignoredCount = (state.settings.ignored_appids || []).length;
        const backupSize = state.stats.backup_only_bytes != null ? state.stats.backup_only_bytes : state.backups.reduce((sum, item) => sum + Number(item.size || 0), 0);
        const snapshotSize = state.stats.snapshot_bytes != null ? state.stats.snapshot_bytes : state.snapshots.reduce((sum, item) => sum + Number(item.size || 0), 0);
        const backupCount = state.stats.backup_count != null ? state.stats.backup_count : state.backups.length;
        const snapshotCount = state.stats.snapshot_count != null ? state.stats.snapshot_count : state.snapshots.length;
        const recentBackups = state.backups.slice(0, 4).map((item) => `
            <div class="ab-row" data-folder="${esc(item.folder || "")}">
                <div><div class="ab-row-title">${esc(backupTitle(item))}</div><div class="ab-row-meta">${esc([formatDateText(item.timestamp), fmtBytes(item.size), item.file_count ? `${item.file_count} arquivos` : ""].filter(Boolean).join(" | "))}</div></div>
                <div class="ab-actions"><button class="ab-icon" data-details="backup" title="Detalhes">${icon.info}</button></div>
            </div>
        `).join("");
        const recentSnapshots = state.snapshots.slice(0, 4).map((item) => `
            <div class="ab-row" data-snapshot="${esc(snapshotId(item))}">
                <div><div class="ab-row-title">${esc(snapshotTitle(item))}</div><div class="ab-row-meta">${esc([item.appid ? `AppID ${item.appid}` : "", formatDateText(item.timestamp), fmtBytes(item.size)].filter(Boolean).join(" | "))}</div></div>
                <div class="ab-actions"><button class="ab-icon" data-details="snapshot" title="Detalhes">${icon.info}</button></div>
            </div>
        `).join("");
        return `
            <div class="ab-hero-panel">
                <div>
                    <h2>Proteção local da sua Steam</h2>
                    <p>Salve, importe e exporte seus backups e capturas em um só lugar.</p>
                </div>
                <div class="ab-actions">
                    <button class="ab-command" data-import>${icon.upload} Importar</button>
                    <button class="ab-command" data-export-all>${icon.download} Exportar tudo</button>
                    <button class="ab-command" data-open-folder>${icon.folder} Abrir pasta</button>
                </div>
            </div>
            <div class="ab-grid">
                <div class="ab-card"><span>Backups</span><strong>${backupCount}</strong><small>${fmtBytes(backupSize)}</small></div>
                <div class="ab-card"><span>Capturas</span><strong>${snapshotCount}</strong><small>${fmtBytes(snapshotSize)}</small></div>
                <div class="ab-card"><span>Armazenamento total</span><strong>${fmtBytes(state.stats.backup_bytes)}</strong><small>Backups + capturas</small></div>
                <div class="ab-card"><span>Monitor</span><strong>${esc(activeGame)}</strong></div>
            </div>
            <div class="ab-status-line">
                <span class="ab-badge">${icon.shield} ${ignoredCount} apps ignorados</span>
                <span class="ab-badge">${icon.folder} Livre no disco: ${fmtBytes(state.stats.disk_free_bytes)}</span>
                <span class="ab-badge">${icon.save} Ultimo backup: ${esc(lastBackup ? backupTitle(lastBackup) : "nenhum")}</span>
                <span class="ab-badge">${icon.game} Ultima captura: ${esc(lastSnapshot ? snapshotGameName(lastSnapshot) : "nenhuma")}</span>
            </div>
            <div class="ab-section">
                <div class="ab-section-head"><strong>O que pode ser restaurado</strong></div>
                <div style="padding:14px;">${sourceCards("backup")}</div>
            </div>
            <div class="ab-grid two">
                <div class="ab-section">
                    <div class="ab-section-head"><strong>Backups recentes</strong><button class="ab-command" data-tab-jump="backups">Ver todos</button></div>
                    <div class="ab-list">${recentBackups || '<div class="ab-empty">Nenhum backup ainda.</div>'}</div>
                </div>
                <div class="ab-section">
                    <div class="ab-section-head"><strong>Capturas recentes</strong><button class="ab-command" data-tab-jump="captures">Ver jogos</button></div>
                    <div class="ab-list">${recentSnapshots || '<div class="ab-empty">Nenhuma captura ainda.</div>'}</div>
                </div>
            </div>
        `;
    }

    function backupsView() {
        const rows = state.backups.map((item) => {
            const folder = item.folder || "";
            const meta = [formatDateText(item.timestamp), fmtBytes(item.size), item.file_count ? `${item.file_count} arquivos` : ""].filter(Boolean).join(" | ");
            return `
                <div class="ab-row" data-folder="${esc(folder)}">
                    <div class="ab-media-row">
                        ${mediaThumb(item, "backup")}
                        <div class="ab-backup-summary">
                            <div class="ab-row-title">${esc(backupTitle(item))}</div>
                            <div class="ab-row-meta">${esc(meta)}</div>
                            <div class="ab-row-copy">${esc(backupShortDescription(item))}</div>
                            ${dataChips(item, "backup")}
                        </div>
                        <div class="ab-actions">
                            <button class="ab-icon" data-details="backup" title="Detalhes">${icon.info}</button>
                            <button class="ab-icon" data-rename-backup title="Renomear">${icon.edit}</button>
                            <button class="ab-icon" data-export-backup title="Exportar">${icon.download}</button>
                            <button class="ab-icon" data-restore-backup title="Restaurar">${icon.restore}</button>
                            <button class="ab-icon" data-delete-backup title="Apagar">${icon.trash}</button>
                        </div>
                    </div>
                </div>
            `;
        }).join("");
        return `
            <div class="ab-section">
                <div class="ab-section-head"><strong>${state.backups.length} backups</strong><div class="ab-actions"><button class="ab-command" data-import>${icon.upload} Importar</button><button class="ab-command" data-export-all>${icon.download} Exportar tudo</button><button class="ab-command primary" data-full-backup>${icon.save} Novo backup</button></div></div>
                <div class="ab-list">${rows || '<div class="ab-empty">Nenhum backup encontrado.</div>'}</div>
            </div>
        `;
    }

    function capturesView() {
        const groups = snapshotsByGame();
        if (!state.captureGame && groups.length) state.captureGame = groups[0].key;
        const selected = groups.find((group) => group.key === state.captureGame) || groups[0];
        const gameCards = groups.map((group) => `
            <button class="ab-game-card ${selected && selected.key === group.key ? "active" : ""}" data-capture-game="${esc(group.key)}">
                ${group.appid ? gameCoverTile(group.appid, group.name, true) : icon.game}
                <span style="min-width:0; flex:1; text-align:left;"><strong style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(group.name)}</strong><small style="color:var(--ab-muted);">${group.items.length} capturas | ${fmtBytes(group.size)}</small></span>
            </button>
        `).join("");
        const rows = (selected ? selected.items : []).map((item) => {
            const id = item.id || item.folder || "";
            const meta = [formatDateText(item.timestamp), item.saveModeLabel ? `Modo ${item.saveModeLabel}` : "", fmtBytes(item.size), item.fileCount ? `${item.fileCount} arquivos` : ""].filter(Boolean).join(" | ");
            return `
                <div class="ab-row" data-snapshot="${esc(id)}">
                    <div class="ab-media-row">
                        ${mediaThumb(item, "snapshot")}
                        <div><div class="ab-row-title">${esc(snapshotTitle(item))}</div><div class="ab-row-meta">${esc(meta)}</div><div class="ab-row-copy">${esc(snapshotDescription(item))}</div>${dataChips(item, "snapshot")}</div>
                        <div class="ab-actions">
                            <button class="ab-icon" data-details="snapshot" title="Detalhes">${icon.info}</button>
                            <button class="ab-icon" data-rename-snapshot title="Renomear">${icon.edit}</button>
                            <button class="ab-icon" data-restore-snapshot title="Restaurar">${icon.restore}</button>
                            <button class="ab-icon" data-delete-snapshot title="Apagar">${icon.trash}</button>
                        </div>
                    </div>
                </div>
            `;
        }).join("");
        return `
            <div class="ab-split">
                <div class="ab-section" style="margin-top:0;">
                    <div class="ab-section-head"><strong>Jogos com capturas</strong></div>
                    <div class="ab-game-list" style="padding:12px;">${gameCards || '<div class="ab-empty">Nenhum jogo capturado.</div>'}</div>
                </div>
                <div class="ab-section" style="margin-top:0;">
                    <div class="ab-section-head"><strong>${selected ? esc(selected.name) : "Capturas"}</strong><button class="ab-command primary" data-capture>${icon.save} Capturar jogo atual</button></div>
                    <div class="ab-list">${rows || '<div class="ab-empty">Selecione um jogo para ver as capturas.</div>'}</div>
                </div>
            </div>
        `;
    }

    function gamesView() {
        const apps = state.apps || [];
        const rows = apps.map((app) => {
            const appid = String(app.appid || "");
            const name = app.name || `AppID ${appid}`;
            return `
                <div class="ab-row" data-appid="${esc(appid)}" data-game-name="${esc(name)}">
                    <div style="display:flex; align-items:center; gap:12px; min-width:0;">
                        ${gameCoverTile(appid, name, false)}
                        <div style="min-width:0;"><div class="ab-row-title">${esc(name)}</div><div class="ab-row-meta">AppID ${esc(appid)}${app.ignored ? " | ignorado" : ""}</div></div>
                    </div>
                    <div class="ab-actions">
                        <button class="ab-icon" data-capture-app title="Capturar">${icon.save}</button>
                    </div>
                </div>
            `;
        }).join("");
        return `
            <div class="ab-section" style="margin-top:0;">
                <div class="ab-section-head">
                    <strong><span data-games-count>${apps.length}</span> jogos</strong>
                    <input class="ab-search" data-game-search placeholder="Buscar jogo ou AppID..." value="${esc(state.query)}">
                </div>
                <div class="ab-list" data-game-list>${rows || '<div class="ab-empty">Nenhum jogo encontrado.</div>'}</div>
                <div class="ab-empty" data-games-empty style="display:none;">Nenhum jogo encontrado.</div>
            </div>
        `;
    }

    function settingsView() {
        const cfg = state.settings || {};
        const mode = cfg.backup_mode || "semi";
        const theme = currentTheme();
        const backupPath = cfg.backup_path || "";
        const currentBackupPath = cfg.backup_current_path || cfg.backup_default_path || backupPath || "pasta backups dentro do plugin";
        const usingDefaultBackupPath = !backupPath;
        const modes = [
            ["semi", "Perguntar ao fechar", "Recomendado", "Quando um jogo fecha, pergunta se você quer criar uma captura leve só daquele AppID."],
            ["manual", "Somente manual", "Mais controle", "Não dispara ao fechar jogos. Você cria backups e capturas pelos botões do painel."],
            ["auto", "Capturar sozinho", "Pode ocupar disco", "Cria uma captura automaticamente ao detectar que o jogo foi fechado. Use só se quiser registrar tudo."],
        ];
        const themes = [
            ["blue", "Azul"],
            ["purple", "Roxo"],
            ["green", "Verde"],
            ["red", "Vermelho"],
        ];
        return `
            <form class="ab-form" data-settings-form>
                <div class="ab-field">
                    <label>Ao fechar um jogo</label>
                    <input type="hidden" name="backup_mode" value="${esc(mode)}">
                    <div class="ab-mode-grid">
                        ${modes.map(([id, title, tag, copy]) => `
                            <button type="button" class="ab-mode-card ${mode === id ? "active" : ""}" data-mode="${id}">
                                <strong>${esc(title)}</strong><em>${esc(tag)}</em><span>${esc(copy)}</span>
                            </button>
                        `).join("")}
                    </div>
                    <div class="ab-save-note" data-mode-note>${esc(modeNote(mode))}</div>
                </div>
                <div class="ab-field">
                    <label>Cor do painel</label>
                    <input type="hidden" name="theme" value="${esc(theme)}">
                    <div class="ab-theme-grid">
                        ${themes.map(([id, label]) => `
                            <button type="button" class="ab-theme-card ${theme === id ? "active" : ""}" data-theme-choice="${id}">
                                <span class="ab-swatch ${id}"></span><strong>${esc(label)}</strong>
                            </button>
                        `).join("")}
                    </div>
                </div>
                <label class="ab-option">
                    <span><strong>Usar API Ludusavi/PCGamingWiki</strong><p>Usa a API/manifest do Ludusavi para encontrar saves Steam e Windows. Alguns jogos salvam fora da pasta da Steam, como em Documentos ou AppData, e essa base ajuda a achar esses caminhos corretos por jogo.</p></span>
                    <input class="ab-toggle" type="checkbox" name="use_save_location_api" ${cfg.use_save_location_api !== false ? "checked" : ""}>
                </label>
                <div class="ab-option">
                    <span>
                        <strong>Pasta dos backups</strong>
                        <p>${usingDefaultBackupPath ? "Usando o caminho padrão dentro do plugin. Bom para manter tudo junto com o AchievementBackup." : "Usando uma pasta personalizada para backups e capturas. Ideal se você quer salvar em outro disco ou pasta maior."}</p>
                        <code class="ab-path-code" title="${esc(currentBackupPath)}">${esc(currentBackupPath)}</code>
                        <input type="hidden" name="backup_path" value="${esc(backupPath)}">
                    </span>
                    <span class="ab-actions">
                        <button class="ab-command" type="button" data-pick-backup-path>${icon.folder} Escolher pasta</button>
                        <button class="ab-command" type="button" data-reset-backup-path>Usar padrão</button>
                    </span>
                </div>
                <label class="ab-option">
                    <span><strong>Busca extra de saves externos</strong><p>Vai além da API e procura pastas com nomes parecidos com o jogo. Ajuda em casos raros, mas pode incluir arquivos inesperados; deixe desligado se quiser capturas mais limpas.</p></span>
                    <input class="ab-toggle" type="checkbox" name="broad_external_scan" ${cfg.broad_external_scan ? "checked" : ""}>
                </label>
                <label class="ab-option">
                    <span><strong>Incluir externos no backup completo</strong><p>Adiciona saves externos encontrados pela API e pela busca extra ao backup geral, junto com appcache/stats, userdata e config/stplug-in. Desligue para backups menores.</p></span>
                    <input class="ab-toggle" type="checkbox" name="backup_all_external_saves" ${cfg.backup_all_external_saves === true ? "checked" : ""}>
                </label>
                <div class="ab-option">
                    <span><strong>Perfil do plugin</strong><p>Guarda configurações, cor, modo de captura e apps ignorados em JSON. Se você reinstalar o plugin ou trocar a pasta, pode importar esse perfil para manter tudo igual.</p></span>
                    <span class="ab-actions"><button class="ab-command" type="button" data-import-settings>${icon.upload} Importar</button><button class="ab-command" type="button" data-export-settings>${icon.download} Exportar</button></span>
                </div>
                <div class="ab-save-note" data-autosave-note>Alterações nesta tela são salvas automaticamente.</div>
            </form>
        `;
    }

    function ignoredView() {
        const ignored = new Set((state.settings.ignored_appids || []).map(String));
        const apps = state.apps
            .sort((a, b) => {
                const ai = ignored.has(String(a.appid || "")) ? 1 : 0;
                const bi = ignored.has(String(b.appid || "")) ? 1 : 0;
                if (ai !== bi) return bi - ai;
                return String(a.name || "").localeCompare(String(b.name || ""));
            });
        const rows = apps.map((app) => {
            const appid = String(app.appid || "");
            const isIgnored = ignored.has(appid);
            const name = app.name || `AppID ${appid}`;
            return `
                <label class="ab-row" data-ignore-row="${esc(appid)}" data-appid="${esc(appid)}" data-game-name="${esc(name)}" style="grid-template-columns:1fr auto;">
                    <span style="display:flex; align-items:center; gap:12px; min-width:0;">
                        ${gameCoverTile(appid, name, false)}
                        <span style="min-width:0;">
                            <span class="ab-row-title">${esc(name)}</span>
                            <span class="ab-row-meta">AppID ${esc(appid)}${isIgnored ? " | ignorado, não dispara captura" : " | monitorado normalmente"}</span>
                        </span>
                    </span>
                    <input class="ab-toggle" type="checkbox" data-ignore-appid="${esc(appid)}" ${isIgnored ? "checked" : ""}>
                </label>
            `;
        }).join("");
        return `
            <div class="ab-section" style="margin-top:0;">
                <div class="ab-section-head">
                    <div><strong>${ignored.size} apps ignorados</strong><div class="ab-row-meta">Marcou, salvou. Apps ignorados aparecem primeiro.</div></div>
                    <input class="ab-search" data-ignored-search placeholder="Buscar jogo ou AppID..." value="${esc(state.ignoredQuery)}">
                </div>
                <div class="ab-list" data-ignored-list>${rows || '<div class="ab-empty">Nenhum app encontrado.</div>'}</div>
                <div class="ab-empty" data-ignored-empty style="display:none;">Nenhum app encontrado.</div>
            </div>
        `;
    }

    async function render() {
        let overlay = document.getElementById(ids.overlay);
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = ids.overlay;
            document.body.appendChild(overlay);
        }
        applyTheme(currentTheme());
        overlay.dataset.abTheme = currentTheme();
        overlay.innerHTML = shell();
        lockOverlayScroll(overlay);
        bind();
    }

    function lockOverlayScroll(overlay) {
        if (!overlay || overlay.__abScrollLock) return;
        overlay.__abScrollLock = true;
        const findScroller = (start) => {
            let node = start;
            while (node && node !== overlay) {
                const style = window.getComputedStyle(node);
                const canScroll = /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight;
                if (canScroll) return node;
                node = node.parentElement;
            }
            return null;
        };
        overlay.addEventListener("wheel", (event) => {
            const scroller = findScroller(event.target);
            event.stopPropagation();
            if (!scroller) {
                event.preventDefault();
                return;
            }
            const atTop = scroller.scrollTop <= 0;
            const atBottom = Math.ceil(scroller.scrollTop + scroller.clientHeight) >= scroller.scrollHeight;
            if ((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom)) {
                event.preventDefault();
            }
        }, { passive: false });
        overlay.addEventListener("touchmove", (event) => event.stopPropagation(), { passive: false });
    }

    function isEditingField() {
        const overlay = document.getElementById(ids.overlay);
        const active = document.activeElement;
        return Boolean(
            overlay &&
            active &&
            overlay.contains(active) &&
            /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)
        );
    }

    function pauseLiveRefresh(ms) {
        state.editingUntil = Math.max(state.editingUntil || 0, Date.now() + (ms || 4000));
    }

    async function softRefresh() {
        const overlay = document.getElementById(ids.overlay);
        if (!overlay) return;
        if (Date.now() < (state.editingUntil || 0) || isEditingField()) return;
        try {
            await refreshData();
            if (Date.now() < (state.editingUntil || 0) || isEditingField()) return;
            const content = overlay.querySelector(".ab-content");
            const top = overlay.querySelector(".ab-top");
            if (!content || !top) return;
            const scrollTop = content.scrollTop;
            applyTheme(currentTheme());
            top.querySelector("h1").textContent = titleForTab();
            top.querySelector("p").textContent = subtitleForTab();
            content.innerHTML = contentForTab();
            content.scrollTop = scrollTop;
            bind();
        } catch (e) {}
    }

    function startLiveRefresh() {
        if (state.liveTimer) return;
        state.liveTimer = setInterval(softRefresh, 1000);
    }

    function applyListSearch(input, listSelector, emptySelector, countSelector) {
        const overlay = document.getElementById(ids.overlay);
        if (!overlay || !input) return;
        const query = input.value.trim().toLowerCase();
        const rows = Array.from(overlay.querySelectorAll(`${listSelector} .ab-row`));
        let visible = 0;
        rows.forEach((row) => {
            const text = `${row.dataset.gameName || ""} ${row.dataset.appid || ""} ${row.textContent || ""}`.toLowerCase();
            const match = !query || text.includes(query);
            row.style.display = match ? "" : "none";
            if (match) visible += 1;
        });
        const empty = overlay.querySelector(emptySelector);
        if (empty) empty.style.display = rows.length && !visible ? "" : "none";
        if (countSelector) {
            const count = overlay.querySelector(countSelector);
            if (count) count.textContent = String(visible);
        }
    }

    function bind() {
        const overlay = document.getElementById(ids.overlay);
        overlay.querySelector("[data-close]").onclick = () => overlay.remove();
        overlay.querySelectorAll("[data-about]").forEach((btn) => btn.onclick = aboutDialog);
        overlay.querySelectorAll("[data-tab]").forEach((btn) => btn.onclick = () => { state.tab = btn.dataset.tab; render(); });
        overlay.querySelectorAll("[data-tab-jump]").forEach((btn) => btn.onclick = () => { state.tab = btn.dataset.tabJump; render(); });
        overlay.querySelectorAll("[data-full-backup]").forEach((btn) => btn.onclick = fullBackup);
        overlay.querySelectorAll("[data-capture]").forEach((btn) => btn.onclick = captureCurrent);
        overlay.querySelectorAll("[data-import]").forEach((btn) => btn.onclick = importZip);
        overlay.querySelectorAll("[data-export-all]").forEach((btn) => btn.onclick = () => exportScope("all"));
        overlay.querySelectorAll("[data-export-settings]").forEach((btn) => btn.onclick = exportSettings);
        overlay.querySelectorAll("[data-import-settings]").forEach((btn) => btn.onclick = importSettings);
        overlay.querySelectorAll("[data-open-folder]").forEach((btn) => btn.onclick = () => json("/achievements/open").then(() => toast("Pasta aberta.")).catch((e) => toast(e.message)));
        overlay.querySelectorAll("[data-export-backup]").forEach((btn) => btn.onclick = () => exportScope(btn.closest("[data-folder]").dataset.folder));
        overlay.querySelectorAll("[data-rename-backup]").forEach((btn) => btn.onclick = () => renameItem(btn.closest("[data-folder]").dataset.folder, btn.closest("[data-folder]").querySelector(".ab-row-title").textContent));
        overlay.querySelectorAll("[data-restore-backup]").forEach((btn) => btn.onclick = () => restoreBackup(btn.closest("[data-folder]").dataset.folder));
        overlay.querySelectorAll("[data-delete-backup]").forEach((btn) => btn.onclick = () => deleteBackup(btn.closest("[data-folder]").dataset.folder));
        overlay.querySelectorAll("[data-capture-app]").forEach((btn) => btn.onclick = () => captureApp(btn.closest("[data-appid]").dataset.appid, btn.closest("[data-appid]").dataset.gameName));
        overlay.querySelectorAll("[data-rename-snapshot]").forEach((btn) => btn.onclick = () => renameItem(btn.closest("[data-snapshot]").dataset.snapshot, btn.closest("[data-snapshot]").querySelector(".ab-row-title").textContent));
        overlay.querySelectorAll("[data-delete-snapshot]").forEach((btn) => btn.onclick = () => deleteSnapshot(btn.closest("[data-snapshot]").dataset.snapshot));
        overlay.querySelectorAll("[data-restore-snapshot]").forEach((btn) => btn.onclick = () => restoreSnapshot(btn.closest("[data-snapshot]").dataset.snapshot));
        overlay.querySelectorAll("[data-details]").forEach((btn) => btn.onclick = () => showDetails(btn.dataset.details, btn.closest("[data-folder],[data-snapshot]")));
        overlay.querySelectorAll("[data-capture-game]").forEach((btn) => btn.onclick = () => { state.captureGame = btn.dataset.captureGame; render(); });
        overlay.querySelectorAll("[data-mode]").forEach((btn) => btn.onclick = () => {
            const form = btn.closest("[data-settings-form]");
            form.backup_mode.value = btn.dataset.mode;
            form.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("active", item === btn));
            const note = form.querySelector("[data-mode-note]");
            if (note) note.textContent = modeNote(btn.dataset.mode);
            scheduleSettingsSave(form);
        });
        overlay.querySelectorAll("[data-theme-choice]").forEach((btn) => btn.onclick = () => {
            const form = btn.closest("[data-settings-form]");
            const theme = btn.dataset.themeChoice || "blue";
            pauseLiveRefresh(5000);
            form.theme.value = theme;
            state.settings = Object.assign({}, state.settings, { theme });
            applyTheme(theme);
            form.querySelectorAll("[data-theme-choice]").forEach((item) => item.classList.toggle("active", item === btn));
            scheduleSettingsSave(form);
        });
        overlay.querySelectorAll("[data-pick-backup-path]").forEach((btn) => btn.onclick = async () => {
            const form = btn.closest("[data-settings-form]");
            pauseLiveRefresh(120000);
            const originalHTML = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = `${icon.folder} Abrindo...`;
            toast("Abrindo seletor de pasta...");
            try {
                const result = await json("/settings/pick-backup-folder");
                if (!result.ok || !result.path) throw new Error(result.message || "Nenhuma pasta escolhida.");
                form.backup_path.value = result.path;
                state.settings = Object.assign({}, state.settings, { backup_path: result.path, backup_current_path: result.path });
                await saveSettings(form);
                await refreshData();
                render();
                toast("Pasta de backups atualizada.");
            } catch (e) {
                if (!String(e.message || "").includes("Nenhuma pasta")) toast(e.message || "Falha ao escolher pasta.");
            } finally {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
                pauseLiveRefresh(2000);
            }
        });
        overlay.querySelectorAll("[data-reset-backup-path]").forEach((btn) => btn.onclick = async () => {
            const form = btn.closest("[data-settings-form]");
            pauseLiveRefresh(4000);
            form.backup_path.value = "";
            state.settings = Object.assign({}, state.settings, { backup_path: "", backup_current_path: state.settings.backup_default_path || "" });
            await saveSettings(form);
            await refreshData();
            render();
            toast("Pasta padrão restaurada.");
        });
        const search = overlay.querySelector("[data-game-search]");
        if (search) {
            applyListSearch(search, "[data-game-list]", "[data-games-empty]", "[data-games-count]");
            search.onfocus = () => pauseLiveRefresh(8000);
            search.onkeydown = () => pauseLiveRefresh(8000);
            search.onclick = () => pauseLiveRefresh(8000);
            search.oninput = () => {
                pauseLiveRefresh(8000);
                state.query = search.value;
                applyListSearch(search, "[data-game-list]", "[data-games-empty]", "[data-games-count]");
            };
        }
        const ignoredSearch = overlay.querySelector("[data-ignored-search]");
        if (ignoredSearch) {
            applyListSearch(ignoredSearch, "[data-ignored-list]", "[data-ignored-empty]", "");
            ignoredSearch.onfocus = () => pauseLiveRefresh(8000);
            ignoredSearch.onkeydown = () => pauseLiveRefresh(8000);
            ignoredSearch.onclick = () => pauseLiveRefresh(8000);
            ignoredSearch.oninput = () => {
                pauseLiveRefresh(8000);
                state.ignoredQuery = ignoredSearch.value;
                applyListSearch(ignoredSearch, "[data-ignored-list]", "[data-ignored-empty]", "");
            };
        }
        overlay.querySelectorAll("[data-ignore-appid]").forEach((input) => input.onchange = () => updateIgnoredApp(input.dataset.ignoreAppid, input.checked));
        overlay.querySelectorAll("[data-cover-sources]").forEach((img) => {
            img.onerror = () => {
                const list = String(img.dataset.coverSources || "").split("|").filter(Boolean);
                const idx = Number(img.dataset.coverIndex || 0);
                if (idx < list.length) {
                    img.dataset.coverIndex = String(idx + 1);
                    img.src = list[idx];
                    return;
                }
                img.style.display = "none";
                if (img.nextElementSibling) img.nextElementSibling.style.display = "grid";
            };
            if (img.complete && img.naturalWidth === 0) img.onerror();
        });
        const form = overlay.querySelector("[data-settings-form]");
        if (form) {
            form.onsubmit = (event) => event.preventDefault();
            form.querySelectorAll("input, select, textarea").forEach((field) => field.onchange = () => scheduleSettingsSave(form));
        }
    }

    async function fullBackup() {
        if (!(await confirmDialog("Criar backup completo", "O backup pode demorar dependendo do tamanho da Steam.", "Criar"))) return;
        state.busy = true;
        try {
            const result = await post("/backup/full", { appid: 0, game_name: "Steam Session", reason: "manual-ui" });
            toast(result.message || "Backup completo criado.");
            await refreshData();
            render();
        } catch (e) {
            toast(e.message);
        } finally {
            state.busy = false;
        }
    }

    async function captureCurrent() {
        state.busy = true;
        try {
            const result = await post("/achievements/backup", { reason: "manual-ui" });
            toast(result.message || "Captura criada.");
            await refreshData();
            render();
        } catch (e) {
            toast(e.message);
        } finally {
            state.busy = false;
        }
    }

    async function captureApp(appid, name) {
        state.busy = true;
        try {
            const result = await post("/achievements/backup", { appid, game_name: name, reason: "manual-ui" });
            toast(result.message || `Captura criada para ${name}.`);
            await refreshData();
            state.tab = "captures";
            render();
        } catch (e) {
            toast(e.message);
        } finally {
            state.busy = false;
        }
    }

    function sleep(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function exportScope(scope) {
        const target = scope || "all";
        const all = target === "all";
        const ok = await confirmDialog(
            all ? "Exportar tudo" : "Exportar backup",
            all
                ? "Vai gerar um arquivo ZIP com todos os backups completos e capturas por jogo. Pode demorar e ocupar bastante espaço temporário enquanto o ZIP é criado."
                : "Vai gerar um arquivo ZIP com este backup. Use para guardar em outro lugar ou importar depois.",
            "Exportar"
        );
        if (!ok) return;
        state.busy = true;
        let progressDialogRef = null;
        try {
            const defaultName = all ? "achievementbackup-backups-all.zip" : `achievementbackup-${target}.zip`;
            toast("Escolha onde salvar o ZIP...");
            const picked = await post("/export/pick-file", { filename: defaultName });
            if (!picked.ok || !picked.path) throw new Error(picked.message || "Nenhum arquivo escolhido.");
            progressDialogRef = progressDialog("Exportando", `Salvando em: ${picked.path}`);
            const started = await post("/export/start", { scope: target, output_path: picked.path });
            const tid = started.id;
            if (!tid) throw new Error("Não consegui iniciar a exportação.");
            let progress = null;
            for (let i = 0; i < 720; i += 1) {
                progress = await json(`/export/progress/${encodeURIComponent(tid)}`);
                if (progress.status === "ready") break;
                if (progress.status === "error") throw new Error("Falha ao criar o ZIP de exportação.");
                if (progress.status === "canceled") throw new Error("Exportação cancelada.");
                const percent = progress.total_bytes ? (Number(progress.done_bytes || 0) / Number(progress.total_bytes || 1)) * 100 : 0;
                const done = progress.total_bytes ? `${fmtBytes(progress.done_bytes)} de ${fmtBytes(progress.total_bytes)}` : `${progress.done_files || 0} arquivos`;
                progressDialogRef.update(`Exportando... ${done}`, percent);
                await sleep(1000);
            }
            if (!progress || progress.status !== "ready") throw new Error("A exportação demorou demais. Tente novamente.");
            progressDialogRef.update(`Exportação concluída: ${progress.output_path || picked.path}`, 100);
            await sleep(1200);
            toast(`ZIP salvo em: ${progress.output_path || picked.path}`);
        } catch (e) {
            if (!String(e.message || "").includes("Nenhum arquivo")) toast(e.message || "Falha ao exportar.");
        } finally {
            if (progressDialogRef) progressDialogRef.close();
            state.busy = false;
        }
    }

    async function importZip() {
        const ok = await confirmDialog(
            "Importar backup",
            "Escolha um ZIP exportado pelo AchievementBackup. Ele vai adicionar backups e capturas à pasta atual sem apagar os arquivos que já existem.",
            "Importar"
        );
        if (!ok) return;
        state.busy = true;
        let progressDialogRef = null;
        try {
            progressDialogRef = progressDialog("Importando", "Escolha o ZIP exportado pelo AchievementBackup.");
            const result = await post("/import/pick-file", {});
            progressDialogRef.update(`Importando arquivos de ${result.path || "ZIP selecionado"}...`, 35);
            await refreshData();
            render();
            progressDialogRef.update(`Importação concluída: ${result.files || 0} arquivos adicionados.`, 100);
            await sleep(900);
            toast(`Importação concluída: ${result.files || 0} arquivos.`);
        } catch (e) {
            if (!String(e.message || "").includes("Nenhum arquivo")) toast(e.message || "Falha ao importar.");
        } finally {
            if (progressDialogRef) progressDialogRef.close();
            state.busy = false;
        }
    }

    function exportSettings() {
        const payload = {
            name: "AchievementBackup settings",
            exportedAt: new Date().toISOString(),
            settings: state.settings || {},
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "achievementbackup-settings.json";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast("Configurações exportadas.");
    }

    function importSettings() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".json,application/json";
        input.onchange = async () => {
            const file = input.files && input.files[0];
            if (!file) return;
            try {
                const data = JSON.parse(await file.text());
                const settings = data.settings && typeof data.settings === "object" ? data.settings : data;
                const payload = Object.assign({}, state.settings, settings);
                const result = await post("/settings", payload);
                state.settings = result.config || payload;
                await refreshData();
                render();
                toast("Configurações importadas.");
            } catch (e) {
                toast(e.message || "Falha ao importar configurações.");
            }
        };
        input.click();
    }

    async function renameItem(folder, currentName) {
        const next = await inputDialog("Renomear", "Nome exibido", currentName || folder);
        if (next == null) return;
        try {
            await post("/rename", { folder, new_name: next });
            await refreshData();
            render();
            toast("Nome atualizado.");
        } catch (e) {
            toast(e.message || "Falha ao renomear.");
        }
    }

    async function restoreBackup(folder) {
        if (!(await confirmDialog("Restaurar backup", "A Steam pode ser fechada durante a restauracao.", "Restaurar"))) return;
        try {
            await fetch(`${API}/restore/${encodeURIComponent(folder)}`, { method: "POST" });
            toast("Restauração iniciada em terminal externo.");
        } catch (e) {
            toast(e.message || "Falha ao restaurar.");
        }
    }

    async function deleteBackup(folder) {
        if (!(await confirmDialog("Apagar backup", folder, "Apagar"))) return;
        try {
            await fetch(`${API}/delete/${encodeURIComponent(folder)}`, { method: "POST" });
            await refreshData();
            render();
            toast("Backup apagado.");
        } catch (e) {
            toast(e.message || "Falha ao apagar.");
        }
    }

    async function deleteSnapshot(id) {
        if (!(await confirmDialog("Apagar captura", id, "Apagar"))) return;
        try {
            await fetch(`${API}/delete/${encodeURIComponent(id)}`, { method: "POST" });
            await refreshData();
            render();
            toast("Captura apagada.");
        } catch (e) {
            toast(e.message || "Falha ao apagar captura.");
        }
    }

    async function restoreSnapshot(id) {
        const item = state.snapshots.find((snapshot) => snapshotId(snapshot) === id) || { id };
        const choice = await restoreSnapshotDialog(item);
        if (!choice) return;
        state.busy = true;
        try {
            const result = await post("/achievements/restore", { id, createSafetyBackup: choice.createSafetyBackup });
            toast(result.message || "Captura restaurada.");
            await refreshData();
            render();
        } catch (e) {
            toast(e.message);
        } finally {
            state.busy = false;
        }
    }

    async function showDetails(kind, row) {
        const scope = row.dataset.folder || row.dataset.snapshot || "";
        try {
            const data = await json(`/details?type=${encodeURIComponent(kind)}&scope=${encodeURIComponent(scope)}`);
            const overlay = document.createElement("div");
            const isSnapshot = (data.type || kind) === "snapshot";
            const original = isSnapshot
                ? state.snapshots.find((item) => snapshotId(item) === scope) || {}
                : state.backups.find((item) => (item.folder || "") === scope) || {};
            const title = isSnapshot ? snapshotTitle(original) : backupTitle(Object.assign({ folder: scope }, original));
            const copy = isSnapshot ? snapshotDescription(original) : backupDescription(original);
            const games = (data.games || []).map((game) => `
                <div class="ab-detail-item">
                    <strong>${esc(game.name || game.appid)}</strong>
                    <div>${esc(game.appid || "")} | ${Number(game.totalFiles || 0)} arquivos</div>
                    <div>${esc(Object.entries(game.categories || {}).map(([k, v]) => `${k}: ${v}`).join(" | ") || "Arquivos protegidos sem categoria detalhada.")}</div>
                </div>
            `).join("");
            overlay.className = "ab-modal-lite";
            overlay.dataset.abTheme = currentTheme();
            overlay.innerHTML = `
                <div class="ab-dialog">
                    <div class="ab-dialog-head">
                        <div><strong>${esc(title)}</strong><p>${esc([formatDateText(data.timestamp || original.timestamp), isSnapshot ? "Captura por jogo" : "Backup Steam completo", data.saveModeLabel ? `Modo ${data.saveModeLabel}` : ""].filter(Boolean).join(" | "))}</p></div>
                        <button class="ab-icon" data-close-detail>${icon.close}</button>
                    </div>
                    <div class="ab-dialog-body">
                        <div class="ab-row-copy" style="margin-top:0;">${esc(copy)}</div>
                        <div style="margin-top:14px;">${sourceCards(isSnapshot ? "snapshot" : "backup")}</div>
                        <div class="ab-section-head" style="padding:14px 0 8px; border-bottom:0;"><strong>${isSnapshot ? "Arquivos desta captura" : "Jogos dentro do backup"}</strong></div>
                        <div class="ab-detail-list">${games || '<div class="ab-empty">Sem detalhes adicionais.</div>'}</div>
                    </div>
                    <div class="ab-dialog-actions"><button class="ab-command primary" data-close-detail>Fechar</button></div>
                </div>
            `;
            overlay.querySelectorAll("[data-close-detail]").forEach((btn) => btn.onclick = () => overlay.remove());
            document.body.appendChild(overlay);
        } catch (e) {
            toast(e.message);
        }
    }

    function collectSettings(form) {
        const payload = {
            backup_mode: form.backup_mode.value,
            use_save_location_api: form.use_save_location_api.checked,
            broad_external_scan: form.broad_external_scan.checked,
            backup_all_external_saves: form.backup_all_external_saves.checked,
            ignored_appids: state.settings.ignored_appids || [],
            theme: form.theme ? form.theme.value : currentTheme(),
            backup_path: form.backup_path ? form.backup_path.value.trim() : (state.settings.backup_path || ""),
        };
        return payload;
    }

    function scheduleSettingsSave(form) {
        pauseLiveRefresh(2500);
        const note = document.querySelector("[data-autosave-note]");
        if (note) note.textContent = "Salvando...";
        clearTimeout(state.saveTimer);
        state.saveTimer = setTimeout(() => saveSettings(form), 350);
    }

    async function saveSettings(form) {
        const payload = collectSettings(form);
        try {
            const result = await post("/settings", payload);
            state.settings = result.config || payload;
            state.settings.theme = payload.theme || currentTheme();
            applyTheme(state.settings.theme);
            const note = document.querySelector("[data-autosave-note]");
            if (note) note.textContent = "Salvo automaticamente.";
        } catch (e) {
            const note = document.querySelector("[data-autosave-note]");
            if (note) note.textContent = "Falha ao salvar.";
            toast(e.message);
        }
    }

    async function updateIgnoredApp(appid, checked) {
        const current = new Set((state.settings.ignored_appids || []).map(String));
        if (checked) current.add(String(appid));
        else current.delete(String(appid));
        const payload = Object.assign({}, state.settings, {
            ignored_appids: Array.from(current).sort((a, b) => Number(a) - Number(b)),
            theme: currentTheme(),
        });
        state.settings = payload;
        render();
        try {
            const result = await post("/settings", payload);
            state.settings = result.config || payload;
            toast(checked ? "App ignorado." : "App monitorado.");
            render();
        } catch (e) {
            toast(e.message || "Falha ao salvar app ignorado.");
            await refreshData();
            render();
        }
    }

    function injectFab() {
        ensureStyles();
        if (document.getElementById(ids.fab)) return;
        const button = document.createElement("button");
        button.id = ids.fab;
        button.type = "button";
        button.innerHTML = `<img src="${API}/assets/mimikyu.png" alt="AB">`;
        button.title = "Abrir AchievementBackup";
        button.onclick = async () => {
            try {
                await refreshData();
                render();
            } catch (e) {
                toast(e.message || "Falha ao abrir painel.");
            }
        };
        document.body.appendChild(button);
    }

    function startPendingWatcher() {
        setInterval(async () => {
            if (state.pendingPromptOpen) return;
            try {
                const pending = await json("/pending");
                if (!pending.pending) return;
                const key = `${pending.appid || ""}:${pending.game_name || ""}`;
                if (state.pendingPromptKey === key) return;
                state.pendingPromptOpen = true;
                state.pendingPromptKey = key;
                try {
                    const ok = await capturePromptDialog(pending.game_name || "jogo atual", pending.appid);
                    await post("/pending/action", { action: ok ? "confirm" : "cancel", appid: pending.appid, game_name: pending.game_name });
                    state.pendingPromptKey = "";
                    await softRefresh();
                } finally {
                    state.pendingPromptOpen = false;
                }
            } catch (e) {}
        }, 1600);
    }

    function boot() {
        if (!document.body) {
            setTimeout(boot, 500);
            return;
        }
        injectFab();
        startPendingWatcher();
        setInterval(injectFab, 3000);
        startLiveRefresh();
    }

    boot();
})();

import { definePlugin } from "@steambrew/client";

declare const window: any;

let bootScheduled = false;
let pendingPromptVisible = false;
let pendingPromptWatcherStarted = false;
let uiWatchStarted = false;

const NATIVE_FAB_ID = "achievementbackup-native-fab";
const LOADER_ID = "achievementbackup-global-loader";
const UI_URL = "http://localhost:9999/ui.js?surface=steam-client";

function ensureNativeFab() {
    if (!document.body || document.getElementById("ab-fab") || document.getElementById(NATIVE_FAB_ID)) return;

    const styleId = "achievementbackup-native-fab-style";
    if (!document.getElementById(styleId)) {
        const style = document.createElement("style");
        style.id = styleId;
        style.textContent = `
            #${NATIVE_FAB_ID} {
                position: fixed;
                right: 30px;
                bottom: 30px;
                width: 56px;
                height: 56px;
                z-index: 2147483646;
                border-radius: 999px;
                border: 2px solid rgba(255,255,255,.18);
                background: linear-gradient(135deg, #0ea5e9, #075985);
                color: #fff;
                box-shadow: 0 8px 28px rgba(14,165,233,.35);
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                font-family: "Motiva Sans", Arial, sans-serif;
                font-weight: 900;
                letter-spacing: .5px;
            }
            #${NATIVE_FAB_ID}:hover { transform: translateY(-2px); filter: brightness(1.1); }
        `;
        document.head.appendChild(style);
    }

    const button = document.createElement("button");
    button.id = NATIVE_FAB_ID;
    button.type = "button";
    button.title = "Abrir AchievementBackup";
    button.textContent = "AB";
    button.onclick = () => {
        bootScheduled = false;
        scheduleAchievementBackupUi(true);
        window.setTimeout(() => {
            const realFab = document.getElementById("ab-fab") as HTMLElement | null;
            if (realFab) realFab.click();
        }, 900);
    };
    document.body.appendChild(button);
}

function removeNativeFabIfPanelExists() {
    if (!document.getElementById("ab-fab")) return;
    const nativeFab = document.getElementById(NATIVE_FAB_ID);
    if (nativeFab) nativeFab.remove();
}

function scheduleAchievementBackupUi(force = false) {
    if (bootScheduled && !force) return;
    bootScheduled = true;

    const mount = async () => {
        try {
            if (!document.body) {
                window.setTimeout(mount, 500);
                return;
            }
            if (document.getElementById("ab-fab")) {
                removeNativeFabIfPanelExists();
                return;
            }
            ensureNativeFab();
            const oldLoader = document.getElementById(LOADER_ID);
            if (oldLoader) oldLoader.remove();

            const response = await fetch(`${UI_URL}&t=${Date.now()}`, { cache: "no-store" });
            if (!response.ok) throw new Error(`UI load failed: ${response.status}`);

            const script = document.createElement("script");
            script.id = LOADER_ID;
            script.textContent = await response.text();
            (document.body || document.documentElement).appendChild(script);
            window.setTimeout(removeNativeFabIfPanelExists, 300);
        } catch (error) {
            console.warn("[AchievementBackup] Global UI bootstrap failed", error);
            ensureNativeFab();
            bootScheduled = false;
            window.setTimeout(mount, 5000);
        }
    };

    window.setTimeout(mount, 3000);
    if (!uiWatchStarted) {
        uiWatchStarted = true;
        window.setInterval(() => {
            if (!document.getElementById("ab-fab")) {
                ensureNativeFab();
                bootScheduled = false;
                scheduleAchievementBackupUi();
            } else {
                removeNativeFabIfPanelExists();
            }
        }, 5000);
    }
}

function ensurePromptStyles() {
    if (document.getElementById("achievementbackup-prompt-style")) return;
    const style = document.createElement("style");
    style.id = "achievementbackup-prompt-style";
    style.textContent = `
        #achievementbackup-prompt-overlay {
            position: fixed; inset: 0; z-index: 2147483647; display: flex;
            align-items: center; justify-content: center; background: rgba(0,0,0,.72);
            font-family: "Motiva Sans", Arial, sans-serif; color: #fff;
        }
        .achievementbackup-prompt {
            width: min(480px, calc(100vw - 32px)); padding: 48px 36px;
            border: 1px solid #0ea5e9; border-radius: 16px;
            background: linear-gradient(145deg, #082f49 0%, #06111d 100%);
            box-shadow: 0 24px 60px rgba(0,0,0,.55), 0 0 28px rgba(14,165,233,.25);
            text-align: center;
        }
        .achievementbackup-prompt img { width: 160px; height: 75px; object-fit: cover; border-radius: 8px; margin-bottom: 24px; }
        .achievementbackup-prompt h2 { margin: 0 0 14px; font-size: 24px; font-weight: 800; }
        .achievementbackup-prompt p { margin: 0 0 30px; color: #cbd5e1; font-size: 15px; line-height: 1.55; }
        .achievementbackup-actions { display: flex; gap: 12px; justify-content: center; }
        .achievementbackup-actions button { border: 1px solid transparent; border-radius: 10px; padding: 12px 20px; color: #fff; font-weight: 800; cursor: pointer; }
        .achievementbackup-ignore { background: rgba(244,63,94,.12); border-color: rgba(244,63,94,.55) !important; }
        .achievementbackup-save { background: #16a34a; border-color: #22c55e !important; }
    `;
    document.head.appendChild(style);
}

function showGlobalPendingPrompt(gameName: string, appid: number | string) {
    if (pendingPromptVisible || document.getElementById("achievementbackup-prompt-overlay")) return;
    pendingPromptVisible = true;
    ensurePromptStyles();

    const overlay = document.createElement("div");
    overlay.id = "achievementbackup-prompt-overlay";
    const image = appid ? `<img src="https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/capsule_sm_120.jpg" onerror="this.style.display='none'">` : "";
    overlay.innerHTML = `
        <div class="achievementbackup-prompt">
            ${image}
            <h2>SessÃ£o Encerrada</h2>
            <p>VocÃª fechou <strong>${String(gameName || "este jogo").replace(/[<>&"]/g, "")}</strong>.<br>Deseja criar um backup de seguranÃ§a deste save?</p>
            <div class="achievementbackup-actions">
                <button class="achievementbackup-ignore" id="achievementbackup-ignore">IGNORAR</button>
                <button class="achievementbackup-save" id="achievementbackup-save">SALVAR</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const close = () => {
        pendingPromptVisible = false;
        overlay.remove();
    };
    overlay.querySelector("#achievementbackup-save")?.addEventListener("click", async () => {
        await fetch("http://localhost:9999/pending/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "confirm", appid, game_name: gameName })
        }).catch(() => {});
        close();
    });
    overlay.querySelector("#achievementbackup-ignore")?.addEventListener("click", async () => {
        await fetch("http://localhost:9999/pending/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "cancel" })
        }).catch(() => {});
        close();
    });
}

function startGlobalPendingPromptWatcher() {
    if (pendingPromptWatcherStarted) return;
    pendingPromptWatcherStarted = true;
    window.setInterval(async () => {
        if (pendingPromptVisible) return;
        try {
            const response = await fetch("http://localhost:9999/pending", { cache: "no-store" });
            const data = await response.json();
            if (data?.pending) showGlobalPendingPrompt(data.game_name, data.appid);
        } catch {}
    }, 1000);
}

export default definePlugin(() => {
    scheduleAchievementBackupUi();
    startGlobalPendingPromptWatcher();
    const React = window.SP_REACT;
    const icon = React?.createElement
        ? React.createElement("span", { style: { color: "#38bdf8", fontWeight: 800, fontSize: "12px" } }, "AB")
        : null;

    const openPanel = () => {
        scheduleAchievementBackupUi();
        window.setTimeout(() => {
            const button = document.getElementById("ab-fab") as HTMLElement | null;
            if (button) button.click();
        }, 450);
    };

    const content = React?.createElement
        ? React.createElement(
            "div",
            {
                style: {
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                    padding: "12px",
                    color: "#dbeafe",
                    fontFamily: "Motiva Sans, Arial, sans-serif"
                }
            },
            React.createElement(
                "div",
                {
                    style: {
                        fontSize: "13px",
                        lineHeight: 1.45,
                        color: "#9fb6c8"
                    }
                },
                "Backups, capturas e restauracao ficam disponiveis pelo painel flutuante."
            ),
            React.createElement(
                "button",
                {
                    onClick: openPanel,
                    style: {
                        border: "1px solid rgba(14, 165, 233, .75)",
                        borderRadius: "8px",
                        padding: "10px 12px",
                        background: "linear-gradient(135deg, #0ea5e9, #075985)",
                        color: "#fff",
                        fontWeight: 800,
                        cursor: "pointer",
                        textTransform: "uppercase",
                        letterSpacing: ".4px"
                    }
                },
                "Abrir AchievementBackup"
            )
        )
        : null;

    return {
        title: "AchievementBackup",
        icon: icon as any,
        content: content as any
    };
});

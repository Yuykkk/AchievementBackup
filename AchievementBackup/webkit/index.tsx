import { Millennium } from '@millennium/ui';

let uiBootScheduled = false;
let uiWatchStarted = false;

const scheduleAchievementBackupUi = () => {
    if (uiBootScheduled) return;
    uiBootScheduled = true;

    const mount = async () => {
        try {
            if (!document.body) {
                window.setTimeout(mount, 500);
                return;
            }
            if (document.getElementById('ab-fab')) return;
            const oldLoader = document.getElementById('achievementbackup-global-loader');
            if (oldLoader) oldLoader.remove();

            const response = await fetch('http://localhost:9999/ui.js?surface=steam-client', { cache: 'no-store' });
            if (!response.ok) throw new Error(`UI load failed: ${response.status}`);

            const script = document.createElement('script');
            script.id = 'achievementbackup-global-loader';
            script.textContent = await response.text();
            (document.body || document.documentElement).appendChild(script);
        } catch (error) {
            console.warn('[AchievementBackup] Library UI bootstrap failed', error);
            window.setTimeout(mount, 5000);
        }
    };

    window.setTimeout(mount, 1000);
    if (!uiWatchStarted) {
        uiWatchStarted = true;
        window.setInterval(() => {
            if (!document.getElementById('ab-fab')) {
                uiBootScheduled = false;
                scheduleAchievementBackupUi();
            }
        }, 5000);
    }
};

const injectStyle = () => {
    if (document.getElementById('achievementbackup-styles')) return;

    const style = document.createElement('style');
    style.id = 'achievementbackup-styles';
    style.textContent = `
        .achievementbackup-dot {
            width: 8px;
            height: 8px;
            background-color: #0ea5e9;
            border-radius: 50%;
            position: absolute;
            top: 4px;
            right: 4px;
            z-index: 99999;
            box-shadow: 0 0 5px rgba(14, 165, 233, 0.8);
            pointer-events: none;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 4px rgba(14, 165, 233, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0); }
        }
    `;
    document.head.appendChild(style);
};

const isVisible = (el: Element): boolean => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
};

const findSteamTab = (navName: 'store' | 'library'): HTMLElement | null => {
    const labels = navName === 'store'
        ? ['LOJA', 'STORE']
        : ['BIBLIOTECA', 'LIBRARY'];

    const modernNav = document.querySelector(`a[href*="steam://nav/${navName}"]`);
    if (modernNav && isVisible(modernNav)) return modernNav as HTMLElement;

    const webMatchers = navName === 'store'
        ? ['store.steampowered.com']
        : ['steam://open/games', 'steam://nav/library'];

    for (const matcher of webMatchers) {
        const webNav = document.querySelector(`a[href*="${matcher}"]`);
        if (webNav && isVisible(webNav)) return webNav as HTMLElement;
    }

    const allElements = document.querySelectorAll('a, div[class*="menuitem"], span[class*="menuitem"]');
    for (const el of Array.from(allElements)) {
        if (!el.textContent) continue;
        
        const text = el.textContent.trim().toUpperCase();
        if (labels.includes(text) && isVisible(el)) {
            const parentLink = el.closest('a');
            return (parentLink || el) as HTMLElement;
        }
    }

    return null;
};

const addDot = () => {
    const tabs = [
        findSteamTab('store'),
        findSteamTab('library'),
    ].filter((tab): tab is HTMLElement => Boolean(tab));

    for (const tab of tabs) {
        if (tab.querySelector('.achievementbackup-dot')) continue;

        const dot = document.createElement('div');
        dot.className = 'achievementbackup-dot';
        
        const computedStyle = window.getComputedStyle(tab);
        if (computedStyle.position === 'static') {
            tab.style.position = 'relative';
        }
        
        if (computedStyle.overflow === 'hidden') {
            tab.style.overflow = 'visible';
        }
        
        tab.appendChild(dot);
    }
};

let lastInjectionTime = 0;
const INJECTION_THROTTLE = 500;

const robustInject = () => {
    const now = Date.now();
    if (now - lastInjectionTime < INJECTION_THROTTLE) return;
    lastInjectionTime = now;
    
    addDot();
};

export default async function main() {
    console.log('[AchievementBackup] Frontend initializing...');
    
    Millennium.callServerMethod("achievementbackup.frontend_log", "Frontend initialized and running!");

    injectStyle();
    scheduleAchievementBackupUi();
    robustInject();
    setInterval(robustInject, 2000);
    
    const originalPushState = history.pushState;
    history.pushState = function (...args) {
        originalPushState.apply(this, args);
        setTimeout(robustInject, 150);
    };
    
    const originalReplaceState = history.replaceState;
    history.replaceState = function (...args) {
        originalReplaceState.apply(this, args);
        setTimeout(robustInject, 150);
    };
    
    window.addEventListener('popstate', () => setTimeout(robustInject, 150));
    
    let mutationTimeout: number | undefined;
    const observer = new MutationObserver(() => {
        window.clearTimeout(mutationTimeout);
        mutationTimeout = window.setTimeout(() => {
            robustInject();
        }, 300);
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
}

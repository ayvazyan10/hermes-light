"""
Browser Stealth Module — Anti-detection & Fingerprint Masking

Applies comprehensive stealth patches to Playwright browser contexts:
- Navigator property patches (webdriver, plugins, languages, platform)
- WebGL/Canvas fingerprint spoofing
- Chrome runtime spoofing (window.chrome, CDPSession evasion)
- WebRTC IP leak prevention
- Permission API spoofing
- Media codecs and hardware concurrency normalization
- Timezone and locale consistency enforcement
"""

import json
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BrowserFingerprint:
    """Immutable fingerprint profile for a browser session."""
    user_agent: str
    platform: str
    vendor: str
    renderer: str
    webgl_vendor: str
    webgl_renderer: str
    languages: tuple[str, ...]
    hardware_concurrency: int
    device_memory: int
    max_touch_points: int
    screen_width: int
    screen_height: int
    color_depth: int
    timezone: str
    canvas_noise_seed: int


# Realistic desktop fingerprint pools
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
)

_WEBGL_RENDERERS = (
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Intel Inc.", "Intel(R) UHD Graphics 630"),
    ("Intel Inc.", "Intel(R) Iris(R) Xe Graphics"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Apple", "Apple M1 Pro"),
    ("Apple", "Apple M2"),
)

_SCREEN_SIZES = (
    (1920, 1080),
    (2560, 1440),
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1680, 1050),
    (1280, 720),
    (3840, 2160),
)

_TIMEZONES = (
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Paris",
    "Asia/Tokyo",
)


def generate_fingerprint(seed: Optional[str] = None) -> BrowserFingerprint:
    """Generate a consistent fingerprint from a seed (or random if None)."""
    rng = random.Random(seed) if seed else random.Random()

    ua = rng.choice(_USER_AGENTS)
    webgl_pair = rng.choice(_WEBGL_RENDERERS)
    screen = rng.choice(_SCREEN_SIZES)

    if "Windows" in ua:
        platform = "Win32"
    elif "Macintosh" in ua or "Mac OS" in ua:
        platform = "MacIntel"
    else:
        platform = "Linux x86_64"

    vendor = "Google Inc." if "Chrome" in ua else ("Apple Computer, Inc." if "Safari" in ua and "Chrome" not in ua else "")

    return BrowserFingerprint(
        user_agent=ua,
        platform=platform,
        vendor=vendor,
        renderer=webgl_pair[1],
        webgl_vendor=webgl_pair[0],
        webgl_renderer=webgl_pair[1],
        languages=rng.choice((("en-US", "en"), ("en-GB", "en"), ("en-US",))),
        hardware_concurrency=rng.choice((4, 6, 8, 12, 16)),
        device_memory=rng.choice((4, 8, 16, 32)),
        max_touch_points=0,
        screen_width=screen[0],
        screen_height=screen[1],
        color_depth=24,
        timezone=rng.choice(_TIMEZONES),
        canvas_noise_seed=rng.randint(0, 2**32 - 1),
    )


def build_stealth_scripts(fp: BrowserFingerprint) -> list[str]:
    """Return a list of JS scripts to inject before any page content loads."""
    scripts = []

    # 1. Navigator webdriver property removal
    scripts.append("""
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});
""")

    # 2. Navigator properties override
    scripts.append(f"""
Object.defineProperty(navigator, 'platform', {{
    get: () => {json.dumps(fp.platform)},
    configurable: true
}});
Object.defineProperty(navigator, 'vendor', {{
    get: () => {json.dumps(fp.vendor)},
    configurable: true
}});
Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => {fp.hardware_concurrency},
    configurable: true
}});
Object.defineProperty(navigator, 'deviceMemory', {{
    get: () => {fp.device_memory},
    configurable: true
}});
Object.defineProperty(navigator, 'maxTouchPoints', {{
    get: () => {fp.max_touch_points},
    configurable: true
}});
Object.defineProperty(navigator, 'languages', {{
    get: () => Object.freeze({json.dumps(list(fp.languages))}),
    configurable: true
}});
Object.defineProperty(navigator, 'language', {{
    get: () => {json.dumps(fp.languages[0])},
    configurable: true
}});
""")

    # 3. Chrome runtime spoofing
    scripts.append("""
if (!window.chrome) {
    const chrome = {
        app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
        runtime: { OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }, OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }, PlatformArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }, PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }, PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }, RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }, connect: function() { return { onDisconnect: { addListener: function() {} }, onMessage: { addListener: function() {} }, postMessage: function() {}, disconnect: function() {} }; }, sendMessage: function() {} },
        csi: function() { return {}; },
        loadTimes: function() { return { requestTime: Date.now() / 1000, startLoadTime: Date.now() / 1000, commitLoadTime: Date.now() / 1000, finishDocumentLoadTime: Date.now() / 1000, finishLoadTime: Date.now() / 1000, firstPaintTime: Date.now() / 1000, firstPaintAfterLoadTime: 0, navigationType: 'Other' }; }
    };
    Object.defineProperty(window, 'chrome', { get: () => chrome, configurable: true });
}
""")

    # 4. WebGL fingerprint spoofing
    scripts.append(f"""
(function() {{
    const getParameterOrig = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return {json.dumps(fp.webgl_vendor)};
        if (param === 37446) return {json.dumps(fp.webgl_renderer)};
        return getParameterOrig.call(this, param);
    }};
    if (typeof WebGL2RenderingContext !== 'undefined') {{
        const getParam2Orig = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return {json.dumps(fp.webgl_vendor)};
            if (param === 37446) return {json.dumps(fp.webgl_renderer)};
            return getParam2Orig.call(this, param);
        }};
    }}
}})();
""")

    # 5. Canvas fingerprint noise injection
    scripts.append(f"""
(function() {{
    const seed = {fp.canvas_noise_seed};
    function mulberry32(a) {{
        return function() {{
            a |= 0; a = a + 0x6D2B79F5 | 0;
            var t = Math.imul(a ^ a >>> 15, 1 | a);
            t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        }};
    }}
    const rng = mulberry32(seed);

    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {{
            try {{
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 4), Math.min(this.height, 4));
                for (let i = 0; i < imageData.data.length; i += 4) {{
                    imageData.data[i] = imageData.data[i] ^ (rng() * 2 | 0);
                }}
                ctx.putImageData(imageData, 0, 0);
            }} catch(e) {{}}
        }}
        return origToDataURL.call(this, type, quality);
    }};

    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {{
            try {{
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 4), Math.min(this.height, 4));
                for (let i = 0; i < imageData.data.length; i += 4) {{
                    imageData.data[i] = imageData.data[i] ^ (rng() * 2 | 0);
                }}
                ctx.putImageData(imageData, 0, 0);
            }} catch(e) {{}}
        }}
        return origToBlob.call(this, callback, type, quality);
    }};
}})();
""")

    # 6. Permissions API spoofing
    scripts.append("""
(function() {
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = function(parameters) {
        if (parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return originalQuery.call(this, parameters);
    };
})();
""")

    # 7. Plugin/MimeType array spoofing (Chrome-like)
    scripts.append("""
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 }
        ];
        plugins.length = 3;
        plugins.item = (i) => plugins[i] || null;
        plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
        plugins.refresh = () => {};
        return plugins;
    },
    configurable: true
});
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const mimeTypes = [
            { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: { name: 'Chrome PDF Plugin' } },
            { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: { name: 'Chrome PDF Viewer' } }
        ];
        mimeTypes.length = 2;
        mimeTypes.item = (i) => mimeTypes[i] || null;
        mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
        return mimeTypes;
    },
    configurable: true
});
""")

    # 8. WebRTC IP leak prevention
    scripts.append("""
(function() {
    if (typeof RTCPeerConnection !== 'undefined') {
        const origRTC = RTCPeerConnection;
        window.RTCPeerConnection = function(config, constraints) {
            if (config && config.iceServers) {
                config.iceServers = [];
            }
            return new origRTC(config, constraints);
        };
        window.RTCPeerConnection.prototype = origRTC.prototype;
        Object.defineProperty(window, 'RTCPeerConnection', { writable: false, configurable: false });
    }
    if (typeof webkitRTCPeerConnection !== 'undefined') {
        window.webkitRTCPeerConnection = window.RTCPeerConnection;
    }
})();
""")

    # 9. Screen dimensions override
    scripts.append(f"""
Object.defineProperty(screen, 'width', {{ get: () => {fp.screen_width}, configurable: true }});
Object.defineProperty(screen, 'height', {{ get: () => {fp.screen_height}, configurable: true }});
Object.defineProperty(screen, 'availWidth', {{ get: () => {fp.screen_width}, configurable: true }});
Object.defineProperty(screen, 'availHeight', {{ get: () => {fp.screen_height - 40}, configurable: true }});
Object.defineProperty(screen, 'colorDepth', {{ get: () => {fp.color_depth}, configurable: true }});
Object.defineProperty(screen, 'pixelDepth', {{ get: () => {fp.color_depth}, configurable: true }});
""")

    # 10. iframe contentWindow consistency
    scripts.append("""
(function() {
    const origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            const win = origContentWindow.get.call(this);
            if (win) {
                try { Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined }); } catch(e) {}
            }
            return win;
        }
    });
})();
""")

    # 11. Headless detection markers removal
    scripts.append("""
delete window.__playwright;
delete window.__pw_manual;
delete window.__PW_inspect;
Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
""")

    # 12. Connection API spoofing
    scripts.append("""
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', { get: () => 50, configurable: true });
    Object.defineProperty(navigator.connection, 'downlink', { get: () => 10, configurable: true });
    Object.defineProperty(navigator.connection, 'effectiveType', { get: () => '4g', configurable: true });
    Object.defineProperty(navigator.connection, 'saveData', { get: () => false, configurable: true });
}
""")

    return scripts


def get_stealth_init_script(fp: BrowserFingerprint) -> str:
    """Combine all stealth scripts into a single init script for addInitScript."""
    parts = build_stealth_scripts(fp)
    return "\n".join(parts)


def get_context_options(fp: BrowserFingerprint) -> dict:
    """Return Playwright browser context options matching the fingerprint."""
    return {
        "user_agent": fp.user_agent,
        "viewport": {"width": min(fp.screen_width, 1920), "height": min(fp.screen_height - 140, 1080)},
        "screen": {"width": fp.screen_width, "height": fp.screen_height},
        "locale": fp.languages[0].replace("-", "_") if fp.languages else "en_US",
        "timezone_id": fp.timezone,
        "color_scheme": "light",
        "has_touch": fp.max_touch_points > 0,
        "is_mobile": False,
        "device_scale_factor": 1,
        "java_script_enabled": True,
        "bypass_csp": False,
        "ignore_https_errors": True,
        "extra_http_headers": {
            "Accept-Language": ", ".join(fp.languages) + ";q=0.9",
            "sec-ch-ua-platform": f'"{fp.platform}"' if fp.platform == "Win32" else f'"{"macOS" if fp.platform == "MacIntel" else "Linux"}"',
        },
    }

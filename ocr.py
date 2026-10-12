import os
import subprocess
import re
import difflib
import unicodedata
import unicodedata
import cv2
import numpy as np
from PIL import Image, ImageDraw
import json
import sys
import threading
import time
import uuid
import shutil
import signal
import atexit
import socket
from queue import Queue, Full
from concurrent.futures import ThreadPoolExecutor

try:
    import Quartz
except ImportError:
    Quartz = None

try:
    import Vision
    import Foundation
except ImportError:
    Vision = None
    Foundation = None

try:
    from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
except ImportError:
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


current_dir = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(current_dir, "settings.json")
queue_dir = os.path.join(current_dir, "Queue")
snap_dir = os.path.join(current_dir, ".snap")
runs_dir = os.path.join(snap_dir, "runs")
toast_swift_path = os.path.join(snap_dir, "SnapToast.swift")
toast_executable_path = os.path.join(snap_dir, "SnapToast")

audio_swift_path = os.path.join(current_dir, "audio.swift")
screen_swift_path = os.path.join(current_dir, "screen.swift")

audio_bundle_path = os.path.join(snap_dir, "Snap Audio.app")
audio_contents_path = os.path.join(audio_bundle_path, "Contents")
audio_macos_path = os.path.join(audio_contents_path, "MacOS")
audio_info_plist_path = os.path.join(audio_contents_path, "Info.plist")
audio_executable_path = os.path.join(audio_macos_path, "SnapAudio")

audio_socket_path = os.path.join(snap_dir, "snap_audio.sock")
screen_bundle_path = os.path.join(snap_dir, "Snap Screen.app")
screen_contents_path = os.path.join(screen_bundle_path, "Contents")
screen_macos_path = os.path.join(screen_contents_path, "MacOS")
screen_info_plist_path = os.path.join(screen_contents_path, "Info.plist")
screen_executable_path = os.path.join(screen_macos_path, "SnapScreen")
screen_socket_path = os.path.join(snap_dir, "snap_screen.sock")

audio_data_dir = os.path.join(current_dir, "audio")

CARD_QUEUE_MAX = 10
CARD_TIMEOUT = 300

AUDIO_WAIT_TIMEOUT = 50
SWIFT_COMPILE_TIMEOUT = 180

SCREEN_QUERY_TIMEOUT = 0.8
SUBTITLE_QUERY_RETRIES = 1
SUBTITLE_QUERY_RETRY_DELAY = 0.05

SUBTITLE_MAX_INTERVAL = 100.0

INTERVAL_CLOSE_TIMEOUT = 25.0
INTERVAL_POLL = 0.5

HOTKEY_SETTINGS_CHECK_INTERVAL = 2.0

AUDIO_TOGGLE_HOTKEY = "cmd+shift+]"
AUDIO_TOGGLE_KEYCODE = 30
AUDIO_TOGGLE_MODS = {"cmd", "shift"}

card_queue = Queue(maxsize=CARD_QUEUE_MAX)

audio_process = None
audio_socket = None
audio_process_lock = threading.Lock()
audio_command_lock = threading.Lock()

screen_process = None
screen_socket = None
screen_process_lock = threading.Lock()
screen_command_lock = threading.Lock()
screen_capture_state_lock = threading.Lock()
screen_capture_started_event = threading.Event()
screen_capture_stopped_event = threading.Event()
screen_capture_active = False
screen_capture_started_at = 0.0
screen_capture_holds = set()
screen_capture_holds_lock = threading.Lock()

pending_audio_jobs = {}
pending_audio_jobs_lock = threading.Lock()

pending_subtitle_queries = {}
pending_subtitle_queries_lock = threading.Lock()

recent_subtitles = []
recent_subtitles_lock = threading.Lock()

audio_toggle_active = False
monitoring_on = False

loaded_ocr_languages = []
settings_mtime = None

ocr_running = False
ocr_settings_lock = threading.Lock()
ocr_selection_lock = threading.Lock()

ocr_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="snap-ocr")

hotkey_mtime = None
hotkey_last_check = 0.0
hotkey_string = "cmd+shift+a"
hotkey_parts = {"mods": {"cmd", "shift"}, "key": "a"}

hotkey_active = False
event_tap = None
toast_process = None
toast_lock = threading.RLock()
toast_suppressed_for_selection = False
toast_notification_pending = False
toast_pending_payload = None


ALL_LANGUAGE_CODES = {
    "en", "de", "ru", "es", "fr", "it", "pt", "ch_sim", "ch_tra",
    "ja", "ko", "nl", "pl", "cs", "hu", "ro", "sv", "da", "no",
    "fi", "tr", "uk", "el", "he", "ar"
}

VISION_LANGUAGE_CODES = {
    "en": "en-US", "de": "de-DE", "ru": "ru-RU", "es": "es-ES",
    "fr": "fr-FR", "it": "it-IT", "pt": "pt-BR",
    "ch_sim": "zh-Hans", "ch_tra": "zh-Hant", "ja": "ja-JP",
    "ko": "ko-KR", "nl": "nl-NL", "pl": "pl-PL", "cs": "cs-CZ",
    "hu": "hu-HU", "ro": "ro-RO", "sv": "sv-SE", "da": "da-DK",
    "no": "nb-NO", "fi": "fi-FI", "tr": "tr-TR", "uk": "uk-UA",
    "el": "el-GR", "he": "he-IL", "ar": "ar-SA"
}

CJK_VISION_LANGUAGES = {"ja-JP", "zh-Hans", "zh-Hant", "ko-KR"}
CJK_LANGUAGE_CODES = {"ja", "ch_sim", "ch_tra", "ko"}

KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37,
    "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "n": 45, "m": 46, ".": 47, "`": 50,
    "enter": 36, "tab": 48, "space": 49, "delete": 51, "backspace": 51,
    "esc": 53, "escape": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "left": 123, "right": 124, "down": 125, "up": 126
}


def log(message, area="SNAP"):
    print(f"[{time.strftime('%H:%M:%S')}] [{area}] {message}", flush=True)


def cleanup_paths(paths):
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def play_error_sound():
    sound_path = "/System/Library/Sounds/Sosumi.aiff"
    afplay_path = "/usr/bin/afplay"

    if not os.path.exists(sound_path):
        return

    try:
        subprocess.Popen(
            [afplay_path, sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def compile_toast_helper_if_needed():
    os.makedirs(snap_dir, exist_ok=True)

    swiftc = find_swiftc()

    if not swiftc:
        log("swiftc not found. Native notification is unavailable.", "UI")
        return False

    source = r'''import AppKit
import Foundation
import Darwin

let arguments = CommandLine.arguments
func argument(_ name: String, default fallback: String = "") -> String {
    guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return fallback }
    return arguments[index + 1]
}

let kind = argument("--kind", default: "success")
let titleText = argument("--title", default: kind == "error" ? "Card not added" : "Card added")
let messageText = String(argument("--message").prefix(200))
let duration = max(1.0, min(Double(argument("--duration", default: kind == "error" ? "8.0" : "1.5")) ?? 1.5, 12.0))
let isError = kind == "error"

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let mouse = NSEvent.mouseLocation
let selectedScreen = NSScreen.screens.first(where: { $0.frame.contains(mouse) }) ?? NSScreen.main ?? NSScreen.screens.first
guard let screen = selectedScreen else { exit(1) }

let accent = isError
    ? NSColor(calibratedRed: 1.0, green: 0.27, blue: 0.30, alpha: 1.0)
    : NSColor(calibratedRed: 0.20, green: 0.78, blue: 0.40, alpha: 1.0)
let icon = NSImageView()
let symbol = isError ? "exclamationmark.circle.fill" : "checkmark.circle.fill"
let symbolConfig = NSImage.SymbolConfiguration(pointSize: 19, weight: .semibold)
    .applying(NSImage.SymbolConfiguration(paletteColors: [.white, accent]))
if let image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil) {
    icon.image = image.withSymbolConfiguration(symbolConfig) ?? image
}
icon.translatesAutoresizingMaskIntoConstraints = false

let title = NSTextField(labelWithString: titleText)
title.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
title.textColor = NSColor.white.withAlphaComponent(0.97)
title.maximumNumberOfLines = 1
title.cell?.lineBreakMode = .byTruncatingTail
title.translatesAutoresizingMaskIntoConstraints = false

let labels = NSStackView()
labels.orientation = .vertical
labels.alignment = .leading
labels.spacing = 3
labels.translatesAutoresizingMaskIntoConstraints = false
labels.addArrangedSubview(title)
if isError && !messageText.isEmpty {
    let detail = NSTextField(wrappingLabelWithString: messageText)
    detail.font = NSFont.systemFont(ofSize: 12, weight: .regular)
    detail.textColor = NSColor.white.withAlphaComponent(0.78)
    detail.maximumNumberOfLines = 2
    detail.cell?.wraps = true
    detail.cell?.lineBreakMode = .byTruncatingTail
    detail.preferredMaxLayoutWidth = 430
    detail.translatesAutoresizingMaskIntoConstraints = false
    detail.widthAnchor.constraint(lessThanOrEqualToConstant: 430).isActive = true
    labels.addArrangedSubview(detail)
}

title.widthAnchor.constraint(lessThanOrEqualToConstant: 430).isActive = true
let stack = NSStackView(views: [icon, labels])
stack.orientation = .horizontal
stack.alignment = .centerY
stack.spacing = 10
stack.translatesAutoresizingMaskIntoConstraints = false

let horizontalPadding: CGFloat = 20
let height: CGFloat = isError ? 68 : 46
let width = min(max(ceil(stack.fittingSize.width) + horizontalPadding * 2, 170), 520)
let radius = height / 2
let visible = screen.visibleFrame
let x = visible.midX - width / 2
let targetY = visible.minY + visible.height * 0.24
let startY = targetY - 10

let panel = NSPanel(contentRect: NSRect(x: x, y: startY, width: width, height: height), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
panel.level = .screenSaver
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
panel.isFloatingPanel = true
panel.becomesKeyOnlyIfNeeded = true
panel.hidesOnDeactivate = false
panel.ignoresMouseEvents = true
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.appearance = NSAppearance(named: .darkAqua)

let mask = NSImage(size: NSSize(width: height, height: height), flipped: false) { rect in
    NSColor.black.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    return true
}
mask.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
mask.resizingMode = .stretch
let content = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: width, height: height))
content.material = .hudWindow
content.blendingMode = .behindWindow
content.state = .active
content.appearance = NSAppearance(named: .darkAqua)
content.maskImage = mask
content.addSubview(stack)
NSLayoutConstraint.activate([
    icon.widthAnchor.constraint(equalToConstant: 20),
    icon.heightAnchor.constraint(equalToConstant: 20),
    stack.leadingAnchor.constraint(greaterThanOrEqualTo: content.leadingAnchor, constant: 16),
    stack.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -16),
    stack.centerXAnchor.constraint(equalTo: content.centerXAnchor),
    stack.centerYAnchor.constraint(equalTo: content.centerYAnchor)
])
panel.contentView = content
panel.alphaValue = 0
panel.orderFrontRegardless()
NSAnimationContext.runAnimationGroup { context in
    context.duration = 0.22
    context.timingFunction = CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.3, 1.0)
    panel.animator().alphaValue = 1
    panel.animator().setFrame(NSRect(x: x, y: targetY, width: width, height: height), display: true)
}
DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
    NSAnimationContext.runAnimationGroup({ context in
        context.duration = 0.24
        context.timingFunction = CAMediaTimingFunction(name: .easeIn)
        panel.animator().alphaValue = 0
        panel.animator().setFrame(NSRect(x: x, y: targetY + 6, width: width, height: height), display: true)
    }, completionHandler: { app.terminate(nil) })
}
app.run()
'''

    try:
        previous_source = None

        if os.path.isfile(toast_swift_path):
            with open(toast_swift_path, "r", encoding="utf-8") as file:
                previous_source = file.read()

        if previous_source != source:
            with open(toast_swift_path, "w", encoding="utf-8") as file:
                file.write(source)

    except Exception as e:
        log(f"Could not write notification helper: {e}", "UI")
        return False

    needs_build = not os.path.isfile(toast_executable_path)

    if not needs_build:
        try:
            needs_build = (
                os.path.getmtime(toast_swift_path)
                > os.path.getmtime(toast_executable_path)
            )
        except OSError:
            needs_build = True

    if not needs_build:
        return True

    temporary_executable = toast_executable_path + ".new"
    cleanup_paths([temporary_executable])

    log("Compiling native notification helper...", "UI")

    try:
        result = subprocess.run(
            [swiftc, "-O", toast_swift_path, "-o", temporary_executable],
            cwd=current_dir,
            capture_output=True,
            text=True,
            timeout=SWIFT_COMPILE_TIMEOUT
        )

    except subprocess.TimeoutExpired:
        log("Notification helper compilation timed out.", "UI")
        cleanup_paths([temporary_executable])
        return False

    except Exception as e:
        log(f"Could not compile notification helper: {e}", "UI")
        cleanup_paths([temporary_executable])
        return False

    if result.returncode != 0:
        log(
            f"Notification helper compilation failed: {result.stderr.strip()}",
            "UI"
        )
        cleanup_paths([temporary_executable])
        return False

    try:
        os.replace(temporary_executable, toast_executable_path)
        os.chmod(toast_executable_path, 0o755)

    except Exception as e:
        log(f"Could not install notification helper: {e}", "UI")
        cleanup_paths([temporary_executable])
        return False

    log("Native notification helper compiled successfully.", "UI")
    return True


def show_notification(kind="success", title=None, message="", duration=None):
    global toast_process, toast_notification_pending, toast_pending_payload

    if title is None:
        title = "Card added" if kind == "success" else "Card not added"
    if duration is None:
        duration = 1.5 if kind == "success" else 8.0

    payload = {
        "kind": str(kind),
        "title": str(title).replace("\n", " ").strip()[:100],
        "message": str(message).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()[:200],
        "duration": float(duration)
    }

    if not compile_toast_helper_if_needed():
        log("Native notification unavailable.", "UI")
        return

    with toast_lock:
        if toast_suppressed_for_selection:
            toast_notification_pending = True
            toast_pending_payload = payload
            log(f"Notification deferred until selection ends: {payload['title']}", "UI")
            return

        old_process = toast_process
        toast_process = None
        if old_process is not None and old_process.poll() is None:
            try:
                old_process.terminate()
            except Exception:
                pass

        try:
            process = subprocess.Popen(
                [
                    toast_executable_path,
                    "--kind", payload["kind"],
                    "--title", payload["title"],
                    "--message", payload["message"],
                    "--duration", str(payload["duration"])
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            toast_process = process
        except Exception as e:
            log(f"Could not show notification: {e}", "UI")
            return

    log(
        f"Native notification started: {payload['title']!r}, "
        f"kind={payload['kind']}, PID={process.pid}",
        "UI"
    )


def show_card_added_notification():
    show_notification(
        kind="success",
        title="Card added",
        duration=1.5
    )


def humanize_job_error(message):
    text = str(message or "").strip()
    text = re.sub(r"^Card:\s*(ERROR|not added)\s*=\s*", "", text, flags=re.IGNORECASE)
    folded = text.casefold()

    if "cannot import name" in folded or "no module named" in folded:
        return "Snap could not load a Python module or symbol. The installed Snap files or a dependency may be missing or out of sync: " + text[:135]
    if "looks like ocr garbage" in folded or "ocr noise" in folded:
        return "The selected text looks like OCR noise. Select the word again or enable OCR Correction."
    if "front that is not supported by target word or context" in folded:
        return "The generated word was not supported. Select a clearer word or enable OCR Correction."
    if "no lm studio llm is currently loaded" in folded or "no loaded model" in folded:
        return "No language model is loaded in LM Studio. Load a model and try again."
    if "could not read lm studio models" in folded or "lm studio models" in folded and "connection" in folded:
        return "Snap could not reach LM Studio. Check that the local server is running."
    if "ankiconnect connection error" in folded or "connection refused" in folded or "urlopen error" in folded:
        return "Snap could not connect to AnkiConnect. Check that Anki is open and enabled."
    if "still in the wrong language" in folded or "back language check failed" in folded:
        return "The model returned a wrong language translation. Check the profile and try again."
    if "duplicate" in folded or "cannot add" in folded and "note" in folded:
        return "Anki rejected the note, possibly because a duplicate already exists."
    if "timed out" in folded or "timeout" in folded or "exceeded" in folded:
        return "Card generation timed out. Check LM Studio and try again."
    if "invalid json" in folded or "structured output failed" in folded:
        return "The language model returned an invalid response. Try again."
    if not text:
        return "Snap could not create the card. Check snap.log for details."


    text = re.sub(r"\s+", " ", text)
    if len(text) > 185:
        text = text[:182].rstrip() + "…"
    return text


def show_error_notification(message, title="Card not added", duration=8.0):
    show_notification(
        kind="error",
        title=title,
        message=humanize_job_error(message),
        duration=duration
    )


def dismiss_card_added_notification(suppress_for_selection=False):
    global toast_process, toast_suppressed_for_selection

    with toast_lock:
        if suppress_for_selection:
            toast_suppressed_for_selection = True
        process = toast_process
        toast_process = None

    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
        log("Notification dismissal requested.", "UI")

        def reap_process():
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass

        threading.Thread(
            target=reap_process,
            daemon=True,
            name="snap-toast-cleanup"
        ).start()
    except Exception as e:
        log(f"Could not dismiss notification: {e}", "UI")


def load_settings_data():
    if not os.path.exists(settings_path):
        return {}

    try:
        with open(settings_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as e:
        log(f"Failed to read settings.json: {e}", "SETTINGS")
        return {}

    return data if isinstance(data, dict) else {}


LANGUAGE_NAME_TO_OCR_CODE = {
    "english": "en",
    "german": "de",
    "russian": "ru",
    "spanish": "es",
    "french": "fr",
    "italian": "it",
    "portuguese": "pt",
    "chinese (simplified)": "ch_sim",
    "chinese simplified": "ch_sim",
    "simplified chinese": "ch_sim",
    "chinese (traditional)": "ch_tra",
    "chinese traditional": "ch_tra",
    "traditional chinese": "ch_tra",
    "japanese": "ja",
    "korean": "ko",
    "dutch": "nl",
    "polish": "pl",
    "czech": "cs",
    "hungarian": "hu",
    "romanian": "ro",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "finnish": "fi",
    "turkish": "tr",
    "ukrainian": "uk",
    "greek": "el",
    "hebrew": "he",
    "arabic": "ar",
}


def language_name_to_ocr_code(language):
    key = re.sub(r"\s+", " ", str(language or "").strip().casefold())
    return LANGUAGE_NAME_TO_OCR_CODE.get(key)


def load_ocr_languages():
    settings = load_settings_data()
    configured = settings.get("ocr_languages", ["en"])

    if not isinstance(configured, list):
        log("Invalid ocr_languages format. Ignoring explicit OCR language list.", "OCR")
        configured = []

    # Put configured study-language profiles first. This prevents a stale default
    # such as ["en"] from silently disabling recognition of Japanese subtitles.
    result = []
    profiles = settings.get("language_profiles", {})
    if isinstance(profiles, dict):
        for language in profiles:
            code = language_name_to_ocr_code(language)
            if code and code in ALL_LANGUAGE_CODES and code not in result:
                result.append(code)

    # Keep manually configured OCR languages too, within the existing three-language limit.
    for language in configured:
        if not isinstance(language, str):
            continue
        language = language.strip()
        if language not in ALL_LANGUAGE_CODES:
            log(f"Unknown OCR language ignored: {language}", "OCR")
            continue
        if language not in result:
            result.append(language)

    if not result:
        legacy_language = str(settings.get("language", "")).strip()
        legacy_code = language_name_to_ocr_code(legacy_language)
        if legacy_code in ALL_LANGUAGE_CODES:
            result.append(legacy_code)

    # CJK subtitles are easily mistaken for Latin text when English is first.
    # Keep the user's languages but prioritize CJK and move English to the end.
    result.sort(key=lambda code: (code not in CJK_LANGUAGE_CODES, code == "en"))
    return result[:3] or ["en"]


def get_ocr_correction_enabled():
    value = load_settings_data().get("ocr_correction", True)

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _script_counts(text):
    counts = {
        "kana": 0, "han": 0, "hangul": 0, "cyrillic": 0,
        "greek": 0, "hebrew": 0, "arabic": 0, "latin": 0,
        "digits": 0
    }
    for char in str(text or ""):
        code = ord(char)
        if 0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
            counts["kana"] += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            counts["han"] += 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            counts["hangul"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0370 <= code <= 0x03FF:
            counts["greek"] += 1
        elif 0x0590 <= code <= 0x05FF:
            counts["hebrew"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif char.isdigit():
            counts["digits"] += 1
        elif char.isalpha() and code < 0x250:
            counts["latin"] += 1
    return counts


def detect_profile_language(word, context=""):
    """Choose a configured profile from clear writing-system evidence.

    Ambiguous Latin-only input returns None when multiple Latin-script profiles
    exist, allowing card.py to keep its existing language-detection behavior.
    """
    settings = load_settings_data()
    profiles = settings.get("language_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        return None

    by_code = {}
    for name in profiles:
        code = language_name_to_ocr_code(name)
        if code:
            by_code.setdefault(code, name)

    def pick(*codes):
        for code in codes:
            if code in by_code:
                return by_code[code]
        return None

    target = _script_counts(word)
    ctx = _script_counts(context)

    # If OCR returned an alphanumeric-looking token, use subtitle script as
    # evidence rather than treating the Latin noise as a real English word.
    target_is_mixed_noise = target["latin"] >= 2 and target["digits"] >= 1
    if target_is_mixed_noise:
        if ctx["kana"]:
            return pick("ja")
        if ctx["hangul"]:
            return pick("ko")
        if ctx["han"]:
            return pick("ja", "ch_sim", "ch_tra")
        if ctx["cyrillic"]:
            return pick("ru", "uk")
        if ctx["greek"]:
            return pick("el")
        if ctx["hebrew"]:
            return pick("he")
        if ctx["arabic"]:
            return pick("ar")

    if target["kana"]:
        return pick("ja")
    if target["hangul"]:
        return pick("ko")
    if target["han"]:
        if ctx["kana"]:
            return pick("ja", "ch_sim", "ch_tra")
        return pick("ch_sim", "ch_tra", "ja")
    if target["cyrillic"]:
        return pick("uk", "ru") if any(ch in str(word).lower() for ch in "їєґ") else pick("ru", "uk")
    if target["greek"]:
        return pick("el")
    if target["hebrew"]:
        return pick("he")
    if target["arabic"]:
        return pick("ar")

    # Context can identify the script even if the selected crop was poorly read.
    if ctx["kana"]:
        return pick("ja")
    if ctx["hangul"]:
        return pick("ko")
    if ctx["han"]:
        return pick("ja", "ch_sim", "ch_tra")
    if ctx["cyrillic"]:
        return pick("ru", "uk")
    if ctx["greek"]:
        return pick("el")
    if ctx["hebrew"]:
        return pick("he")
    if ctx["arabic"]:
        return pick("ar")

    latin_profiles = [
        name for code, name in by_code.items()
        if code in {"en", "de", "es", "fr", "it", "pt", "nl", "pl", "cs", "hu", "ro", "sv", "da", "no", "fi", "tr"}
    ]
    if target["latin"] and len(latin_profiles) == 1:
        return latin_profiles[0]

    # For Latin-script ambiguity, prefer the configured default only when it is
    # the sole matching profile; otherwise let card.py resolve it when enabled.
    default_language = str(settings.get("language", "")).strip()
    default_profile = next((name for name in profiles if name.casefold() == default_language.casefold()), None)
    if len(latin_profiles) == 1:
        return latin_profiles[0]
    return None if len(latin_profiles) > 1 else default_profile


def get_vision_languages(languages):
    result = []

    for language in languages:
        vision_code = VISION_LANGUAGE_CODES.get(language)
        if vision_code and vision_code not in result:
            result.append(vision_code)

    result.sort(key=lambda code: (code not in CJK_VISION_LANGUAGES, code == "en-US"))
    return result or ["en-US"]


def refresh_ocr_if_needed():
    global loaded_ocr_languages
    global settings_mtime

    with ocr_settings_lock:
        try:
            current_mtime = os.path.getmtime(settings_path)
        except OSError:
            current_mtime = None

        if loaded_ocr_languages and current_mtime == settings_mtime:
            return

        languages = load_ocr_languages()

        if languages == loaded_ocr_languages and current_mtime == settings_mtime:
            return

        if languages != loaded_ocr_languages:
            log(
                f"OCR languages changed: "
                f"{loaded_ocr_languages} -> {languages}",
                "OCR"
            )

        loaded_ocr_languages = languages
        settings_mtime = current_mtime

        log(
            f"Vision languages active: "
            f"{get_vision_languages(languages)}",
            "OCR"
        )


def warm_up_vision():
    os.makedirs(snap_dir, exist_ok=True)

    path = os.path.join(snap_dir, "warmup.png")

    try:
        image = Image.new("RGB", (360, 90), "white")

        ImageDraw.Draw(image).text(
            (12, 30),
            "Snap warm up 123",
            fill="black"
        )

        image.save(path)

        started = time.perf_counter()
        run_vision_ocr(path)

        log(
            f"Vision warm-up took "
            f"{time.perf_counter() - started:.2f}s.",
            "OCR"
        )

    except Exception as e:
        log(f"Vision warm-up failed: {e}", "OCR")

    finally:
        cleanup_paths([path])


def preload_ocr():
    time.sleep(1)

    if ocr_running:
        return

    try:
        log("Preparing Apple Vision OCR...", "OCR")
        refresh_ocr_if_needed()
        warm_up_vision()
        log("OCR ready.", "OCR")
    except Exception as e:
        log(f"OCR initialization failed: {e}", "OCR")


def start_ocr_preloader():
    threading.Thread(target=preload_ocr, daemon=True).start()


def parent_watchdog():
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            try:
                shutdown()
            finally:
                os._exit(0)

threading.Thread(target=parent_watchdog, daemon=True).start()


def find_swiftc():
    candidates = [
        "/usr/bin/swiftc",
        "/usr/local/bin/swiftc"
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    try:
        result = subprocess.run(
            ["which", "swiftc"],
            capture_output=True,
            text=True,
            timeout=5
        )

        path = result.stdout.strip()

        if path and os.path.isfile(path):
            return path

    except Exception as e:
        log(f"Could not locate swiftc: {e}", "SWIFT")

    return None



def create_audio_bundle():
    os.makedirs(audio_macos_path, exist_ok=True)
    os.makedirs(audio_data_dir, exist_ok=True)

    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Snap Audio</string>
    <key>CFBundleExecutable</key>
    <string>SnapAudio</string>
    <key>CFBundleIdentifier</key>
    <string>com.snap.audio</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Snap Audio</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>14.2</string>
    <key>NSAudioCaptureUsageDescription</key>
    <string>Snap captures system audio to attach audio to Anki cards.</string>
</dict>
</plist>
"""

    try:
        old = None

        if os.path.isfile(audio_info_plist_path):
            try:
                with open(audio_info_plist_path, "r", encoding="utf-8") as file:
                    old = file.read()
            except Exception:
                old = None

        if old != plist:
            with open(audio_info_plist_path, "w", encoding="utf-8") as file:
                file.write(plist)
            log("Info.plist updated.", "AUDIO")
        else:
            log("Info.plist unchanged.", "AUDIO")

        return True

    except Exception as e:
        log(
            f"Could not create Info.plist: {e}",
            "AUDIO"
        )
        return False


def sign_audio_bundle():
    codesign = "/usr/bin/codesign"

    if not os.path.exists(codesign):
        return False

    try:
        result = subprocess.run(
            [
                codesign,
                "--force",
                "--deep",
                "--sign",
                "-",
                "--identifier",
                "com.snap.audio",
                audio_bundle_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
    except Exception as e:
        log(f"codesign failed to start: {e}", "AUDIO")
        return False

    if result.returncode != 0:
        log(
            f"codesign failed with code "
            f"{result.returncode}.",
            "AUDIO"
        )

        if result.stderr.strip():
            print(result.stderr, flush=True)

        return False

    return True


def verify_audio_bundle():
    codesign = "/usr/bin/codesign"

    if not os.path.exists(codesign):
        return False

    try:
        result = subprocess.run(
            [
                codesign,
                "--verify",
                "--deep",
                "--strict",
                audio_bundle_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )

        return result.returncode == 0

    except Exception:
        return False


def compile_audio_swift_if_needed():
    if not os.path.isfile(audio_swift_path):
        log(f"audio.swift not found: {audio_swift_path}", "AUDIO")
        return False

    swiftc = find_swiftc()

    if not swiftc:
        log("swiftc not found.", "AUDIO")
        return False

    if not create_audio_bundle():
        return False

    needs_build = not os.path.isfile(audio_executable_path)

    if not needs_build:
        try:
            source_mtime = os.path.getmtime(audio_swift_path)
            binary_mtime = os.path.getmtime(audio_executable_path)
            plist_mtime = os.path.getmtime(audio_info_plist_path)

            if source_mtime > binary_mtime or plist_mtime > binary_mtime:
                needs_build = True

        except OSError:
            needs_build = True

    if not needs_build and not verify_audio_bundle():
        needs_build = True

    if not needs_build:
        log(
            f"Audio executable ready: "
            f"{audio_executable_path}",
            "AUDIO"
        )

        return True

    log("Compiling audio.swift...", "AUDIO")
    log(f"swiftc = {swiftc}", "AUDIO")

    temp_executable = audio_executable_path + ".new"

    try:
        cleanup_paths([temp_executable])

        result = subprocess.run(
            [
                swiftc,
                "-O",
                audio_swift_path,
                "-o",
                temp_executable,
                "-Xlinker",
                "-sectcreate",
                "-Xlinker",
                "__TEXT",
                "-Xlinker",
                "__info_plist",
                "-Xlinker",
                audio_info_plist_path
            ],
            cwd=current_dir,
            capture_output=True,
            text=True,
            timeout=SWIFT_COMPILE_TIMEOUT
        )

    except subprocess.TimeoutExpired:
        log("Swift compilation timed out.", "AUDIO")
        return False

    except Exception as e:
        log(f"Failed to start swiftc: {e}", "AUDIO")
        return False

    if result.returncode != 0:
        log(
            f"swiftc failed with code "
            f"{result.returncode}.",
            "AUDIO"
        )

        if result.stderr.strip():
            print(result.stderr, flush=True)

        cleanup_paths([temp_executable])

        return False

    try:
        os.replace(
            temp_executable,
            audio_executable_path
        )

        os.chmod(
            audio_executable_path,
            0o755
        )

    except Exception as e:
        log(
            f"Failed to install audio executable: {e}",
            "AUDIO"
        )

        return False

    if sign_audio_bundle():
        log("Snap Audio.app signed.", "AUDIO")
    else:
        log("WARNING: Snap Audio.app could not be signed.", "AUDIO")

    if verify_audio_bundle():
        log("Audio bundle signature verified.", "AUDIO")
    else:
        log(
            "WARNING: Audio bundle signature verification failed.",
            "AUDIO"
        )

    log(
        f"Audio executable built: "
        f"{audio_executable_path}",
        "AUDIO"
    )

    return True


def open_audio_permission_settings():
    try:
        subprocess.Popen(
            [
                "open",
                "x-apple.systempreferences:"
                "com.apple.preference.security?"
                "Privacy_AudioCapture"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        log(
            "Opened System Settings for audio capture permission.",
            "AUDIO"
        )

    except Exception as e:
        log(
            f"Could not open audio permission settings: {e}",
            "AUDIO"
        )


def connect_audio_socket(timeout=10.0):
    deadline = time.time() + timeout

    while time.time() < deadline:
        with audio_process_lock:
            process = audio_process

        if process is not None and process.poll() is not None:
            log(
                "Snap Audio process exited while waiting for IPC socket.",
                "AUDIO"
            )
            return None

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)

        try:
            sock.connect(audio_socket_path)
            sock.settimeout(None)
            return sock
        except Exception:
            try:
                sock.close()
            except Exception:
                pass

        time.sleep(0.05)

    return None


def audio_reader_loop(process, sock):
    global audio_process
    global audio_socket

    log("Audio socket reader started.", "AUDIO")

    buffer = b""

    try:
        while True:
            data = sock.recv(8192)

            if not data:
                break

            buffer += data

            while b"\n" in buffer:
                line_bytes, buffer = buffer.split(b"\n", 1)

                try:
                    line = line_bytes.decode(
                        "utf-8",
                        errors="replace"
                    ).rstrip("\r")

                except Exception:
                    continue

                if line:
                    handle_audio_output(line)

    except Exception as e:
        if process.poll() is None:
            log(
                f"Audio socket reader error: {e}",
                "AUDIO"
            )

    finally:
        try:
            sock.close()
        except Exception:
            pass

        with audio_process_lock:
            if audio_socket is sock:
                audio_socket = None

            if audio_process is process:
                audio_process = None

        log(
            f"SnapAudio process ended. "
            f"returncode={process.poll()}",
            "AUDIO"
        )

def find_audio_pid():
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5
        )
    except Exception:
        return None

    candidates = []

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split(None, 1)

        if len(parts) != 2:
            continue

        try:
            pid = int(parts[0])
        except ValueError:
            continue

        command = parts[1].strip()

        if (
            command == audio_executable_path
            or command.startswith(audio_executable_path + " ")
        ):
            candidates.append(pid)

    if not candidates:
        return None

    return max(candidates)

def stop_stale_audio_processes():
    pid = find_audio_pid()

    while pid is not None:
        log(
            f"Stopping stale SnapAudio PID={pid}.",
            "AUDIO"
        )

        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

        deadline = time.time() + 3

        while time.time() < deadline:
            if find_audio_pid() != pid:
                break
            time.sleep(0.05)

        if find_audio_pid() == pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

        pid = find_audio_pid()

class AttachedProcess:
    def __init__(self, pid, name="SnapAudio"):
        self.pid = pid
        self.name = name

    def poll(self):
        try:
            os.kill(self.pid, 0)
            return None
        except ProcessLookupError:
            return 0
        except PermissionError:
            return None
        except Exception:
            return 0

    def wait(self, timeout=None):
        started = time.time()

        while self.poll() is None:
            if timeout is not None and time.time() - started >= timeout:
                raise subprocess.TimeoutExpired(
                    cmd=self.name,
                    timeout=timeout
                )

            time.sleep(0.05)

        return 0

def start_audio_process():
    global audio_process
    global audio_socket

    with audio_process_lock:
        if (
            audio_process is not None
            and audio_process.poll() is None
            and audio_socket is not None
        ):
            return True

    if not compile_audio_swift_if_needed():
        log(
            "Audio subsystem unavailable.",
            "AUDIO"
        )
        return False

    os.makedirs(audio_data_dir, exist_ok=True)
    os.makedirs(snap_dir, exist_ok=True)

    try:
        if audio_socket is not None:
            audio_socket.close()
    except Exception:
        pass

    with audio_process_lock:
        audio_socket = None
        audio_process = None

    stop_stale_audio_processes()

    if os.path.exists(audio_socket_path):
        try:
            os.remove(audio_socket_path)
        except OSError:
            pass

    log(
        "Launching Snap Audio.app through LaunchServices...",
        "AUDIO"
    )

    log(
        f"App = {audio_bundle_path}",
        "AUDIO"
    )

    log(
        f"Socket = {audio_socket_path}",
        "AUDIO"
    )

    log(
        f"Audio directory = {audio_data_dir}",
        "AUDIO"
    )

    try:
        launcher = subprocess.Popen(
            [
                "/usr/bin/open",
                "-n",
                audio_bundle_path,
                "--args",
                "--socket",
                audio_socket_path,
                "--audio-dir",
                audio_data_dir,
                "--parent-pid",
                str(os.getpid())
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            _, stderr = launcher.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()
            _, stderr = launcher.communicate()

            log(
                "LaunchServices open timed out.",
                "AUDIO"
            )
            return False

        if launcher.returncode != 0:
            log(
                f"open failed with code {launcher.returncode}.",
                "AUDIO"
            )

            if stderr.strip():
                log(
                    stderr.strip(),
                    "AUDIO"
                )

            return False

    except Exception as e:
        log(
            f"Failed to launch Snap Audio.app: {e}",
            "AUDIO"
        )
        return False

    deadline = time.time() + 10
    sock = None
    pid = None

    while time.time() < deadline:
        pid = find_audio_pid()

        if os.path.exists(audio_socket_path):
            test = socket.socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM
            )

            test.settimeout(0.5)

            try:
                test.connect(
                    audio_socket_path
                )

                test.settimeout(None)
                sock = test
                break

            except Exception:
                try:
                    test.close()
                except Exception:
                    pass

        time.sleep(0.05)

    if sock is None:
        log(
            "Could not connect to Snap Audio.app socket.",
            "AUDIO"
        )

        stop_stale_audio_processes()
        return False

    for _ in range(40):
        if pid is None:
            pid = find_audio_pid()

        if pid is not None:
            break

        time.sleep(0.05)

    if pid is None:
        log(
            "Could not determine SnapAudio PID.",
            "AUDIO"
        )

        try:
            sock.close()
        except Exception:
            pass

        stop_stale_audio_processes()
        return False

    process = AttachedProcess(pid)

    with audio_process_lock:
        audio_process = process
        audio_socket = sock

    log(
        f"SnapAudio process started. PID={pid}",
        "AUDIO"
    )

    threading.Thread(
        target=audio_reader_loop,
        args=(process, sock),
        daemon=True,
        name="snap-audio-reader"
    ).start()

    log(
        "Audio socket reader started.",
        "AUDIO"
    )

    time.sleep(0.2)

    if process.poll() is not None:
        log(
            "SnapAudio exited immediately after launch.",
            "AUDIO"
        )
        return False

    log(
        "Connected to Snap Audio.app through its app bundle.",
        "AUDIO"
    )

    return True


def send_audio_command(command):
    with audio_process_lock:
        process = audio_process
        sock = audio_socket

    if process is None or process.poll() is not None:
        log("SnapAudio is not running.", "AUDIO")
        return False

    if sock is None:
        log("SnapAudio socket is unavailable.", "AUDIO")
        return False

    try:
        payload = (command + "\n").encode("utf-8")

        with audio_command_lock:
            sock.sendall(payload)

        log(
            f">>> {command}",
            "AUDIO"
        )

        return True

    except Exception as e:
        log(
            f"Failed to send audio command: {e}",
            "AUDIO"
        )
        return False


def toggle_audio_capture():
    log(
        "Audio toggle hotkey pressed.",
        "AUDIO"
    )

    sent = send_audio_command("TOGGLE")

    if sent:
        log(
            "TOGGLE sent to SnapAudio.",
            "AUDIO"
        )
    else:
        log(
            "Could not toggle audio because SnapAudio is unavailable.",
            "AUDIO"
        )


def send_audio_select(
    request_id,
    word,
    audio_reference_time,
    audio_interval=None
):
    request_id = str(request_id).strip()
    word = str(word).strip()

    if not request_id or not word:
        return False

    safe_word = (
        word
        .replace("\t", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )

    command = (
        "SELECT\t"
        + request_id
        + "\t"
        + safe_word
        + "\t"
        + f"{float(audio_reference_time):.6f}"
    )

    if audio_interval:
        start_wall, end_wall = audio_interval

        command += (
            "\t"
            + f"{float(start_wall):.6f}"
            + "\t"
            + f"{float(end_wall):.6f}"
        )

    return send_audio_command(command)


def stop_audio_process():
    global audio_process
    global audio_socket

    with audio_process_lock:
        process = audio_process
        sock = audio_socket

    if process is None:
        return

    log(
        f"Stopping SnapAudio PID={process.pid}...",
        "AUDIO"
    )

    try:
        if sock is not None and process.poll() is None:
            with audio_command_lock:
                sock.sendall(b"STOP\n")
    except Exception as e:
        log(
            f"Could not send STOP: {e}",
            "AUDIO"
        )

    try:
        if sock is not None:
            sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass

    try:
        if sock is not None:
            sock.close()
    except Exception:
        pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log(
            "SnapAudio did not stop after STOP. Sending SIGTERM.",
            "AUDIO"
        )

        try:
            os.kill(
                process.pid,
                signal.SIGTERM
            )
        except Exception:
            pass

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log(
                "SnapAudio still alive. Sending SIGKILL.",
                "AUDIO"
            )

            try:
                os.kill(
                    process.pid,
                    signal.SIGKILL
                )
            except Exception:
                pass

    with audio_process_lock:
        if audio_process is process:
            audio_process = None

        if audio_socket is sock:
            audio_socket = None

    if os.path.exists(audio_socket_path):
        try:
            os.remove(audio_socket_path)
        except OSError:
            pass


def handle_audio_clip(request_id, audio_path):
    request_id = str(request_id).strip()
    audio_path = str(audio_path).strip()

    log(
        f"AUDIO_CLIP request={request_id}",
        "AUDIO"
    )
    log(
        f"Audio path = {audio_path}",
        "AUDIO"
    )

    if not request_id or not audio_path:
        return

    audio_path = os.path.abspath(
        os.path.expanduser(audio_path)
    )

    if not os.path.isfile(audio_path):
        log(
            f"Audio file does not exist: {audio_path}",
            "AUDIO"
        )
        return

    with pending_audio_jobs_lock:
        job = pending_audio_jobs.get(request_id)

    if job is None:
        log(
            f"No pending job for request ID {request_id}.",
            "AUDIO"
        )
        return

    job["audio"] = audio_path
    job["audio_error"] = ""

    event = job.get("audio_event")

    if event is not None:
        event.set()

    log(
        f"Audio matched to Job {job['id']}.",
        "AUDIO"
    )


def handle_audio_error(request_id, reason):
    request_id = str(request_id).strip()
    reason = str(reason).strip()

    log(
        f"AUDIO_ERROR request={request_id} reason={reason}",
        "AUDIO"
    )

    if request_id == "system":
        if reason == "no_io_callbacks":
            log("No IO callbacks: output device may be idle. Play audio and retry.", "AUDIO")

        elif reason == "zero_audio":
            log(
                "No audio signal yet. If something is playing, "
                "check System Settings > Privacy & Security > "
                "Screen & System Audio Recording.",
                "AUDIO"
            )

        return

    with pending_audio_jobs_lock:
        job = pending_audio_jobs.get(request_id)

    if job is None:
        return

    job["audio"] = ""
    job["audio_error"] = reason

    event = job.get("audio_event")

    if event is not None:
        event.set()


def set_monitoring(on):
    global monitoring_on
    if on == monitoring_on:
        return
    monitoring_on = on
    def work():
        if on:
            start_screen_capture()
        elif not has_screen_capture_holds():
            stop_screen_capture(force=True)
    threading.Thread(target=work, daemon=True).start()


def handle_audio_output(line):
    line = str(line).strip()

    if not line:
        return

    if line.startswith("AUDIO_CLIP\t"):
        parts = line.split("\t", 2)

        if len(parts) == 3:
            handle_audio_clip(
                parts[1],
                parts[2]
            )

        return

    if line.startswith("AUDIO_ERROR\t"):
        parts = line.split("\t", 2)

        if len(parts) == 3:
            handle_audio_error(
                parts[1],
                parts[2]
            )

        return

    if line.startswith("AUDIO_STATUS\t"):
        set_monitoring(line.split("\t", 1)[1].strip() == "on")
        log(line, "AUDIO")
        return

    if line.startswith("LOG\t"):
        log(
            line.split("\t", 1)[1],
            "AUDIO"
        )
        return

    log(
        line,
        "AUDIO"
    )


def audio_timeout_watchdog():
    while True:
        time.sleep(5)

        now = time.time()
        expired = []

        with pending_audio_jobs_lock:
            for request_id, job in list(pending_audio_jobs.items()):
                created_at = job.get("created_at", now)

                if now - created_at > CARD_TIMEOUT:
                    expired.append(
                        (request_id, job)
                    )
                    del pending_audio_jobs[request_id]

        for request_id, job in expired:
            log(
                f"Removing stale audio job "
                f"{job['id']} request={request_id}",
                "AUDIO"
            )


def start_audio_watchdog():
    threading.Thread(
        target=audio_timeout_watchdog,
        daemon=True,
        name="snap-audio-watchdog"
    ).start()


def create_screen_bundle():
    os.makedirs(screen_macos_path, exist_ok=True)
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Snap Screen</string>
    <key>CFBundleExecutable</key>
    <string>SnapScreen</string>
    <key>CFBundleIdentifier</key>
    <string>com.snap.screen</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Snap Screen</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.2</string>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Snap temporarily captures the screen to detect subtitle intervals.</string>
</dict>
</plist>
"""
    try:
        old=None
        if os.path.isfile(screen_info_plist_path):
            try:
                with open(screen_info_plist_path,"r",encoding="utf-8") as f:
                    old=f.read()
            except Exception:
                old=None
        if old != plist:
            with open(screen_info_plist_path,"w",encoding="utf-8") as f:
                f.write(plist)
            log("Screen Info.plist updated.","SCREEN")
        return True
    except Exception as e:
        log(f"Could not create screen Info.plist: {e}","SCREEN")
        return False


def sign_screen_bundle():
    codesign="/usr/bin/codesign"
    if not os.path.exists(codesign):
        return False
    try:
        r=subprocess.run([codesign,"--force","--deep","--sign","-","--identifier","com.snap.screen",screen_bundle_path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    except Exception as e:
        log(f"screen codesign failed to start: {e}","SCREEN")
        return False
    if r.returncode != 0:
        log(f"screen codesign failed with code {r.returncode}.","SCREEN")
        if r.stderr.strip(): print(r.stderr,flush=True)
        return False
    return True


def verify_screen_bundle():
    codesign="/usr/bin/codesign"
    if not os.path.exists(codesign):
        return False
    try:
        r=subprocess.run([codesign,"--verify","--deep","--strict",screen_bundle_path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def compile_screen_swift_if_needed():
    if not os.path.isfile(screen_swift_path):
        log(f"screen.swift not found: {screen_swift_path}","SCREEN")
        return False
    swiftc=find_swiftc()
    if not swiftc:
        log("swiftc not found.","SCREEN")
        return False
    if not create_screen_bundle():
        return False
    needs_build=not os.path.isfile(screen_executable_path)
    if not needs_build:
        try:
            source_mtime=os.path.getmtime(screen_swift_path)
            binary_mtime=os.path.getmtime(screen_executable_path)
            plist_mtime=os.path.getmtime(screen_info_plist_path)
            if source_mtime>binary_mtime or plist_mtime>binary_mtime: needs_build=True
        except OSError:
            needs_build=True
    if not needs_build and not verify_screen_bundle(): needs_build=True
    if not needs_build:
        log(f"Screen app ready: {screen_bundle_path}","SCREEN")
        return True
    log("Compiling screen.swift...","SCREEN")
    log(f"swiftc = {swiftc}","SCREEN")
    temp=screen_executable_path+".new"
    try:
        cleanup_paths([temp])
        r=subprocess.run([swiftc,"-O",screen_swift_path,"-o",temp,"-Xlinker","-sectcreate","-Xlinker","__TEXT","-Xlinker","__info_plist","-Xlinker",screen_info_plist_path],cwd=current_dir,capture_output=True,text=True,timeout=SWIFT_COMPILE_TIMEOUT)
    except subprocess.TimeoutExpired:
        log("screen.swift compilation timed out.","SCREEN")
        return False
    except Exception as e:
        log(f"Failed to start swiftc for screen.swift: {e}","SCREEN")
        return False
    if r.returncode != 0:
        log(f"screen.swift compilation failed. Exit code={r.returncode}","SCREEN")
        if r.stderr.strip(): print(r.stderr,flush=True)
        cleanup_paths([temp])
        return False
    try:
        os.replace(temp,screen_executable_path)
        os.chmod(screen_executable_path,0o755)
    except Exception as e:
        log(f"Could not install screen executable: {e}","SCREEN")
        return False
    if sign_screen_bundle(): log("Snap Screen.app signed.","SCREEN")
    else: log("WARNING: Snap Screen.app could not be signed.","SCREEN")
    if verify_screen_bundle(): log("Screen bundle signature verified.","SCREEN")
    else: log("WARNING: Screen bundle signature verification failed.","SCREEN")
    log(f"Screen executable built: {screen_executable_path}","SCREEN")
    return True


def find_screen_pid():
    try:
        r=subprocess.run(["ps","-axo","pid=,command="],capture_output=True,text=True,timeout=5)
    except Exception:
        return None
    candidates=[]
    for line in r.stdout.splitlines():
        line=line.strip()
        if not line: continue
        parts=line.split(None,1)
        if len(parts)!=2: continue
        try: pid=int(parts[0])
        except ValueError: continue
        cmd=parts[1].strip()
        if cmd==screen_executable_path or cmd.startswith(screen_executable_path+" "): candidates.append(pid)
    return max(candidates) if candidates else None


def stop_stale_screen_processes():
    pid=find_screen_pid()
    while pid is not None:
        log(f"Stopping stale SnapScreen PID={pid}.","SCREEN")
        try: os.kill(pid,signal.SIGTERM)
        except Exception: pass
        deadline=time.time()+3
        while time.time()<deadline:
            if find_screen_pid()!=pid: break
            time.sleep(0.05)
        if find_screen_pid()==pid:
            try: os.kill(pid,signal.SIGKILL)
            except Exception: pass
        pid=find_screen_pid()


def screen_reader_loop(process,sock):
    global screen_process, screen_socket
    log("Screen socket reader started.","SCREEN")
    buffer=b""
    try:
        while True:
            data=sock.recv(8192)
            if not data: break
            buffer+=data
            while b"\n" in buffer:
                line_bytes,buffer=buffer.split(b"\n",1)
                try: line=line_bytes.decode("utf-8",errors="replace").rstrip("\r")
                except Exception: continue
                if line: handle_screen_output(line)
    except Exception as e:
        if process.poll() is None: log(f"Screen socket reader error: {e}","SCREEN")
    finally:
        try: sock.close()
        except Exception: pass
        with screen_process_lock:
            if screen_socket is sock: screen_socket=None
            if screen_process is process: screen_process=None
        log(f"SnapScreen process ended. returncode={process.poll()}","SCREEN")


def start_screen_process():
    global screen_process, screen_socket
    refresh_ocr_if_needed()
    preferred_languages = ",".join(get_vision_languages(loaded_ocr_languages))
    with screen_process_lock:
        if screen_process is not None and screen_process.poll() is None and screen_socket is not None: return True
    if not compile_screen_swift_if_needed():
        log("Screen watcher unavailable.","SCREEN")
        return False
    os.makedirs(snap_dir,exist_ok=True)
    try:
        if screen_socket is not None: screen_socket.close()
    except Exception: pass
    with screen_process_lock:
        screen_socket=None; screen_process=None
    stop_stale_screen_processes()
    if os.path.exists(screen_socket_path):
        try: os.remove(screen_socket_path)
        except OSError: pass
    log("Launching Snap Screen.app through LaunchServices...","SCREEN")
    log(f"App = {screen_bundle_path}","SCREEN")
    log(f"Socket = {screen_socket_path}","SCREEN")
    try:
        launcher=subprocess.Popen(["/usr/bin/open","-n",screen_bundle_path,"--args","--socket",screen_socket_path,"--parent-pid",str(os.getpid()),"--languages",preferred_languages],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        try: _,stderr=launcher.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill(); _,stderr=launcher.communicate(); log("LaunchServices open timed out.","SCREEN"); return False
        if launcher.returncode != 0:
            log(f"open failed with code {launcher.returncode}.","SCREEN")
            if stderr.strip(): log(stderr.strip(),"SCREEN")
            return False
    except Exception as e:
        log(f"Failed to launch Snap Screen.app: {e}","SCREEN")
        return False
    deadline=time.time()+10
    sock=None; pid=None
    while time.time()<deadline:
        pid=find_screen_pid()
        if os.path.exists(screen_socket_path):
            test=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); test.settimeout(0.5)
            try:
                test.connect(screen_socket_path); test.settimeout(None); sock=test; break
            except Exception:
                try: test.close()
                except Exception: pass
        time.sleep(0.05)
    if sock is None:
        log("Could not connect to Snap Screen.app socket.","SCREEN")
        stop_stale_screen_processes()
        return False
    for _ in range(40):
        if pid is None: pid=find_screen_pid()
        if pid is not None: break
        time.sleep(0.05)
    if pid is None:
        log("Could not determine SnapScreen PID.","SCREEN")
        try: sock.close()
        except Exception: pass
        stop_stale_screen_processes()
        return False
    process=AttachedProcess(pid,"SnapScreen")
    with screen_process_lock:
        screen_process=process; screen_socket=sock
    threading.Thread(target=screen_reader_loop,args=(process,sock),daemon=True,name="snap-screen-reader").start()
    time.sleep(0.2)
    if process.poll() is not None:
        log("SnapScreen exited immediately after launch.","SCREEN")
        return False
    log(f"SnapScreen process started. PID={pid}","SCREEN")
    log("Connected to Snap Screen.app through its app bundle.","SCREEN")
    return True


def send_screen_command(command,quiet=False):
    with screen_process_lock:
        process=screen_process; sock=screen_socket
    if process is None or process.poll() is not None:
        log("SnapScreen is not running.","SCREEN"); return False
    if sock is None:
        log("SnapScreen socket is unavailable.","SCREEN"); return False
    try:
        with screen_command_lock: sock.sendall((command+"\n").encode("utf-8"))
        if not quiet: log(f">>> {command}","SCREEN")
        return True
    except Exception as e:
        log(f"Failed to send screen command: {e}","SCREEN"); return False


def handle_screen_output(line):
    global screen_capture_active, screen_capture_started_at
    line=str(line).strip()
    if not line: return
    if line.startswith("SUBTITLE_RESULT\t"):
        parts=line.split("\t",5)
        if len(parts)==5: parts.append("")
        if len(parts)!=6: return
        request_id=parts[1].strip()
        try: text_time=float(parts[2]); start_time=float(parts[3]); end_time=float(parts[4])
        except ValueError:
            log(f"Invalid SUBTITLE_RESULT: {line}","SCREEN"); return
        text_value=parts[5].strip()
        with pending_subtitle_queries_lock: request=pending_subtitle_queries.get(request_id)
        if request is None: return
        request["result"]={"text":text_value,"textTime":text_time,"startWallTime":start_time,"endWallTime":end_time}
        request["event"].set(); return
    if line=="SCREEN_CAPTURE_STARTED":
        with screen_capture_state_lock:
            screen_capture_active=True; screen_capture_started_at=time.time()
        screen_capture_started_event.set(); screen_capture_stopped_event.clear()
        log("ScreenCaptureKit capture is ON.","SCREEN"); return
    if line=="SCREEN_CAPTURE_STOPPED":
        with screen_capture_state_lock: screen_capture_active=False
        screen_capture_stopped_event.set(); screen_capture_started_event.clear()
        log("ScreenCaptureKit capture is OFF.","SCREEN"); return
    if line.startswith("SCREEN_PERMISSION_"):
        log(line,"SCREEN"); return
    log(line,"SCREEN")


def query_subtitle_at(reference_time,keep_empty=False,strict=False,quiet=False):
    if not start_screen_process(): return None
    try: reference_time=float(reference_time)
    except Exception: return None
    if reference_time<=0: return None
    for attempt in range(SUBTITLE_QUERY_RETRIES+1):
        request_id=uuid.uuid4().hex; event=threading.Event(); request={"event":event,"result":None}
        with pending_subtitle_queries_lock: pending_subtitle_queries[request_id]=request
        command="QUERY\t"+request_id+"\t"+f"{reference_time:.6f}"
        if strict: command+="\tstrict"
        sent=send_screen_command(command,quiet=quiet)
        if not sent:
            with pending_subtitle_queries_lock: pending_subtitle_queries.pop(request_id,None)
            return None
        ready=event.wait(timeout=SCREEN_QUERY_TIMEOUT)
        with pending_subtitle_queries_lock: pending_subtitle_queries.pop(request_id,None)
        if ready:
            result=request.get("result")
            if result is not None and (result.get("text") or keep_empty):
                if result.get("text") and not quiet:
                    log(f"Subtitle at {reference_time:.6f}: {result['text']} [{result['startWallTime']:.3f} -> {result['endWallTime'] or 'open'}]","SCREEN")
                elif not result.get("text") and not quiet:
                    log(f"No subtitle at reference {reference_time:.6f}.","SCREEN")
                return result
        if attempt< SUBTITLE_QUERY_RETRIES: time.sleep(SUBTITLE_QUERY_RETRY_DELAY)
    if not quiet: log(f"No subtitle at reference {reference_time:.6f}.","SCREEN")
    if keep_empty: return {"text":"","textTime":0.0,"startWallTime":0.0,"endWallTime":0.0}
    return None


def screen_result_belongs_to_current_capture(result):
    if not result or not result.get("text"): return False
    with screen_capture_state_lock: started_at=screen_capture_started_at
    if started_at<=0: return True
    try: start=float(result.get("startWallTime",0.0)); end=float(result.get("endWallTime",0.0))
    except Exception: return False
    if end>0 and end<started_at: return False
    if start>0 and start<started_at and end>0 and end<=started_at: return False
    return True


def start_screen_capture():
    global screen_capture_active
    with screen_capture_state_lock:
        if screen_capture_active: return True
    if not start_screen_process(): return False
    screen_capture_started_event.clear(); screen_capture_stopped_event.clear()
    if not send_screen_command("START"):
        log("Could not start ScreenCaptureKit capture.","SCREEN"); return False
    if not screen_capture_started_event.wait(timeout=8):
        log("Timed out waiting for SCREEN_CAPTURE_STARTED.","SCREEN")
        with screen_capture_state_lock: active=screen_capture_active
        if not active: return False
    time.sleep(0.12)
    with screen_capture_state_lock: return screen_capture_active


def stop_screen_capture(force=False):
    global screen_capture_active, screen_capture_started_at
    if monitoring_on and not force:
        return True
    with screen_capture_state_lock: active=screen_capture_active
    if not active: return True
    with screen_process_lock: process=screen_process
    if process is None or process.poll() is not None:
        with screen_capture_state_lock:
            screen_capture_active=False; screen_capture_started_at=0.0
        return False
    log("Stopping ScreenCaptureKit capture...","SCREEN")
    screen_capture_stopped_event.clear()
    if not send_screen_command("STOP"):
        log("Could not send STOP to screen.swift.","SCREEN"); return False
    if not screen_capture_stopped_event.wait(timeout=8):
        log("Timed out waiting for SCREEN_CAPTURE_STOPPED. Terminating screen.swift to guarantee capture is off.","SCREEN")
        try: os.kill(process.pid,signal.SIGTERM)
        except Exception: pass
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try: os.kill(process.pid,signal.SIGKILL)
            except Exception: pass
    with screen_capture_state_lock:
        screen_capture_active=False; screen_capture_started_at=0.0
    screen_capture_started_event.clear(); screen_capture_stopped_event.clear()
    return True


def add_screen_capture_hold(request_id):
    with screen_capture_holds_lock: screen_capture_holds.add(request_id)
    log(f"Screen capture hold added for Job request={request_id}.","SCREEN")


def release_screen_capture_hold(request_id):
    with screen_capture_holds_lock:
        screen_capture_holds.discard(request_id); has_holds=bool(screen_capture_holds)
    log(f"Screen capture hold released for Job request={request_id}. remaining={len(screen_capture_holds)}","SCREEN")
    if not has_holds: stop_screen_capture()


def has_screen_capture_holds():
    with screen_capture_holds_lock: return bool(screen_capture_holds)


def query_hotkey_subtitle(reference_time):
    time.sleep(0.12)
    current=query_subtitle_at(time.time(),keep_empty=True,strict=True,quiet=True)
    if current and current.get("text") and screen_result_belongs_to_current_capture(current):
        log(f"Hotkey subtitle recovered from current state: {current['text']}","SCREEN")
        return current
    exact=query_subtitle_at(reference_time,quiet=True)
    if exact and exact.get("text") and screen_result_belongs_to_current_capture(exact): return exact
    return None


def stop_screen_process():
    global screen_process, screen_socket, screen_capture_active, screen_capture_started_at
    with screen_process_lock: process=screen_process; sock=screen_socket
    if process is None: return
    if process.poll() is not None:
        with screen_process_lock:
            if screen_process is process: screen_process=None
            if screen_socket is sock: screen_socket=None
        with screen_capture_state_lock:
            screen_capture_active=False; screen_capture_started_at=0.0
        return
    log("Stopping screen.swift process...","SCREEN")
    try:
        if sock is not None and process.poll() is None:
            with screen_command_lock: sock.sendall(b"EXIT\n")
    except Exception as e:
        log(f"Could not send EXIT to screen.swift: {e}","SCREEN")
    try:
        if sock is not None: sock.shutdown(socket.SHUT_RDWR)
    except Exception: pass
    try:
        if sock is not None: sock.close()
    except Exception: pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log("screen.swift did not exit in time. Sending SIGTERM.","SCREEN")
        try: os.kill(process.pid,signal.SIGTERM)
        except Exception: pass
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log("screen.swift still alive. Sending SIGKILL.","SCREEN")
            try: os.kill(process.pid,signal.SIGKILL)
            except Exception: pass
    with screen_process_lock:
        if screen_process is process: screen_process=None
        if screen_socket is sock: screen_socket=None
    with screen_capture_state_lock:
        screen_capture_active=False; screen_capture_started_at=0.0
    screen_capture_started_event.clear(); screen_capture_stopped_event.clear()
    if os.path.exists(screen_socket_path):
        try: os.remove(screen_socket_path)
        except OSError: pass

def parse_hotkey(value):
    if not isinstance(value, str) or not value.strip():
        value = "cmd+shift+a"

    aliases = {
        "command": "cmd",
        "control": "ctrl",
        "option": "alt",
        "⌘": "cmd",
        "⌥": "alt"
    }

    parts = [
        part.strip().lower()
        for part in value.split("+")
        if part.strip()
    ]

    mods = set()
    key = None

    for part in parts:
        part = aliases.get(
            part,
            part
        )

        if part in {
            "cmd",
            "ctrl",
            "alt",
            "shift"
        }:
            mods.add(part)
        else:
            key = part

    return {
        "mods": mods,
        "key": key or "a"
    }


def refresh_hotkey_if_needed():
    global hotkey_mtime
    global hotkey_string
    global hotkey_parts

    try:
        current_mtime = os.path.getmtime(
            settings_path
        )
    except OSError:
        current_mtime = None

    if current_mtime == hotkey_mtime:
        return

    data = load_settings_data()

    value = data.get(
        "hotkey",
        "cmd+shift+a"
    )

    if not isinstance(value, str):
        value = "cmd+shift+a"

    hotkey_string = value.strip()
    hotkey_parts = parse_hotkey(
        hotkey_string
    )

    hotkey_mtime = current_mtime

    log(
        f"Hotkey active: {hotkey_string}",
        "HOTKEY"
    )


def refresh_hotkey_throttled():
    global hotkey_last_check

    now = time.monotonic()

    if (
        now - hotkey_last_check
        < HOTKEY_SETTINGS_CHECK_INTERVAL
    ):
        return

    hotkey_last_check = now
    refresh_hotkey_if_needed()


def get_modifier_flags(mods):
    if Quartz is None:
        return 0

    flags = 0

    if "cmd" in mods:
        flags |= Quartz.kCGEventFlagMaskCommand

    if "ctrl" in mods:
        flags |= Quartz.kCGEventFlagMaskControl

    if "alt" in mods:
        flags |= Quartz.kCGEventFlagMaskAlternate

    if "shift" in mods:
        flags |= Quartz.kCGEventFlagMaskShift

    return flags


def open_permission_settings():
    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:"
            "com.apple.preference.security?"
            "Privacy_Accessibility"
        ])

    except Exception as e:
        log(
            f"Could not open permission settings: {e}",
            "HOTKEY"
        )


def request_permissions():
    if Quartz is None:
        return False

    accessibility_ok = True
    input_monitoring_ok = True

    if AXIsProcessTrustedWithOptions is not None:
        try:
            accessibility_ok = bool(
                AXIsProcessTrustedWithOptions({
                    kAXTrustedCheckOptionPrompt: True
                })
            )
        except Exception as e:
            log(
                f"Accessibility check failed: {e}",
                "HOTKEY"
            )

    if hasattr(
        Quartz,
        "CGPreflightListenEventAccess"
    ):
        try:
            input_monitoring_ok = bool(
                Quartz.CGPreflightListenEventAccess()
            )
        except Exception as e:
            log(
                f"Input Monitoring check failed: {e}",
                "HOTKEY"
            )

    if (
        not input_monitoring_ok
        and hasattr(
            Quartz,
            "CGRequestListenEventAccess"
        )
    ):
        try:
            log(
                "Requesting Input Monitoring permission...",
                "HOTKEY"
            )

            Quartz.CGRequestListenEventAccess()

        except Exception as e:
            log(
                f"Input Monitoring request failed: {e}",
                "HOTKEY"
            )

    if accessibility_ok and input_monitoring_ok:
        log(
            "Keyboard permissions are available.",
            "HOTKEY"
        )
        return True

    log(
        "Accessibility/Input Monitoring permissions are required.",
        "HOTKEY"
    )

    open_permission_settings()

    return False



def cleanup_job(job):
    job_dir = job.get("job_dir")

    if not job_dir:
        return

    try:
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
    except Exception as e:
        log(
            f"Job cleanup failed for {job_dir}: {e}",
            "QUEUE"
        )


def cleanup_old_queue_jobs():
    os.makedirs(
        queue_dir,
        exist_ok=True
    )

    try:
        for name in os.listdir(
            queue_dir
        ):
            path = os.path.join(
                queue_dir,
                name
            )

            if os.path.isdir(path):
                try:
                    shutil.rmtree(path)
                except Exception as e:
                    log(
                        f"Could not remove old job "
                        f"{name}: {e}",
                        "QUEUE"
                    )

    except Exception as e:
        log(
            f"Queue cleanup failed: {e}",
            "QUEUE"
        )

    shutil.rmtree(
        runs_dir,
        ignore_errors=True
    )


def subtitle_interval(subtitle):
    try:
        start = float(
            subtitle["startWallTime"]
        )
        end = float(
            subtitle["endWallTime"]
        )
    except Exception:
        return None

    if not (
        start > 0
        and end > start
    ):
        return None

    duration = end - start

    if duration > SUBTITLE_MAX_INTERVAL:
        log(
            f"Subtitle interval too long "
            f"({duration:.1f}s). "
            f"Using adaptive audio mode.",
            "SCREEN"
        )
        return None

    return (
        start,
        end
    )


def same_subtitle_text(a, b):
    return (
        normalize_text(
            a.get("text", "")
        )
        ==
        normalize_text(
            b.get("text", "")
        )
    )


def subtitle_is_closed(
    reference,
    current
):
    if current is None:
        return False

    if not current.get("text"):
        return True

    return not same_subtitle_text(
        reference,
        current
    )


def finalize_audio_select(
    job,
    reference
):
    request_id = job["request_id"]
    word = job["word"]
    hotkey_time = job["audio_reference_time"]

    interval = None
    outcome = "timeout"
    failures = 0

    try:
        deadline = (
            time.time()
            + INTERVAL_CLOSE_TIMEOUT
        )

        while time.time() < deadline:
            with pending_audio_jobs_lock:
                alive = (
                    request_id
                    in pending_audio_jobs
                )

            if not alive:
                release_screen_capture_hold(request_id)
                return

            current = query_subtitle_at(
                time.time(),
                keep_empty=True,
                strict=True,
                quiet=True
            )

            if current is None:
                failures += 1

                if failures >= 3:
                    outcome = (
                        "screen watcher "
                        "not answering"
                    )
                    break

            else:
                failures = 0

                if subtitle_is_closed(
                    reference,
                    current
                ):
                    closed = query_subtitle_at(
                        float(reference["startWallTime"]) + 0.05,
                        quiet=True
                    )

                    if (
                        closed
                        and closed.get("text")
                        and same_subtitle_text(
                            closed,
                            reference
                        )
                    ):
                        interval = subtitle_interval(
                            closed
                        )

                    if interval is None:
                        time.sleep(0.08)

                        closed = query_subtitle_at(
                            float(reference["startWallTime"]) + 0.05,
                            quiet=True
                        )

                        if (
                            closed
                            and closed.get("text")
                            and same_subtitle_text(
                                closed,
                                reference
                            )
                        ):
                            interval = subtitle_interval(
                                closed
                            )

                    outcome = "closed"
                    break

            time.sleep(
                INTERVAL_POLL
            )

        if interval is None:
            try:
                start = float(
                    reference["startWallTime"]
                )
            except Exception:
                start = 0.0

            now = time.time()

            if (
                start > 0
                and 0 < now - start
                <= SUBTITLE_MAX_INTERVAL
            ):
                interval = (
                    start,
                    now
                )
                outcome = "open-timeout"

        if interval:
            log(
                f"Job {job['id']}: "
                f"subtitle {outcome}. "
                f"Audio interval "
                f"{interval[0]:.3f} -> "
                f"{interval[1]:.3f} "
                f"({interval[1] - interval[0]:.2f}s).",
                "AUDIO"
            )
        else:
            log(
                f"Job {job['id']}: "
                f"subtitle {outcome}. "
                f"Audio will use adaptive mode.",
                "AUDIO"
            )

    except Exception as e:
        log(
            f"Interval finalization failed: {e}",
            "AUDIO"
        )

    sent = send_audio_select(
        request_id,
        word,
        hotkey_time,
        interval
    )

    if not sent:
        job["audio_error"] = (
            "select_command_failed"
        )

        event = job.get(
            "audio_event"
        )

        if event is not None:
            event.set()

    release_screen_capture_hold(request_id)


def create_card_job(
    word,
    context,
    image_path,
    audio_reference_time,
    audio_interval=None,
    pending_subtitle=None,
    context_variants=None,
    language_profile=None
):
    if not os.path.exists(
        image_path
    ):
        log(
            "Card screenshot does not exist.",
            "QUEUE"
        )
        return False

    job_id = uuid.uuid4().hex[:8]
    request_id = uuid.uuid4().hex

    job_dir = os.path.join(
        queue_dir,
        job_id
    )

    os.makedirs(
        job_dir,
        exist_ok=True
    )

    queued_image = os.path.join(
        job_dir,
        "card.png"
    )

    try:
        shutil.copy2(
            image_path,
            queued_image
        )
    except Exception as e:
        log(
            f"Failed to copy card screenshot: {e}",
            "QUEUE"
        )

        cleanup_job({
            "job_dir": job_dir
        })

        return False

    audio_event = threading.Event()

    job = {
        "id": job_id,
        "request_id": request_id,
        "word": word,
        "context": context,
        "context_variants": list(context_variants or []),
        "language_profile": language_profile,
        "image": queued_image,
        "audio": "",
        "audio_error": "",
        "audio_event": audio_event,
        "audio_reference_time": audio_reference_time,
        "created_at": time.time(),
        "job_dir": job_dir
    }

    with pending_audio_jobs_lock:
        pending_audio_jobs[
            request_id
        ] = job

    log(
        f"Created Job {job_id}.",
        "QUEUE"
    )

    log(
        f"requestID = {request_id}",
        "AUDIO"
    )

    log(
        f"audio reference time = "
        f"{audio_reference_time:.6f}",
        "AUDIO"
    )

    if audio_interval:
        log(
            f"audio interval = "
            f"{audio_interval[0]:.6f} -> "
            f"{audio_interval[1]:.6f} "
            f"({audio_interval[1] - audio_interval[0]:.2f}s)",
            "AUDIO"
        )

    elif pending_subtitle:
        log(
            "audio interval = pending "
            "(waiting for subtitle to close)",
            "AUDIO"
        )

    else:
        log(
            "audio interval = none "
            "(adaptive mode)",
            "AUDIO"
        )

    audio_started = start_audio_process()

    if (
        audio_started
        and pending_subtitle
    ):
        add_screen_capture_hold(request_id)

        threading.Thread(
            target=finalize_audio_select,
            args=(
                job,
                pending_subtitle
            ),
            daemon=True,
            name=f"snap-audio-select-{job_id}"
        ).start()

        log(
            f"Job {job_id}: "
            "SELECT deferred until "
            f"the subtitle closes "
            f"(max {INTERVAL_CLOSE_TIMEOUT:.0f}s).",
            "AUDIO"
        )

    elif audio_started:
        sent = send_audio_select(
            request_id,
            word,
            audio_reference_time,
            audio_interval
        )

        if sent:
            log(
                f"SELECT sent for Job {job_id}.",
                "AUDIO"
            )
        else:
            job["audio_error"] = (
                "select_command_failed"
            )
            audio_event.set()

            log(
                f"SELECT failed for Job {job_id}.",
                "AUDIO"
            )

    else:
        job["audio_error"] = (
            "audio_process_unavailable"
        )

        audio_event.set()

        log(
            f"Job {job_id}: "
            "audio unavailable. "
            "Card will still be created.",
            "AUDIO"
        )

    try:
        card_queue.put_nowait(job)

    except Full:
        with pending_audio_jobs_lock:
            pending_audio_jobs.pop(
                request_id,
                None
            )

        release_screen_capture_hold(request_id)

        cleanup_job(job)

        log(
            f"Queue full. Job {job_id} rejected.",
            "QUEUE"
        )

        play_error_sound()

        return False

    log(
        f"Job {job_id} queued. "
        f"queue={card_queue.qsize()}/"
        f"{CARD_QUEUE_MAX}",
        "QUEUE"
    )

    return True


def run_card_job(job):
    card_path = os.path.join(
        current_dir,
        "card.py"
    )

    audio_event = job.get(
        "audio_event"
    )

    if (
        audio_event is not None
        and not job.get("audio")
        and not job.get("audio_error")
    ):
        log(
            f"Job {job['id']}: "
            f"waiting up to "
            f"{AUDIO_WAIT_TIMEOUT}s "
            "for audio.",
            "AUDIO"
        )

        audio_ready = audio_event.wait(
            timeout=AUDIO_WAIT_TIMEOUT
        )

        if audio_ready:
            if job.get("audio"):
                log(
                    f"Job {job['id']}: "
                    "audio received.",
                    "AUDIO"
                )
            else:
                log(
                    f"Job {job['id']}: "
                    "audio failed: "
                    f"{job.get('audio_error', 'unknown error')}",
                    "AUDIO"
                )

        else:
            job["audio_error"] = (
                "audio_timeout"
            )

            log(
                f"Job {job['id']}: "
                f"no audio after "
                f"{AUDIO_WAIT_TIMEOUT}s. "
                "Continuing without audio.",
                "AUDIO"
            )

    audio_path = str(
        job.get("audio", "")
    ).strip()

    if audio_path and not os.path.isfile(
        audio_path
    ):
        log(
            f"Job {job['id']}: "
            "audio file disappeared: "
            f"{audio_path}",
            "AUDIO"
        )
        audio_path = ""

    profile_name = str(job.get("language_profile") or "").strip()
    profile_settings = load_settings_data().get("language_profiles", {})
    profile_data = profile_settings.get(profile_name, {}) if (
        profile_name and isinstance(profile_settings, dict)
    ) else {}
    if not isinstance(profile_data, dict):
        profile_data = {}

    payload = {
        "word": job["word"],
        "context": job["context"],
        "context_variants": job.get("context_variants", []),
        "image": job["image"],
        "audio": audio_path,
        "job_id": job["id"],
        "language_profile": profile_name,
        "language": profile_name,
        "translation_language": str(profile_data.get("translation_language", "")).strip(),
        "deck": str(profile_data.get("deck", "")).strip()
    }

    log(
        f"Job {job['id']} -> card.py",
        "QUEUE"
    )

    log(
        f"word = {job['word']}",
        "CARD"
    )

    log(
        f"context = {job['context']}",
        "CARD"
    )

    log(
        f"audio = {audio_path or 'none'}",
        "CARD"
    )

    process = None
    output_lines = []
    output_lock = threading.Lock()
    reader_thread = None

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                card_path
            ],
            cwd=current_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True
        )

        def read_card_output():
            if process.stdout is None:
                return
            for line in process.stdout:
                line = line.rstrip("\r\n")
                if line:
                    with output_lock:
                        output_lines.append(line)
                    print(line, flush=True)

        reader_thread = threading.Thread(
            target=read_card_output,
            daemon=True,
            name=f"snap-card-reader-{job['id']}"
        )
        reader_thread.start()

        process.stdin.write(
            json.dumps(payload, ensure_ascii=False)
        )
        process.stdin.flush()
        process.stdin.close()

        return_code = process.wait(timeout=CARD_TIMEOUT)
        if reader_thread is not None:
            reader_thread.join(timeout=1.5)

        with output_lock:
            lines = list(output_lines)

        diagnostic = ""
        for line in reversed(lines):
            if line.startswith("Card: ERROR ="):
                diagnostic = line.split("=", 1)[1].strip()
                break
            if line.startswith("Card: not added ="):
                diagnostic = line.split("=", 1)[1].strip()
                break

        # If card.py exits before its own error handler runs (for example, an
        # ImportError during module import), the useful cause is the final line
        # of Python's traceback rather than a "Card: ERROR =" log entry.
        if not diagnostic:
            for line in reversed(lines):
                candidate = line.strip()
                if re.match(
                    r"^(?:[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Interrupt|Exit)|SystemExit|KeyboardInterrupt)(?::|$)",
                    candidate
                ):
                    diagnostic = candidate
                    break

        if not diagnostic and any(
            line.strip().startswith("Traceback (most recent call last):")
            for line in lines
        ):
            nonempty_lines = [line.strip() for line in lines if line.strip()]
            if nonempty_lines:
                diagnostic = nonempty_lines[-1]

        if return_code == 0:
            log(
                f"Job {job['id']} completed successfully.",
                "QUEUE"
            )
            job["error_message"] = ""
            return True

        log(
            f"Job {job['id']} failed. Exit code={return_code}",
            "QUEUE"
        )
        job["error_message"] = humanize_job_error(
            diagnostic or f"Card generation failed with exit code {return_code}. Check snap.log for details."
        )
        log(f"Job {job['id']} failure reason = {job['error_message']}", "CARD")
        return False

    except subprocess.TimeoutExpired:
        log(
            f"Job {job['id']} exceeded "
            f"{CARD_TIMEOUT}s.",
            "QUEUE"
        )
        job["error_message"] = (
            "Card generation timed out. Check whether LM Studio is responding, then try again."
        )

        if process is not None:
            try:
                os.killpg(
                    process.pid,
                    signal.SIGTERM
                )
            except Exception:
                pass

            try:
                process.wait(
                    timeout=3
                )
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(
                        process.pid,
                        signal.SIGKILL
                    )
                except Exception:
                    pass

                try:
                    process.wait()
                except Exception:
                    pass

        if reader_thread is not None:
            reader_thread.join(timeout=1.0)
        return False

    except Exception as e:
        job["error_message"] = humanize_job_error(str(e))
        log(
            f"Job {job['id']} failed: {e}",
            "QUEUE"
        )

        if process is not None:
            try:
                if process.poll() is None:
                    os.killpg(
                        process.pid,
                        signal.SIGTERM
                    )
            except Exception:
                pass

        return False


def card_worker():
    os.makedirs(
        queue_dir,
        exist_ok=True
    )

    log(
        "Card worker started.",
        "QUEUE"
    )

    while True:
        job = card_queue.get()

        try:
            if run_card_job(job):
                show_card_added_notification()
            else:
                show_error_notification(
                    job.get("error_message") or "Card generation failed. Check snap.log for technical details."
                )

        except Exception as e:
            log(
                f"Critical Job error "
                f"{job.get('id')}: {e}",
                "QUEUE"
            )
            show_error_notification(
                str(e),
                title="Snap could not create the card"
            )

        finally:
            request_id = job.get(
                "request_id"
            )

            with pending_audio_jobs_lock:
                current_job = pending_audio_jobs.get(
                    request_id
                )

                if current_job is job:
                    pending_audio_jobs.pop(
                        request_id,
                        None
                    )

            cleanup_job(job)

            card_queue.task_done()

            log(
                f"Job {job.get('id')} cleaned. "
                f"queue={card_queue.qsize()}",
                "QUEUE"
            )


def start_card_worker():
    threading.Thread(
        target=card_worker,
        daemon=True,
        name="snap-card-worker"
    ).start()



def run_ocr(hotkey_time):
    global ocr_running

    log("run_ocr entered.", "OCR")

    if not ocr_selection_lock.acquire(blocking=False):
        log("Selection is already in progress.", "OCR")
        return

    log("Selection lock acquired.", "OCR")

    ocr_running = True
    state = {"released": False}

    def release_selection():
        global ocr_running
        global toast_suppressed_for_selection
        global toast_notification_pending
        global toast_pending_payload

        if state["released"]:
            return

        state["released"] = True
        ocr_running = False

        try:
            ocr_selection_lock.release()
        except RuntimeError:
            pass

        with toast_lock:
            toast_suppressed_for_selection = False
            notification_pending = toast_notification_pending
            pending_payload = toast_pending_payload
            toast_notification_pending = False
            toast_pending_payload = None

        if notification_pending:
            if pending_payload:
                show_notification(**pending_payload)
            else:
                show_card_added_notification()

    try:
        log("Calling process_ocr.", "OCR")
        process_ocr(hotkey_time, release_selection)
    except Exception as e:
        log(f"Critical OCR error: {e}", "OCR")
        show_error_notification(
            f"OCR processing failed: {e}",
            title="Snap could not read the selection"
        )
    finally:
        release_selection()


def start_ocr(hotkey_time):
    threading.Thread(
        target=run_ocr,
        args=(hotkey_time,),
        daemon=True,
        name="snap-ocr-job"
    ).start()



def mac_event_callback(
    proxy,
    event_type,
    event,
    refcon
):
    global hotkey_active
    global audio_toggle_active

    if event_type in (
        Quartz.kCGEventTapDisabledByTimeout,
        Quartz.kCGEventTapDisabledByUserInput
    ):
        log(
            "Event tap was disabled by macOS. "
            "Re-enabling.",
            "HOTKEY"
        )

        if event_tap is not None:
            Quartz.CGEventTapEnable(
                event_tap,
                True
            )

        return event

    refresh_hotkey_throttled()

    if event_type not in (
        Quartz.kCGEventKeyDown,
        Quartz.kCGEventKeyUp
    ):
        return event

    keycode = Quartz.CGEventGetIntegerValueField(
        event,
        Quartz.kCGKeyboardEventKeycode
    )

    flags = Quartz.CGEventGetFlags(
        event
    )

    if keycode == AUDIO_TOGGLE_KEYCODE:
        required_audio_flags = get_modifier_flags(
            AUDIO_TOGGLE_MODS
        )

        audio_modifiers_match = (
            flags & required_audio_flags
        ) == required_audio_flags

        if (
            event_type
            == Quartz.kCGEventKeyDown
            and audio_modifiers_match
        ):
            if not audio_toggle_active:
                audio_toggle_active = True

                log(
                    f"Audio hotkey pressed: "
                    f"{AUDIO_TOGGLE_HOTKEY}",
                    "HOTKEY"
                )

                toggle_audio_capture()

            return None

        if (
            event_type
            == Quartz.kCGEventKeyUp
            and audio_toggle_active
        ):
            audio_toggle_active = False
            return None

    target_keycode = KEYCODES.get(
        hotkey_parts["key"]
    )

    if keycode != target_keycode:
        return event

    required_flags = get_modifier_flags(
        hotkey_parts["mods"]
    )

    modifiers_match = (
        flags & required_flags
    ) == required_flags

    if (
        event_type
        == Quartz.kCGEventKeyDown
        and modifiers_match
    ):
        if not hotkey_active:
            hotkey_active = True

            pressed_at = time.time()

            dismiss_card_added_notification(
                suppress_for_selection=True
            )

            start_ocr(
                pressed_at
            )

            log(
                "Hotkey pressed.",
                "HOTKEY"
            )

            log(
                f"Reference time = "
                f"{pressed_at:.6f}",
                "SCREEN"
            )

        return None

    if (
        event_type
        == Quartz.kCGEventKeyUp
        and hotkey_active
    ):
        hotkey_active = False
        return None

    return event


def start_hotkey_listener():
    global event_tap

    if Quartz is None:
        log(
            "Quartz unavailable. "
            "Global hotkey disabled.",
            "HOTKEY"
        )
        return

    request_permissions()

    log(
        "Checking hotkey permissions...",
        "HOTKEY"
    )

    for _ in range(30):
        try:
            accessibility_ok = True

            if AXIsProcessTrustedWithOptions is not None:
                accessibility_ok = bool(
                    AXIsProcessTrustedWithOptions(
                        None
                    )
                )

            input_monitoring_ok = True

            if hasattr(
                Quartz,
                "CGPreflightListenEventAccess"
            ):
                input_monitoring_ok = bool(
                    Quartz.CGPreflightListenEventAccess()
                )

            if (
                accessibility_ok
                and input_monitoring_ok
            ):
                break

        except Exception:
            pass

        time.sleep(1)

    event_mask = (
        (1 << Quartz.kCGEventKeyDown)
        | (1 << Quartz.kCGEventKeyUp)
    )

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        mac_event_callback,
        None
    )

    if tap is None:
        log(
            "Failed to create Quartz Event Tap.",
            "HOTKEY"
        )

        open_permission_settings()

        return

    event_tap = tap

    source = Quartz.CFMachPortCreateRunLoopSource(
        None,
        tap,
        0
    )

    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        source,
        Quartz.kCFRunLoopCommonModes
    )

    Quartz.CGEventTapEnable(
        tap,
        True
    )

    log(
        "Quartz hotkey listener started.",
        "HOTKEY"
    )

    log(
        "Audio toggle hotkey active: "
        "Cmd+Shift+] "
        "(Russian layout: Cmd+Shift+Ъ).",
        "HOTKEY"
    )

    Quartz.CFRunLoopRun()



def normalize_text(text):
    return re.sub(r"[^\w\s]", "", str(text), flags=re.UNICODE).lower().strip()


_TIMER_TOKEN_PATTERN = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")


def is_timer_only_text(text):
    value = str(text or "").strip()
    if not value:
        return False

    if not _TIMER_TOKEN_PATTERN.search(value):
        return False

    remainder = _TIMER_TOKEN_PATTERN.sub(" ", value)
    remainder = re.sub(r"[\s|/•·:：,.;()\[\]{}\-–—]+", "", remainder)
    return not remainder


def trim_word_edges(word):
    value = str(word or "").strip()
    if not any(char.isalnum() for char in value):
        return value
    while value and (value[0].isspace() or unicodedata.category(value[0]).startswith("P")):
        value = value[1:]
    while value and (value[-1].isspace() or unicodedata.category(value[-1]).startswith("P")):
        value = value[:-1]
    return value.strip()

def load_image(path):
    if (
        Vision is None
        or Foundation is None
        or Quartz is None
    ):
        raise RuntimeError(
            "Apple Vision is unavailable."
        )

    url = Foundation.NSURL.fileURLWithPath_(
        os.path.abspath(path)
    )

    source = Quartz.CGImageSourceCreateWithURL(
        url,
        None
    )

    if source is None:
        raise RuntimeError(
            f"Vision could not open image: {path}"
        )

    image = Quartz.CGImageSourceCreateImageAtIndex(
        source,
        0,
        None
    )

    if image is None:
        raise RuntimeError(
            f"Vision could not decode image: {path}"
        )

    return image


def run_vision_ocr(
    path,
    detail=False
):
    refresh_ocr_if_needed()

    wanted_languages = get_vision_languages(loaded_ocr_languages)
    use_language_correction = get_ocr_correction_enabled()
    image = load_image(path)

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelAccurate
    )

    try:
        supported_result = request.supportedRecognitionLanguagesAndReturnError_(None)
        supported_languages = set(supported_result[0] or []) if supported_result else set()
    except Exception as e:
        supported_languages = set()
        log(f"Vision supported-language query unavailable: {e}", "OCR")

    if supported_languages:
        languages = [language for language in wanted_languages if language in supported_languages]
        # If Apple's language query is incomplete, do not silently switch to English.
        if not languages:
            languages = wanted_languages
    else:
        languages = wanted_languages

    languages.sort(key=lambda code: (code not in CJK_VISION_LANGUAGES, code == "en-US"))
    has_cjk = any(language in CJK_VISION_LANGUAGES for language in languages)

    request.setRecognitionLanguages_(languages)
    request.setUsesLanguageCorrection_(False if has_cjk else use_language_correction)

    log(
        f"Vision request: languages={languages}, "
        f"correction={False if has_cjk else use_language_correction}",
        "OCR"
    )

    handler = (
        Vision.VNImageRequestHandler
        .alloc()
        .initWithCGImage_options_(
            image,
            {}
        )
    )

    _, error = handler.performRequests_error_(
        [request],
        None
    )

    if error is not None:
        raise RuntimeError(
            f"Vision OCR failed: {error}"
        )

    observations = (
        request.results()
        or []
    )

    image_width = Quartz.CGImageGetWidth(
        image
    )

    image_height = Quartz.CGImageGetHeight(
        image
    )

    output = []

    for observation in observations:
        candidates = observation.topCandidates_(
            1
        )

        if not candidates:
            continue

        candidate = candidates[0]

        text = str(
            candidate.string()
        ).strip()

        if not text:
            continue

        try:
            confidence = float(
                candidate.confidence()
            )
        except Exception:
            confidence = 0.0

        if not detail:
            output.append(text)
            continue

        bbox = observation.boundingBox()

        x1 = (
            bbox.origin.x
            * image_width
        )

        y1 = (
            1.0
            - bbox.origin.y
            - bbox.size.height
        ) * image_height

        x2 = (
            bbox.origin.x
            + bbox.size.width
        ) * image_width

        y2 = (
            1.0
            - bbox.origin.y
        ) * image_height

        output.append({
            "text": text,
            "confidence": confidence,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "cx": (x1 + x2) / 2,
            "cy": (y1 + y2) / 2,
            "width": x2 - x1,
            "height": y2 - y1
        })

    return output


def get_ocr_text(path):
    results = run_vision_ocr(
        path,
        detail=False
    )

    return " ".join(
        result.strip()
        for result in results
        if str(result).strip()
    )


def get_ocr_boxes(path):
    return run_vision_ocr(
        path,
        detail=True
    )


def prepare_word_image(source_path, output_path):
    """Upscale small selection crops for OCR without changing the template image."""
    try:
        image = Image.open(source_path).convert("RGB")
        width, height = image.size
        longest = max(width, height)
        scale = 3 if longest < 300 else (2 if longest < 600 else 1)

        if scale > 1:
            image = image.resize(
                (width * scale, height * scale),
                Image.Resampling.LANCZOS
            )

        pad = 40
        try:
            background = image.getpixel((0, 0))
        except Exception:
            background = (0, 0, 0)

        canvas = Image.new(
            "RGB",
            (image.width + pad * 2, image.height + pad * 2),
            background
        )
        canvas.paste(image, (pad, pad))
        canvas.save(output_path)
        log(
            f"Prepared word OCR image: {width}x{height} -> "
            f"{canvas.width}x{canvas.height} (scale={scale}).",
            "OCR"
        )
        return output_path
    except Exception as e:
        log(f"Could not prepare enlarged word image: {e}", "OCR")
        return source_path


def deduplicate_boxes(boxes):
    result = []

    for box in boxes:
        current_norm = normalize_text(
            box["text"]
        )

        if not current_norm:
            continue

        duplicate = False

        for i, existing in enumerate(result):
            existing_norm = normalize_text(
                existing["text"]
            )

            if (
                current_norm == existing_norm
                or current_norm in existing_norm
                or existing_norm in current_norm
            ):
                duplicate = True

                if (
                    box["confidence"]
                    > existing["confidence"]
                ):
                    result[i] = box

                break

        if not duplicate:
            result.append(box)

    return result



def safe_result(
    future,
    default=None
):
    try:
        return future.result()
    except Exception as e:
        log(
            f"Background task failed: {e}",
            "OCR"
        )
        return default


def word_in_text(word, text):
    word_tokens = normalize_text(word).split()
    text_tokens = normalize_text(text).split()
    if not word_tokens or not text_tokens or len(word_tokens) > len(text_tokens):
        return False

    for start in range(len(text_tokens) - len(word_tokens) + 1):
        matched = True
        for offset, word_token in enumerate(word_tokens):
            ratio = difflib.SequenceMatcher(None, word_token, text_tokens[start + offset]).ratio()
            if ratio <= 0.8:
                matched = False
                break
        if matched:
            return True

    return False


def remember_subtitle(ref):
    if not ref or not ref.get("text"):
        return

    text = str(ref.get("text", "")).strip()
    norm = normalize_text(text)

    try:
        start = float(ref.get("startWallTime", 0.0))
        end = float(ref.get("endWallTime", 0.0))
    except Exception:
        return

    if not norm or start <= 0:
        return

    now = time.time()

    with recent_subtitles_lock:
        recent_subtitles[:] = [item for item in recent_subtitles if now - item["saved_at"] <= 180.0]
        for item in recent_subtitles:
            if item["norm"] == norm and abs(item["start"] - start) < 0.5:
                item["text"] = text
                item["start"] = start
                item["end"] = end
                item["saved_at"] = now
                break
        else:
            recent_subtitles.append({"norm": norm, "text": text, "start": start, "end": end, "saved_at": now})

        recent_subtitles.sort(key=lambda item: item["saved_at"], reverse=True)
        del recent_subtitles[20:]


def lookup_cached_subtitle(word):
    now = time.time()

    with recent_subtitles_lock:
        recent_subtitles[:] = [item for item in recent_subtitles if now - item["saved_at"] <= 180.0]
        for item in recent_subtitles:
            if now - item["saved_at"] > 120.0:
                continue

            original_text = str(item.get("text", item.get("norm", ""))).strip()
            if not word_in_text(word, original_text):
                continue

            return {"text": original_text, "startWallTime": item["start"], "endWallTime": item["end"]}

    return None


def subtitle_text_similarity(first, second):
    first_norm = normalize_text(first)
    second_norm = normalize_text(second)
    if not first_norm or not second_norm:
        return 0.0
    return difflib.SequenceMatcher(None, first_norm, second_norm).ratio()


def collect_subtitle_contexts(word, named_candidates):
    candidates = []

    for source, candidate in named_candidates:
        if not isinstance(candidate, dict):
            continue
        text = str(candidate.get("text", "")).strip()
        if text and word_in_text(word, text):
            candidates.append({"source": source, "text": text})

    now = time.time()
    with recent_subtitles_lock:
        recent = [dict(item) for item in recent_subtitles if now - item.get("saved_at", 0) <= 120.0]

    anchor = candidates[0]["text"] if candidates else ""
    if not anchor:
        for item in recent:
            text = str(item.get("text", item.get("norm", ""))).strip()
            if text and word_in_text(word, text):
                anchor = text
                break

    for item in recent:
        text = str(item.get("text", item.get("norm", ""))).strip()
        if not text or not word_in_text(word, text):
            continue
        if anchor and subtitle_text_similarity(anchor, text) < 0.55:
            continue
        candidates.append({"source": "recent_subtitles", "text": text})

    if anchor:
        candidates = [item for item in candidates if subtitle_text_similarity(anchor, item["text"]) >= 0.55]

    result = []
    for item in candidates:
        norm = normalize_text(item["text"])
        duplicate = False
        for existing in result:
            existing_norm = normalize_text(existing["text"])
            if difflib.SequenceMatcher(None, norm, existing_norm).ratio() >= 0.98:
                duplicate = True
                break
        if not duplicate:
            result.append(item)
        if len(result) >= 3:
            break

    for index, item in enumerate(result):
        item["order"] = index

    return result

def query_closing_state(
    reference_time
):
    try:
        second = query_subtitle_at(
            reference_time,
            quiet=True
        )

        current = query_subtitle_at(
            time.time(),
            keep_empty=True,
            strict=True,
            quiet=True
        )

        return (
            second,
            current
        )

    except Exception as e:
        log(
            f"Subtitle closing-state query failed: {e}",
            "SCREEN"
        )
        return (
            None,
            None
        )



def get_display_under_cursor():
    try:
        event = Quartz.CGEventCreate(
            None
        )

        point = Quartz.CGEventGetLocation(
            event
        )

        error, displays, count = (
            Quartz.CGGetDisplaysWithPoint(
                point,
                1,
                None,
                None
            )
        )

        if (
            error == 0
            and count
            and displays
        ):
            return displays[0]

    except Exception:
        pass

    return Quartz.CGMainDisplayID()


def cgimage_to_pil(
    cg_image
):
    width = Quartz.CGImageGetWidth(
        cg_image
    )

    height = Quartz.CGImageGetHeight(
        cg_image
    )

    bytes_per_row = (
        Quartz.CGImageGetBytesPerRow(
            cg_image
        )
    )

    if (
        Quartz.CGImageGetBitsPerPixel(
            cg_image
        )
        != 32
    ):
        raise RuntimeError(
            "Unexpected display image pixel format"
        )

    provider = (
        Quartz.CGImageGetDataProvider(
            cg_image
        )
    )

    data = Quartz.CGDataProviderCopyData(
        provider
    )

    image = Image.frombuffer(
        "RGBA",
        (
            width,
            height
        ),
        bytes(data),
        "raw",
        "BGRA",
        bytes_per_row,
        1
    )

    return image.convert(
        "RGB"
    )


def grab_screen_via_screencapture():
    os.makedirs(
        snap_dir,
        exist_ok=True
    )

    path = os.path.join(
        snap_dir,
        f"grab_{uuid.uuid4().hex[:6]}.png"
    )

    try:
        result = subprocess.run(
            [
                "screencapture",
                "-x",
                path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if (
            result.returncode != 0
            or not os.path.exists(path)
        ):
            return None

        image = Image.open(
            path
        )

        image.load()

        return image.convert(
            "RGB"
        )

    except Exception as e:
        log(
            f"screencapture grab failed: {e}",
            "OCR"
        )
        return None

    finally:
        cleanup_paths(
            [path]
        )


def grab_screen_image(
    allow_fallback=True
):
    started = time.perf_counter()

    if Quartz is not None:
        try:
            display = get_display_under_cursor()

            cg_image = Quartz.CGDisplayCreateImage(
                display
            )

            if cg_image is not None:
                image = cgimage_to_pil(
                    cg_image
                )

                log(
                    f"Screen grabbed in "
                    f"{time.perf_counter() - started:.3f}s "
                    f"({image.size[0]}x"
                    f"{image.size[1]}).",
                    "OCR"
                )

                return image

            log(
                "CGDisplayCreateImage returned None.",
                "OCR"
            )

        except Exception as e:
            log(
                f"Fast screen grab failed: {e}",
                "OCR"
            )

    if not allow_fallback:
        return None

    image = grab_screen_via_screencapture()

    if image is not None:
        log(
            f"Screen grabbed via screencapture in "
            f"{time.perf_counter() - started:.2f}s.",
            "OCR"
        )

    return image



def find_word_on_screen(
    word_path,
    screen_image
):
    if (
        screen_image is None
        or not os.path.exists(word_path)
    ):
        return None

    template = cv2.imread(
        word_path,
        cv2.IMREAD_GRAYSCALE
    )

    if template is None:
        return None

    screen = np.array(
        screen_image.convert("L")
    )

    template_h, template_w = (
        template.shape
    )

    screen_h, screen_w = (
        screen.shape
    )

    if (
        template_w > screen_w
        or template_h > screen_h
    ):
        return None

    factor = (
        0.5
        if min(
            template_w,
            template_h
        ) >= 24
        else 1.0
    )

    if factor != 1.0:
        coarse_screen = cv2.resize(
            screen,
            None,
            fx=factor,
            fy=factor,
            interpolation=cv2.INTER_AREA
        )
    else:
        coarse_screen = screen

    coarse_h, coarse_w = (
        coarse_screen.shape
    )

    best = None

    for scale in [
        1.0,
        0.75,
        0.85,
        0.90,
        0.95,
        1.05,
        1.10,
        1.15,
        1.25
    ]:
        new_w = int(
            template_w * scale
        )

        new_h = int(
            template_h * scale
        )

        if (
            new_w < 5
            or new_h < 5
            or new_w > screen_w
            or new_h > screen_h
        ):
            continue

        if scale == 1.0:
            scaled = template
        else:
            scaled = cv2.resize(
                template,
                (
                    new_w,
                    new_h
                ),
                interpolation=cv2.INTER_AREA
            )

        if factor != 1.0:
            coarse_template = cv2.resize(
                scaled,
                None,
                fx=factor,
                fy=factor,
                interpolation=cv2.INTER_AREA
            )
        else:
            coarse_template = scaled

        coarse_template_h, coarse_template_w = (
            coarse_template.shape
        )

        if (
            coarse_template_w < 4
            or coarse_template_h < 4
            or coarse_template_w > coarse_w
            or coarse_template_h > coarse_h
        ):
            continue

        match = cv2.matchTemplate(
            coarse_screen,
            coarse_template,
            cv2.TM_CCOEFF_NORMED
        )

        _, value, _, location = (
            cv2.minMaxLoc(match)
        )

        if (
            best is None
            or value > best[0]
        ):
            best = (
                value,
                location[0] / factor,
                location[1] / factor,
                new_w,
                new_h,
                scaled
            )

        if (
            scale == 1.0
            and value >= 0.70
        ):
            break

    if best is None:
        return None

    (
        _,
        coarse_x,
        coarse_y,
        best_w,
        best_h,
        best_template
    ) = best

    margin = 12

    x0 = max(
        0,
        int(coarse_x) - margin
    )

    y0 = max(
        0,
        int(coarse_y) - margin
    )

    x1 = min(
        screen_w,
        int(coarse_x)
        + best_w
        + margin
    )

    y1 = min(
        screen_h,
        int(coarse_y)
        + best_h
        + margin
    )

    region = screen[
        y0:y1,
        x0:x1
    ]

    if (
        region.shape[0] < best_h
        or region.shape[1] < best_w
    ):
        return None

    match = cv2.matchTemplate(
        region,
        best_template,
        cv2.TM_CCOEFF_NORMED
    )

    _, value, _, location = (
        cv2.minMaxLoc(match)
    )

    if value < 0.55:
        return None

    return {
        "x": x0 + location[0],
        "y": y0 + location[1],
        "w": best_w,
        "h": best_h,
        "confidence": value
    }


def create_context_image(
    screen_image,
    rect,
    output_path
):
    if screen_image is None:
        return False

    try:
        screen_w, screen_h = (
            screen_image.size
        )

        x = int(rect["x"])
        y = int(rect["y"])
        w = int(rect["w"])
        h = int(rect["h"])

        padding_x = 2400
        padding_top = 260
        padding_bottom = 320

        left = max(
            0,
            x - padding_x
        )

        top = max(
            0,
            y - padding_top
        )

        right = min(
            screen_w,
            x + w + padding_x
        )

        bottom = min(
            screen_h,
            y + h + padding_bottom
        )

        cropped = screen_image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )

        cropped.save(
            output_path,
            compress_level=3
        )

        return {
            "x": x - left,
            "y": y - top,
            "w": w,
            "h": h
        }

    except Exception as e:
        log(
            f"Context image creation failed: {e}",
            "OCR"
        )
        return False


def get_context_lines(context_path, word_rect):
    # Player timers are screen UI, not subtitle text. Filter them before grouping
    # boxes so they cannot be merged into the subtitle row at the same height.
    boxes = [
        box for box in deduplicate_boxes(get_ocr_boxes(context_path))
        if not is_timer_only_text(box.get("text", ""))
    ]
    if not boxes:
        return []

    boxes.sort(key=lambda box: (box["cy"], box["x1"]))
    groups = []

    for box in boxes:
        height = max(1.0, float(box.get("height", 1.0)))
        selected_group = None
        selected_distance = None

        for group in groups:
            center_y = sum(item["cy"] for item in group) / len(group)
            group_height = sum(max(1.0, float(item.get("height", 1.0))) for item in group) / len(group)
            tolerance = max(8.0, min(height, group_height) * 0.6)
            distance = abs(float(box["cy"]) - center_y)
            if distance <= tolerance and (selected_distance is None or distance < selected_distance):
                selected_group = group
                selected_distance = distance

        if selected_group is None:
            groups.append([box])
        else:
            selected_group.append(box)

    lines = []
    for group in groups:
        group.sort(key=lambda box: box["x1"])
        parts = []
        seen = set()
        for box in group:
            text = str(box.get("text", "")).strip()
            norm = normalize_text(text)
            if text and norm and norm not in seen:
                seen.add(norm)
                parts.append(text)
        text = " ".join(parts).strip()
        if text:
            lines.append({
                "text": text,
                "cy": sum(box["cy"] for box in group) / len(group),
                "x1": min(float(box.get("x1", 0)) for box in group),
                "x2": max(float(box.get("x2", 0)) for box in group),
                "top": min(float(box.get("y1", box.get("cy", 0))) for box in group),
                "bottom": max(float(box.get("y2", box.get("cy", 0))) for box in group),
                "height": max(1.0, max(float(box.get("y2", box.get("cy", 1))) for box in group) - min(float(box.get("y1", box.get("cy", 0))) for box in group))
            })

    lines.sort(key=lambda line: line["cy"])
    for index, line in enumerate(lines):
        line["order"] = index
    return lines


def score_target_line(target_word, line_text):
    target_tokens = [token for token in normalize_text(target_word).split() if len(token) >= 3]
    line_tokens = normalize_text(line_text).split()
    if not target_tokens or not line_tokens:
        return 0.0

    score = 0.0
    used = set()
    for target in target_tokens:
        best = 0.0
        best_index = None
        for index, token in enumerate(line_tokens):
            if index in used:
                continue
            ratio = difflib.SequenceMatcher(None, target, token).ratio()
            if ratio > best:
                best = ratio
                best_index = index
        if best_index is not None and best >= 0.66:
            used.add(best_index)
            score += min(len(target), 8) * best
    return score


def can_merge_subtitle_rows(first, second):
    first_height = max(1.0, float(first.get("height", 1.0)))
    second_height = max(1.0, float(second.get("height", 1.0)))
    gap = max(0.0, max(first.get("top", first["cy"]), second.get("top", second["cy"])) - min(first.get("bottom", first["cy"]), second.get("bottom", second["cy"])))
    if gap > max(28.0, min(first_height, second_height) * 1.5):
        return False

    first_center = (float(first.get("x1", 0)) + float(first.get("x2", 0))) / 2
    second_center = (float(second.get("x1", 0)) + float(second.get("x2", 0))) / 2
    width_alignment = max(85.0, min(max(float(first.get("x2", 0)) - float(first.get("x1", 0)), float(second.get("x2", 0)) - float(second.get("x1", 0))) * 0.16, 220.0))
    if abs(first_center - second_center) > width_alignment:
        return False

    if not re.search(r"[^\W_]{3,}", str(first.get("text", "")), flags=re.UNICODE):
        return False
    if not re.search(r"[^\W_]{3,}", str(second.get("text", "")), flags=re.UNICODE):
        return False
    return True


def subtitle_context_block(lines, primary):
    if not lines or primary not in lines:
        return primary["text"].strip() if primary else ""

    index = lines.index(primary)
    candidates = []
    for other_index in (index - 1, index + 1):
        if other_index < 0 or other_index >= len(lines):
            continue
        other = lines[other_index]
        if can_merge_subtitle_rows(primary, other):
            gap = max(0.0, max(primary.get("top", primary["cy"]), other.get("top", other["cy"])) - min(primary.get("bottom", primary["cy"]), other.get("bottom", other["cy"])))
            p_center = (primary.get("x1", 0) + primary.get("x2", 0)) / 2
            o_center = (other.get("x1", 0) + other.get("x2", 0)) / 2
            candidates.append((gap + abs(p_center - o_center) * 0.35, other_index, other))

    if not candidates:
        return primary["text"].strip()

    _, other_index, other = min(candidates, key=lambda item: item[0])
    pair = sorted([primary, other], key=lambda line: line["cy"])
    return "\n".join(line["text"].strip() for line in pair)


def get_context_line(context_path, word_rect, target_word="", lines=None):
    if lines is None:
        lines = get_context_lines(context_path, word_rect)
    if not lines:
        return ""

    target_word = str(target_word or "").strip()
    word_center_y = word_rect["y"] + word_rect["h"] / 2

    primary = None
    if target_word:
        matching = [line for line in lines if word_in_text(target_word, line["text"])]
        if matching:
            primary = min(matching, key=lambda line: abs(line["cy"] - word_center_y))
        else:
            scored = [(score_target_line(target_word, line["text"]), line) for line in lines]
            scored = [(score, line) for score, line in scored if score > 0]
            if scored:
                primary = max(scored, key=lambda item: (item[0], -abs(item[1]["cy"] - word_center_y)))[1]

    if primary is None:
        # If text matching fails, only use a spatial fallback when a real text
        # row is close to the selected region. Do not promote distant UI to context.
        primary = min(lines, key=lambda line: abs(line["cy"] - word_center_y))
        distance = abs(float(primary["cy"]) - float(word_center_y))
        tolerance = max(90.0, float(word_rect.get("h", 0)) * 2.5, float(primary.get("height", 0)) * 1.5)
        if distance > tolerance:
            log(
                f"No target match and nearest OCR row is too far away "
                f"({distance:.1f}px > {tolerance:.1f}px); context rejected.",
                "OCR"
            )
            return ""
        log(
            "Target text did not match OCR rows; using only the nearby non-timer row as low-confidence context.",
            "OCR"
        )

    context = subtitle_context_block(lines, primary)
    if is_timer_only_text(context):
        log("Timer-only OCR context rejected.", "OCR")
        return ""
    return context


def get_fallback_context(context_path):
    try:
        results = run_vision_ocr(context_path, detail=False)
    except Exception as e:
        log(f"Fallback OCR failed: {e}", "OCR")
        return ""

    meaningful = [
        str(result).strip()
        for result in results
        if str(result).strip() and not is_timer_only_text(result)
    ]
    return " ".join(meaningful).strip()


def create_center_card_screenshot(
    screen_image,
    output_path
):
    if screen_image is None:
        return False

    try:
        screen_w, screen_h = (
            screen_image.size
        )

        capture_w = int(
            screen_w * 0.70
        )

        capture_h = int(
            screen_h * 0.65
        )

        vertical_shift = int(
            screen_h * 0.10
        )

        left = (
            screen_w
            - capture_w
        ) // 2

        top = max(
            0,
            (
                screen_h
                - capture_h
            ) // 2
            - vertical_shift
        )

        right = min(
            screen_w,
            left + capture_w
        )

        bottom = min(
            screen_h,
            top + capture_h
        )

        cropped = screen_image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )

        cropped.save(
            output_path,
            compress_level=3
        )

        log(
            f"Card screenshot: "
            f"x={left}, y={top}, "
            f"w={right - left}, "
            f"h={bottom - top}",
            "OCR"
        )

        return True

    except Exception as e:
        log(
            f"Card screenshot creation failed: {e}",
            "OCR"
        )
        return False


def find_context_from_screen(word_path, context_path, hotkey_image, word_text=""):
    rect = None
    screen_image = None

    if hotkey_image is not None:
        rect = find_word_on_screen(word_path, hotkey_image)
        if rect is not None:
            screen_image = hotkey_image

    if rect is None:
        fresh = grab_screen_image(allow_fallback=True)
        if fresh is not None:
            rect = find_word_on_screen(word_path, fresh)
            if rect is not None:
                screen_image = fresh

    if rect is None:
        log("Could not locate selected word on screen.", "OCR")
        return "", []

    log(f"Position: x={rect['x']} y={rect['y']} w={rect['w']} h={rect['h']} match={rect['confidence']:.2f}", "OCR")

    local_rect = create_context_image(screen_image, rect, context_path)
    if not local_rect:
        log("Context image could not be created.", "OCR")
        return "", []

    target_word = str(word_text or get_ocr_text(word_path)).strip()
    lines = get_context_lines(context_path, local_rect)
    context_text = get_context_line(context_path, local_rect, target_word, lines)

    if context_text and is_timer_only_text(context_text):
        log("Timer-only OCR context rejected before card generation.", "OCR")
        context_text = ""

    if context_text:
        block_texts = [part.strip() for part in context_text.splitlines() if part.strip()]
        included = [line for line in lines if line["text"].strip() in block_texts]
        word_center_y = local_rect["y"] + local_rect["h"] / 2
        primary = min(included or lines, key=lambda line: abs(line["cy"] - word_center_y))
        exact_target_found = bool(target_word and any(word_in_text(target_word, line["text"]) for line in lines))
        partial_target_found = bool(target_word and max((score_target_line(target_word, line["text"]) for line in lines), default=0.0) > 0)
        if not exact_target_found and not partial_target_found:
            log("Target text did not match any OCR row; the selected nearby row is low-confidence context.", "OCR")

        included_orders = {line["order"] for line in included}
        variants = []
        for line in lines:
            if line["order"] in included_orders:
                continue
            if abs(line["order"] - primary["order"]) > 2:
                continue
            variants.append({"order": line["order"], "source": "screen", "text": line["text"]})

        log(f"CONTEXT block from screen = {context_text}", "OCR")
        for variant in variants:
            log(f"CONTEXT variant order={variant['order']} = {variant['text']}", "OCR")
        return context_text.strip(), variants

    fallback = get_fallback_context(context_path).strip()
    if fallback:
        log("No individual OCR rows found; using non-timer OCR text as last-resort context.", "OCR")
    else:
        log("No usable on-screen context found; card will be evaluated without context.", "OCR")
    return fallback, []

def process_ocr(
    hotkey_time,
    release_selection
):
    start_time = time.perf_counter()

    run_id = uuid.uuid4().hex[:8]

    run_dir = os.path.join(
        runs_dir,
        run_id
    )

    os.makedirs(
        run_dir,
        exist_ok=True
    )

    word_path = os.path.join(
        run_dir,
        "word.png"
    )

    word_ocr_path = os.path.join(
        run_dir,
        "word_ocr.png"
    )

    context_path = os.path.join(
        run_dir,
        "context.png"
    )

    card_image_path = os.path.join(
        run_dir,
        "card_screenshot.png"
    )

    futures = []
    selection_process = None
    screen_capture_started_for_job = False

    log(
        f"OCR job {run_id} started.",
        "OCR"
    )

    try:
        screen_capture_started_for_job = start_screen_capture()

        if not screen_capture_started_for_job:
            log(
                "Screen capture could not be started. "
                "Subtitle tracking will use screenshot context fallback.",
                "SCREEN"
            )

        hotkey_image = grab_screen_image(
            allow_fallback=False
        )

        try:
            selection_process = subprocess.Popen(
                [
                    "screencapture",
                    "-i",
                    "-s",
                    "-x",
                    word_path
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        except Exception as e:
            log(
                f"Could not start screencapture: {e}",
                "OCR"
            )

            play_error_sound()
            show_error_notification(
                f"Could not open the macOS selection tool: {e}",
                title="Word selection failed"
            )
            return

        log(
            f"Selection overlay launched "
            f"{time.time() - hotkey_time:.2f}s "
            "after hotkey.",
            "OCR"
        )

        subtitle_future = ocr_executor.submit(
            query_hotkey_subtitle,
            hotkey_time
        )

        futures.append(
            subtitle_future
        )

        card_future = None

        if hotkey_image is not None:
            card_future = ocr_executor.submit(
                create_center_card_screenshot,
                hotkey_image,
                card_image_path
            )

            futures.append(
                card_future
            )

        selection_start = time.perf_counter()

        try:
            selection_process.wait()
        finally:
            release_selection()

        selection_time = (
            time.perf_counter()
            - selection_start
        )

        if not os.path.exists(
            word_path
        ):
            log(
                "Selection cancelled "
                "or screenshot was not created.",
                "OCR"
            )
            return

        log(
            f"Selection completed in "
            f"{selection_time:.2f}s.",
            "OCR"
        )

        requery_future = ocr_executor.submit(
            query_closing_state,
            hotkey_time
        )

        futures.append(
            requery_future
        )

        refresh_ocr_if_needed()

        word_start = time.perf_counter()

        prepared_word_path = prepare_word_image(
            word_path,
            word_ocr_path
        )
        word_text = trim_word_edges(
            get_ocr_text(prepared_word_path)
        )

        log(
            f"Word OCR took "
            f"{time.perf_counter() - word_start:.2f}s.",
            "OCR"
        )

        if not word_text:
            log(
                "Selected word was not recognized.",
                "OCR"
            )

            play_error_sound()
            show_error_notification(
                "Try a larger selection or check OCR language settings.",
                title="Text not recognized"
            )
            return

        log(
            f"WORD = {word_text}",
            "OCR"
        )

        hotkey_reference = safe_result(
            subtitle_future
        )

        second, current = safe_result(
            requery_future,
            (
                None,
                None
            )
        )

        named_candidates = [
            ("hotkey_reference", hotkey_reference),
            ("second", second),
            ("current", current)
        ]

        candidates = []
        for source, candidate in named_candidates:
            if not candidate or not candidate.get("text"):
                continue
            if not any(same_subtitle_text(candidate, existing) for existing in candidates):
                candidates.append(candidate)
            if word_in_text(word_text, candidate["text"]):
                remember_subtitle(candidate)

        reference = None
        for candidate in candidates:
            if word_in_text(word_text, candidate["text"]):
                reference = candidate
                break

        if reference is None:
            cached_reference = lookup_cached_subtitle(word_text)
            if cached_reference is not None:
                reference = cached_reference
                log(f"Subtitle recovered from recent cache = {reference['text']}", "SCREEN")

        if reference is not None and reference.get("text") and not any(candidate is reference for _, candidate in named_candidates):
            named_candidates.append(("recent_subtitles", reference))

        subtitle_contexts = collect_subtitle_contexts(word_text, named_candidates)
        if subtitle_contexts:
            selected_context = max(subtitle_contexts, key=lambda item: len(item["text"]))
            context_text = selected_context["text"].strip()
            context_variants = [dict(item) for item in subtitle_contexts if item is not selected_context]
        else:
            context_text = ""
            context_variants = []

        audio_interval = None
        pending_subtitle = None

        if reference and reference.get("text") and word_in_text(word_text, reference["text"]):
            log(f"CONTEXT from subtitle history = {context_text}", "OCR")
            if subtitle_is_closed(reference, current):
                audio_interval = subtitle_interval(reference)
                if audio_interval:
                    log("Subtitle interval is closed. Using it for audio.", "SCREEN")
            else:
                pending_subtitle = reference
                log(f"Subtitle is still on screen. Waiting up to {INTERVAL_CLOSE_TIMEOUT:.0f}s for it to close.", "SCREEN")
        else:
            if reference:
                log("Selected word is not part of the subtitle. Using on-screen context.", "SCREEN")
            else:
                log("No historical subtitle found.", "SCREEN")

        if not context_text:
            context_start = time.perf_counter()
            context_text, context_variants = find_context_from_screen(word_path, context_path, hotkey_image, word_text)
            log(f"On-screen context took {time.perf_counter() - context_start:.2f}s.", "OCR")

        if not context_text:
            # A missing context is safer than a timer or unrelated UI falsely
            # presented as context. Keep the selected target and let card.py
            # reject only targets that are clearly OCR garbage.
            log(
                "No usable context was recognized. Continuing with empty context "
                "instead of passing unrelated UI text to the language model.",
                "OCR"
            )
            context_text = ""
            context_variants = []

        log(
            f"CONTEXT = {context_text or '[none]'}",
            "OCR"
        )

        language_profile = detect_profile_language(
            word_text,
            context_text
        )
        log(
            f"Detected language profile = {language_profile or '[not determined]'}",
            "OCR"
        )

        card_ok = False

        if card_future is not None:
            card_ok = bool(
                safe_result(
                    card_future,
                    False
                )
            )

        if not card_ok:
            fresh = grab_screen_image(
                allow_fallback=True
            )

            card_ok = create_center_card_screenshot(
                fresh,
                card_image_path
            )

        if not card_ok:
            log(
                "Card screenshot could not be created.",
                "OCR"
            )

            play_error_sound()
            show_error_notification(
                "Snap could not capture the image to attach to the card. Check Screen Recording permission and try again.",
                title="Screenshot failed"
            )
            return

        queued = create_card_job(
            word_text,
            context_text,
            card_image_path,
            hotkey_time,
            audio_interval,
            pending_subtitle,
            context_variants=context_variants,
            language_profile=language_profile
        )

        if not queued:
            log(
                "Failed to create card job.",
                "QUEUE"
            )
            show_error_notification(
                "Snap could not queue the card job. The queue may be full or the screenshot could not be copied.",
                title="Card was not queued"
            )

    finally:
        release_selection()

        if (
            selection_process is not None
            and selection_process.poll() is None
        ):
            try:
                selection_process.terminate()
                selection_process.wait(
                    timeout=1
                )
            except Exception:
                try:
                    selection_process.kill()
                except Exception:
                    pass

        for future in futures:
            try:
                future.result(
                    timeout=5
                )
            except Exception:
                pass

        shutil.rmtree(
            run_dir,
            ignore_errors=True
        )

        if screen_capture_started_for_job and not has_screen_capture_holds():
            stop_screen_capture()

        log(
            f"OCR job {run_id} finished in "
            f"{time.perf_counter() - start_time:.2f}s.",
            "OCR"
        )



def shutdown():
    log(
        "Shutting down.",
        "SNAP"
    )

    with screen_capture_holds_lock:
        screen_capture_holds.clear()

    stop_screen_process()
    stop_audio_process()

    ocr_executor.shutdown(
        wait=False
    )


atexit.register(
    shutdown
)



log(
    "ocr.py started.",
    "SNAP"
)

log(
    f"Python = {sys.executable}",
    "SNAP"
)

log(
    f"Addon directory = {current_dir}",
    "SNAP"
)

log(
    f"audio.swift = {audio_swift_path}",
    "SNAP"
)

log(
    f"audio bundle = {audio_bundle_path}",
    "SNAP"
)

log(
    f"audio executable = {audio_executable_path}",
    "SNAP"
)

log(
    f"audio socket = {audio_socket_path}",
    "SNAP"
)

log(
    f"screen.swift = {screen_swift_path}",
    "SNAP"
)

log(
    f"screen executable = {screen_executable_path}",
    "SNAP"
)

log(
    f"screen bundle = {screen_bundle_path}",
    "SNAP"
)

log(
    f"screen socket = {screen_socket_path}",
    "SNAP"
)


refresh_hotkey_if_needed()

if Vision is None:
    log(
        "CRITICAL: Apple Vision is unavailable.",
        "SNAP"
    )
else:
    log(
        "Apple Vision OCR is active.",
        "SNAP"
    )


cleanup_old_queue_jobs()

start_card_worker()
start_audio_watchdog()


screen_started = start_screen_process()

if screen_started:
    log(
        "Screen subtitle service is ready. "
        "ScreenCaptureKit capture is OFF until the OCR hotkey.",
        "SNAP"
    )
else:
    log(
        "Screen subtitle service is unavailable. "
        "OCR will use screenshot context fallback.",
        "SCREEN"
    )


audio_started = start_audio_process()

if audio_started:
    log(
        "Audio subsystem is active. "
        "Continuous capture starts ON.",
        "SNAP"
    )
else:
    log(
        "Audio subsystem is unavailable. "
        "Cards will still be created without audio.",
        "SNAP"
    )


log(
    f"Snap is ready. "
    f"Hotkey = {hotkey_string}",
    "SNAP"
)

log(
    "ScreenCaptureKit remains OFF until an OCR hotkey starts a job.",
    "SCREEN"
)

log(
    "Audio capture remains running so "
    "the ring buffer can contain audio "
    "from before the screenshot/hotkey.",
    "AUDIO"
)

if compile_toast_helper_if_needed():
    log("System-wide notification helper is ready.", "UI")
else:
    log(
        "System-wide notification helper unavailable. "
        "Card creation will continue normally.",
        "UI"
    )

start_ocr_preloader()
start_hotkey_listener()

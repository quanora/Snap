import os
import subprocess
import re
<<<<<<< Updated upstream
=======
import difflib
import unicodedata
import unicodedata
>>>>>>> Stashed changes
import cv2
from PIL import Image
import json
import sys
import threading
import time
<<<<<<< Updated upstream
=======
import uuid
import shutil
import signal
import atexit
import socket
from queue import Queue, Full
from concurrent.futures import ThreadPoolExecutor
>>>>>>> Stashed changes

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
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt
    )
except ImportError:
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None


current_dir = os.path.dirname(
    os.path.abspath(__file__)
)

<<<<<<< Updated upstream
settings_path = os.path.join(
    current_dir,
    "settings.json"
)
=======
current_dir = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(current_dir, "settings.json")
queue_dir = os.path.join(current_dir, "Queue")
snap_dir = os.path.join(current_dir, ".snap")
runs_dir = os.path.join(snap_dir, "runs")
toast_swift_path = os.path.join(snap_dir, "SnapToast.swift")
toast_executable_path = os.path.join(snap_dir, "SnapToast")
>>>>>>> Stashed changes

shot1_path = os.path.join(
    current_dir,
    "word.png"
)

shot2_path = os.path.join(
    current_dir,
    "context.png"
)

screen_path = os.path.join(
    current_dir,
    "full_screen.png"
)

<<<<<<< Updated upstream
card_screenshot_path = os.path.join(
    current_dir,
    "card_screenshot.png"
)
=======
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
>>>>>>> Stashed changes


ALL_LANGUAGE_CODES = {
    "en", "de", "ru", "es", "fr", "it", "pt",
    "ch_sim", "ch_tra", "ja", "ko",
    "nl", "pl", "cs", "hu", "ro",
    "sv", "da", "no", "fi", "tr",
    "uk", "el", "he", "ar"
}


VISION_LANGUAGE_CODES = {
    "en": "en",
    "de": "de",
    "ru": "ru",
    "es": "es",
    "fr": "fr",
    "it": "it",
    "pt": "pt",
    "ch_sim": "zh-Hans",
    "ch_tra": "zh-Hant",
    "ja": "ja",
    "ko": "ko",
    "nl": "nl",
    "pl": "pl",
    "cs": "cs",
    "hu": "hu",
    "ro": "ro",
    "sv": "sv",
    "da": "da",
    "no": "no",
    "fi": "fi",
    "tr": "tr",
    "uk": "uk",
    "el": "el",
    "he": "he",
    "ar": "ar"
}


KEYCODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "`": 50,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "delete": 51,
    "backspace": 51,
    "esc": 53,
    "escape": 53,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126
}


loaded_ocr_languages = []
settings_mtime = None
ocr_running = False
ocr_settings_lock = threading.Lock()

hotkey_mtime = None
hotkey_string = "cmd+shift+a"
hotkey_parts = {
    "mods": {"cmd", "shift"},
    "key": "a"
}

<<<<<<< Updated upstream
hotkey_active = False
=======
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

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let mouse = NSEvent.mouseLocation

let selectedScreen =
    NSScreen.screens.first(where: { $0.frame.contains(mouse) })
    ?? NSScreen.main
    ?? NSScreen.screens.first

guard let screen = selectedScreen else {
    exit(1)
}

let icon = NSImageView()
let symbolConfig = NSImage.SymbolConfiguration(pointSize: 19, weight: .semibold)
    .applying(NSImage.SymbolConfiguration(paletteColors: [
        .white,
        NSColor(calibratedRed: 0.20, green: 0.78, blue: 0.40, alpha: 1.0)
    ]))

if let image = NSImage(
    systemSymbolName: "checkmark.circle.fill",
    accessibilityDescription: nil
) {
    icon.image = image.withSymbolConfiguration(symbolConfig) ?? image
}
icon.translatesAutoresizingMaskIntoConstraints = false

let label = NSTextField(labelWithString: "Card added")
label.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
label.textColor = NSColor.white.withAlphaComponent(0.95)

let stack = NSStackView(views: [icon, label])
stack.orientation = .horizontal
stack.alignment = .centerY
stack.spacing = 9
stack.translatesAutoresizingMaskIntoConstraints = false

let height: CGFloat = 46
let horizontalPadding: CGFloat = 20
let width = ceil(stack.fittingSize.width) + horizontalPadding * 2
let radius = height / 2

let visible = screen.visibleFrame
let x = visible.midX - width / 2
let targetY = visible.minY + visible.height * 0.17
let startY = targetY - 10

let panel = NSPanel(
    contentRect: NSRect(x: x, y: startY, width: width, height: height),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)

panel.level = .screenSaver
panel.collectionBehavior = [
    .canJoinAllSpaces,
    .fullScreenAuxiliary,
    .ignoresCycle
]
panel.isFloatingPanel = true
panel.becomesKeyOnlyIfNeeded = true
panel.hidesOnDeactivate = false
panel.ignoresMouseEvents = true
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.appearance = NSAppearance(named: .darkAqua)

let mask = NSImage(
    size: NSSize(width: height, height: height),
    flipped: false
) { rect in
    NSColor.black.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    return true
}
mask.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
mask.resizingMode = .stretch

let content = NSVisualEffectView(
    frame: NSRect(x: 0, y: 0, width: width, height: height)
)
content.material = .hudWindow
content.blendingMode = .behindWindow
content.state = .active
content.appearance = NSAppearance(named: .darkAqua)
content.maskImage = mask

content.addSubview(stack)

NSLayoutConstraint.activate([
    icon.widthAnchor.constraint(equalToConstant: 20),
    icon.heightAnchor.constraint(equalToConstant: 20),
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
    panel.animator().setFrame(
        NSRect(x: x, y: targetY, width: width, height: height),
        display: true
    )
}

DispatchQueue.main.asyncAfter(deadline: .now() + 1.3) {
    NSAnimationContext.runAnimationGroup({ context in
        context.duration = 0.2
        context.timingFunction = CAMediaTimingFunction(name: .easeIn)
        panel.animator().alphaValue = 0
        panel.animator().setFrame(
            NSRect(x: x, y: targetY + 6, width: width, height: height),
            display: true
        )
    }, completionHandler: {
        app.terminate(nil)
    })
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


def show_card_added_notification():
    global toast_process, toast_notification_pending

    if not compile_toast_helper_if_needed():
        log("Card added notification unavailable.", "UI")
        return

    with toast_lock:
        if toast_suppressed_for_selection:
            toast_notification_pending = True
            log("Card added notification deferred until selection ends.", "UI")
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
                [toast_executable_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            toast_process = process

        except Exception as e:
            log(f"Could not show Card added notification: {e}", "UI")
            return

    log(
        f"Native Card added notification started. PID={process.pid}",
        "UI"
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
        log("Card added notification dismissal requested.", "UI")

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
        log(f"Could not dismiss Card added notification: {e}", "UI")
>>>>>>> Stashed changes


def load_settings_data():
    if not os.path.exists(
        settings_path
    ):
        return {}

    try:
        with open(
            settings_path,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

    except Exception as e:
        print(
            f"Ошибка чтения settings.json: {e}"
        )
        return {}

    if not isinstance(
        data,
        dict
    ):
        return {}

    return data


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
<<<<<<< Updated upstream
    data = load_settings_data()

    languages = data.get(
        "ocr_languages",
        ["en"]
    )

    if not isinstance(
        languages,
        list
    ):
        print(
            "ocr_languages имеет неправильный формат. "
            "Используется OCR: ['en']"
        )
        return ["en"]
=======
    settings = load_settings_data()
    configured = settings.get("ocr_languages", ["en"])

    if not isinstance(configured, list):
        log("Invalid ocr_languages format. Ignoring explicit OCR language list.", "OCR")
        configured = []
>>>>>>> Stashed changes

    # Put configured study-language profiles first. This prevents a stale default
    # such as ["en"] from silently disabling recognition of Japanese subtitles.
    result = []
    profiles = settings.get("language_profiles", {})
    if isinstance(profiles, dict):
        for language in profiles:
            code = language_name_to_ocr_code(language)
            if code and code in ALL_LANGUAGE_CODES and code not in result:
                result.append(code)

<<<<<<< Updated upstream
    for language in languages:

        if not isinstance(
            language,
            str
        ):
=======
    # Keep manually configured OCR languages too, within the existing three-language limit.
    for language in configured:
        if not isinstance(language, str):
>>>>>>> Stashed changes
            continue
        language = language.strip()
        if language not in ALL_LANGUAGE_CODES:

            print(
                f"Неизвестный OCR язык пропущен: {language}"
            )

            continue
        if language not in result:
            result.append(
                language
            )

    if not result:
        legacy_language = str(settings.get("language", "")).strip()
        legacy_code = language_name_to_ocr_code(legacy_language)
        if legacy_code in ALL_LANGUAGE_CODES:
            result.append(legacy_code)

    return result[:3] or ["en"]


def get_ocr_correction_enabled():
    data = load_settings_data()

    value = data.get(
        "ocr_correction",
        True
    )

    if isinstance(
        value,
        bool
    ):
        return value

    return str(
        value
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on"
    }


def get_vision_languages(languages):
    result = []

    for language in languages:

        vision_code = VISION_LANGUAGE_CODES.get(
            language
        )

        if (
            vision_code
            and vision_code not in result
        ):
            result.append(
                vision_code
            )

    return result or ["en"]


def refresh_ocr_if_needed():
    global loaded_ocr_languages
    global settings_mtime

    with ocr_settings_lock:

        try:
            current_mtime = os.path.getmtime(
                settings_path
            )

        except OSError:
            current_mtime = None

        languages = load_ocr_languages()

        if (
            languages == loaded_ocr_languages
            and current_mtime == settings_mtime
        ):
            return

        if languages != loaded_ocr_languages:

            print(
                f"\nOCR языки изменились: "
                f"{loaded_ocr_languages} → {languages}"
            )

        loaded_ocr_languages = languages
        settings_mtime = current_mtime

        vision_languages = get_vision_languages(
            languages
        )

        print(
            f"Vision OCR языки активны: "
            f"{vision_languages}"
        )

        print(
            "Apple Vision не требует отдельной загрузки "
            "OCR-моделей."
        )


def preload_ocr():
    time.sleep(1)

    if ocr_running:
        return

    try:
        print(
            "Подготовка Apple Vision OCR..."
        )

        refresh_ocr_if_needed()

    except Exception as e:

        print(
            f"Ошибка подготовки Vision OCR: {e}"
        )


def start_ocr_preloader():
    threading.Thread(
        target=preload_ocr,
        daemon=True
    ).start()


def parse_hotkey(
    value
):
    if (
        not isinstance(
            value,
            str
        )
        or not value.strip()
    ):
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
            mods.add(
                part
            )

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

    hotkey_string = value

    hotkey_parts = parse_hotkey(
        value
    )

    hotkey_mtime = current_mtime

    print(
        f"Горячая клавиша активна: {hotkey_string}"
    )


def get_modifier_flags(
    mods
):
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

        time.sleep(1)

        subprocess.Popen([
            "open",
            "x-apple.systempreferences:"
            "com.apple.preference.security?"
            "Privacy_ListenEvent"
        ])

    except Exception as e:

        print(
            f"Не удалось открыть настройки разрешений: {e}"
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

            print(
                f"Ошибка проверки Accessibility: {e}"
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

            print(
                f"Ошибка проверки Input Monitoring: {e}"
            )

    if (
        not input_monitoring_ok
        and hasattr(
            Quartz,
            "CGRequestListenEventAccess"
        )
    ):

        try:

            print(
                "Запрашивается Input Monitoring..."
            )

            Quartz.CGRequestListenEventAccess()

        except Exception as e:

            print(
                f"Ошибка запроса Input Monitoring: {e}"
            )

    if (
        accessibility_ok
        and input_monitoring_ok
    ):

        print(
            "Разрешения клавиатуры уже получены."
        )

        return True

    print(
        "Требуются разрешения macOS для глобального хоткея."
    )

    open_permission_settings()

    return False


<<<<<<< Updated upstream
def run_ocr():
    global ocr_running

    if ocr_running:
=======

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
    context_variants=None
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

    payload = {
        "word": job["word"],
        "context": job["context"],
        "context_variants": job.get("context_variants", []),
        "image": job["image"],
        "audio": audio_path,
        "job_id": job["id"]
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
                line = line.rstrip(
                    "\r\n"
                )

                if line:
                    print(
                        line,
                        flush=True
                    )

        threading.Thread(
            target=read_card_output,
            daemon=True,
            name=f"snap-card-reader-{job['id']}"
        ).start()

        process.stdin.write(
            json.dumps(
                payload,
                ensure_ascii=False
            )
        )
        process.stdin.flush()
        process.stdin.close()

        return_code = process.wait(
            timeout=CARD_TIMEOUT
        )

        if return_code == 0:
            log(
                f"Job {job['id']} completed successfully.",
                "QUEUE"
            )
            return True

        log(
            f"Job {job['id']} failed. "
            f"Exit code={return_code}",
            "QUEUE"
        )

        return False

    except subprocess.TimeoutExpired:
        log(
            f"Job {job['id']} exceeded "
            f"{CARD_TIMEOUT}s.",
            "QUEUE"
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

        return False

    except Exception as e:
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

        except Exception as e:
            log(
                f"Critical Job error "
                f"{job.get('id')}: {e}",
                "QUEUE"
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
>>>>>>> Stashed changes
        return

    log("Selection lock acquired.", "OCR")

    ocr_running = True
<<<<<<< Updated upstream

    try:
        process_ocr()

    except Exception as e:

        print(
            f"\nОшибка: {e}\n"
        )

=======
    state = {"released": False}

    def release_selection():
        global ocr_running
        global toast_suppressed_for_selection
        global toast_notification_pending

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
            toast_notification_pending = False

        if notification_pending:
            show_card_added_notification()

    try:
        log("Calling process_ocr.", "OCR")
        process_ocr(hotkey_time, release_selection)
    except Exception as e:
        log(f"Critical OCR error: {e}", "OCR")
>>>>>>> Stashed changes
    finally:
        ocr_running = False


def start_ocr():
    threading.Thread(
        target=run_ocr,
        daemon=True
    ).start()


def mac_event_callback(
    proxy,
    event_type,
    event,
    refcon
):
    global hotkey_active

    if (
        event_type
        == Quartz.kCGEventTapDisabledByTimeout
    ):

        Quartz.CGEventTapEnable(
            refcon,
            True
        )

        return event

    refresh_hotkey_if_needed()

    if event_type not in (
        Quartz.kCGEventKeyDown,
        Quartz.kCGEventKeyUp
    ):
        return event

    keycode = Quartz.CGEventGetIntegerValueField(
        event,
        Quartz.kCGKeyboardEventKeycode
    )

    target_keycode = KEYCODES.get(
        hotkey_parts["key"]
    )

    if keycode != target_keycode:
        return event

    flags = Quartz.CGEventGetFlags(
        event
    )

    required_flags = get_modifier_flags(
        hotkey_parts["mods"]
    )

    modifiers_match = (
        flags & required_flags
    ) == required_flags

    if event_type == Quartz.kCGEventKeyDown:

        if modifiers_match:

<<<<<<< Updated upstream
            if not hotkey_active:
=======
            dismiss_card_added_notification(
                suppress_for_selection=True
            )

            start_ocr(
                pressed_at
            )
>>>>>>> Stashed changes

                hotkey_active = True

                start_ocr()

            return None

    if event_type == Quartz.kCGEventKeyUp:

        if hotkey_active:

            hotkey_active = False

            return None

    return event


def start_hotkey_listener():

    if Quartz is None:

        print(
            "Quartz недоступен. Глобальный хоткей не запущен."
        )

        return

    request_permissions()

    print(
        "Ожидание разрешений macOS..."
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

        print(
            "Не удалось создать Quartz Event Tap."
        )

        print(
            "Проверь Accessibility и Input Monitoring."
        )

        open_permission_settings()

        return

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

    print(
        "Quartz hotkey listener запущен."
    )

    Quartz.CFRunLoopRun()


<<<<<<< Updated upstream
def normalize_text(
    text
):
    return re.sub(
        r"[^\w\s]",
        "",
        text,
        flags=re.UNICODE
    ).lower().strip()


def load_image(
    path
):
=======

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
>>>>>>> Stashed changes
    if (
        Vision is None
        or Foundation is None
        or Quartz is None
    ):
        raise RuntimeError(
            "Apple Vision недоступен. "
            "Установи pyobjc-framework-Vision."
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
            f"Vision: не удалось открыть изображение: {path}"
        )

    image = Quartz.CGImageSourceCreateImageAtIndex(
        source,
        0,
        None
    )

    if image is None:
        raise RuntimeError(
            f"Vision: не удалось декодировать изображение: {path}"
        )

    return image


def run_vision_ocr(
    path,
    detail=False
):
    refresh_ocr_if_needed()

    languages = get_vision_languages(
        loaded_ocr_languages
    )

    use_language_correction = (
        get_ocr_correction_enabled()
    )

    image = load_image(
        path
    )

    request = Vision.VNRecognizeTextRequest.alloc().init()

    request.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelAccurate
    )

    request.setRecognitionLanguages_(
        languages
    )

    request.setUsesLanguageCorrection_(
        use_language_correction
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

    observations = request.results() or []

    image_width = Quartz.CGImageGetWidth(
        image
    )

    image_height = Quartz.CGImageGetHeight(
        image
    )

    output = []

    for observation in observations:

        candidates = (
            observation.topCandidates_(1)
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

            output.append(
                text
            )

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


def get_ocr_text(
    path
):
    results = run_vision_ocr(
        path,
        detail=False
    )

    return " ".join(
        result.strip()
        for result in results
        if str(result).strip()
    )


def get_ocr_boxes(
    path
):
    return run_vision_ocr(
        path,
        detail=True
    )


def deduplicate_boxes(
    boxes
):
    result = []

    for box in boxes:

        current_norm = normalize_text(
            box["text"]
        )

        if not current_norm:
            continue

        duplicate = False

        for i, existing in enumerate(
            result
        ):

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
            result.append(
                box
            )

    return result


<<<<<<< Updated upstream
=======

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



>>>>>>> Stashed changes
def find_word_on_screen(
    word_path,
    screen_path
):
    if (
        not os.path.exists(word_path)
        or not os.path.exists(screen_path)
    ):
        return None

    template = cv2.imread(
        word_path,
        cv2.IMREAD_GRAYSCALE
    )

    screen = cv2.imread(
        screen_path,
        cv2.IMREAD_GRAYSCALE
    )

    if (
        template is None
        or screen is None
    ):
        return None

    template_h, template_w = template.shape
    screen_h, screen_w = screen.shape

    if (
        template_w > screen_w
        or template_h > screen_h
    ):
        return None

    result = cv2.matchTemplate(
        screen,
        template,
        cv2.TM_CCOEFF_NORMED
    )

    _, max_value, _, max_location = cv2.minMaxLoc(
        result
    )

    if max_value < 0.70:

        best_value = max_value
        best_location = max_location
        best_size = (
            template_w,
            template_h
        )

        for scale in [
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

            resized = cv2.resize(
                template,
                (
                    new_w,
                    new_h
                ),
                interpolation=cv2.INTER_AREA
            )

            match = cv2.matchTemplate(
                screen,
                resized,
                cv2.TM_CCOEFF_NORMED
            )

            _, value, _, location = cv2.minMaxLoc(
                match
            )

            if value > best_value:

                best_value = value
                best_location = location
                best_size = (
                    new_w,
                    new_h
                )

        max_value = best_value
        max_location = best_location
        template_w, template_h = best_size

    if max_value < 0.55:
        return None

    return {
        "x": max_location[0],
        "y": max_location[1],
        "w": template_w,
        "h": template_h,
        "confidence": max_value
    }


def capture_full_screen():
    if os.path.exists(screen_path):

        try:
            os.remove(
                screen_path
            )

        except OSError:
            pass

    result = subprocess.run(
        [
            "screencapture",
            "-x",
            screen_path
        ],
        capture_output=True,
        text=True
    )

    return (
        result.returncode == 0
        and os.path.exists(screen_path)
    )


def create_context_image(
    screen_path,
    rect
):
    if not os.path.exists(
        screen_path
    ):
        return False

    try:
        image = Image.open(
            screen_path
        )

        screen_w, screen_h = image.size

        x = int(
            rect["x"]
        )

        y = int(
            rect["y"]
        )

        w = int(
            rect["w"]
        )

        h = int(
            rect["h"]
        )

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

        cropped = image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )

        cropped.save(
            shot2_path
        )

        return {
            "x": x - left,
            "y": y - top,
            "w": w,
            "h": h
        }

    except Exception as e:

        print(
            f"Ошибка создания контекста: {e}"
        )

        return False


<<<<<<< Updated upstream
def get_context_line(
    context_path,
    word_rect
):
    boxes = deduplicate_boxes(
        get_ocr_boxes(
            context_path
        )
    )

=======
def get_context_lines(context_path, word_rect):
    # Player timers are screen UI, not subtitle text. Filter them before grouping
    # boxes so they cannot be merged into the subtitle row at the same height.
    boxes = [
        box for box in deduplicate_boxes(get_ocr_boxes(context_path))
        if not is_timer_only_text(box.get("text", ""))
    ]
>>>>>>> Stashed changes
    if not boxes:
        return []

    boxes.sort(key=lambda box: (box["cy"], box["x1"]))
    groups = []

    for box in boxes:
<<<<<<< Updated upstream

        vertical_distance = abs(
            box["cy"]
            - word_center_y
        )
=======
        height = max(1.0, float(box.get("height", 1.0)))
        selected_group = None
        selected_distance = None
>>>>>>> Stashed changes

        for group in groups:
            center_y = sum(item["cy"] for item in group) / len(group)
            group_height = sum(max(1.0, float(item.get("height", 1.0))) for item in group) / len(group)
            tolerance = max(8.0, min(height, group_height) * 0.6)
            distance = abs(float(box["cy"]) - center_y)
            if distance <= tolerance and (selected_distance is None or distance < selected_distance):
                selected_group = group
                selected_distance = distance

<<<<<<< Updated upstream
        if (
            vertical_distance
            <= tolerance
        ):

            candidates.append(
                box
            )

    if not candidates:

        boxes_sorted = sorted(
            boxes,
            key=lambda b: abs(
                b["cy"]
                - word_center_y
            )
        )

        if boxes_sorted:

            closest = boxes_sorted[0]
=======
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
>>>>>>> Stashed changes


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
<<<<<<< Updated upstream

    if filtered:
        candidates = filtered

    candidates.sort(
        key=lambda b: (
            b["cy"],
            b["x1"]
        )
    )

    final_boxes = []
    seen = set()

    for box in candidates:

        norm = normalize_text(
            box["text"]
        )

        if (
            norm
            and norm not in seen
        ):

            seen.add(
                norm
            )

            final_boxes.append(
                box
            )

    return " ".join(
        box["text"].strip()
        for box in final_boxes
        if box["text"].strip()
    ).strip()


def get_fallback_context(
    context_path
):
    return get_ocr_text(
        context_path
    ).strip()
=======
    return " ".join(meaningful).strip()
>>>>>>> Stashed changes


def create_center_card_screenshot(
    screen_path,
    output_path
):
    if not os.path.exists(
        screen_path
    ):
        return False

    try:
        image = Image.open(
            screen_path
        )

        screen_w, screen_h = image.size

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
            screen_w - capture_w
        ) // 2

        top = (
            screen_h - capture_h
        ) // 2 - vertical_shift

        top = max(
            0,
            top
        )

        right = min(
            screen_w,
            left + capture_w
        )

        bottom = min(
            screen_h,
            top + capture_h
        )

        cropped = image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )

        if os.path.exists(
            output_path
        ):
            try:
                os.remove(
                    output_path
                )
            except OSError:
                pass

        cropped.save(
            output_path
        )

        print(
            f"Card screenshot: "
            f"x={left}, y={top}, "
            f"w={right - left}, "
            f"h={bottom - top}"
        )

        return True

    except Exception as e:
        print(
            f"Ошибка создания скрина карточки: {e}"
        )
        return False


<<<<<<< Updated upstream
def create_card(
    word,
    context,
    image_path
):
    card_path = os.path.join(
        current_dir,
        "card.py"
    )

    payload = {
        "word": word,
        "context": context,
        "image": image_path
    }

    try:

        result = subprocess.run(
            [
                sys.executable,
                card_path
            ],
            cwd=current_dir,
            input=json.dumps(
                payload,
                ensure_ascii=False
            ),
            text=True
        )

        return result.returncode == 0

    except Exception as e:

        print(
            f"Card creation error: {e}"
        )

        return False


def process_ocr():

    start_time = time.perf_counter()

    for path in (
        shot1_path,
        shot2_path,
        screen_path
    ):

        if os.path.exists(path):

            try:
                os.remove(
                    path
                )

            except OSError:
                pass

    selection_start = time.perf_counter()

    subprocess.run(
        [
            "screencapture",
            "-i",
            "-s",
            "-x",
            shot1_path
        ],
        capture_output=True,
        text=True
    )

    selection_time = (
        time.perf_counter()
        - selection_start
    )

    if not os.path.exists(
        shot1_path
    ):
        return

    print(
        f"Время выбора: {selection_time:.2f} сек."
    )

    screen_start = time.perf_counter()

    if not capture_full_screen():

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось получить screenshot экрана\n"
        )

        return

    print(
        f"Полный экран: {time.perf_counter() - screen_start:.2f} сек."
    )

    if create_center_card_screenshot(
        screen_path,
        card_screenshot_path
    ):

        print(
            f"СКРИН КАРТОЧКИ: {card_screenshot_path}"
        )

    else:

        print(
            "СКРИН КАРТОЧКИ: не удалось создать"
        )

    match_start = time.perf_counter()

    rect = find_word_on_screen(
        shot1_path,
        screen_path
    )

    print(
        f"Поиск слова на экране: {time.perf_counter() - match_start:.2f} сек."
    )

    if rect is None:

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось определить положение слова на экране\n"
        )

        return

    print(
        f"Позиция найдена: "
        f"x={rect['x']} "
        f"y={rect['y']} "
        f"w={rect['w']} "
        f"h={rect['h']} "
        f"match={rect['confidence']:.2f}"
    )

    context_start = time.perf_counter()

    local_rect = create_context_image(
        screen_path,
        rect
    )

    print(
        f"Создание контекста: {time.perf_counter() - context_start:.2f} сек."
    )
=======
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
>>>>>>> Stashed changes

    local_rect = create_context_image(screen_image, rect, context_path)
    if not local_rect:
<<<<<<< Updated upstream

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось создать область контекста\n"
        )

        return

    refresh_ocr_if_needed()

    ocr_start = time.perf_counter()

    word_text = get_ocr_text(
        shot1_path
    )

    print(
        f"Vision OCR слова: {time.perf_counter() - ocr_start:.2f} сек."
    )

    if not word_text:

        print(
            "\nНе удалось распознать выделенное слово.\n"
        )

        return

    print(
        f"\nСЛОВО: {word_text}"
    )

    context_ocr_start = time.perf_counter()

    context_text = get_context_line(
        shot2_path,
        local_rect
    )

    print(
        f"Vision OCR контекста: {time.perf_counter() - context_ocr_start:.2f} сек."
    )

    if not context_text:

        context_fallback_start = time.perf_counter()

        context_text = get_fallback_context(
            shot2_path
        )

        print(
            f"Vision OCR fallback: {time.perf_counter() - context_fallback_start:.2f} сек."
=======
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
>>>>>>> Stashed changes
        )

    if context_text:

        print(
            f"ПРЕДЛОЖЕНИЕ: {context_text}\n"
        )

        card_start = time.perf_counter()

<<<<<<< Updated upstream
        success = create_card(
            word_text,
            context_text,
            card_screenshot_path
=======
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

        word_text = trim_word_edges(
            get_ocr_text(word_path)
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
            return

        queued = create_card_job(
            word_text,
            context_text,
            card_image_path,
            hotkey_time,
            audio_interval,
            pending_subtitle,
            context_variants=context_variants
>>>>>>> Stashed changes
        )

        print(
            f"Создание карточки: {time.perf_counter() - card_start:.2f} сек."
        )

        if not success:
            print(
                "Карточка не была создана."
            )

    else:

        print(
            "ПРЕДЛОЖЕНИЕ: не найдено\n"
        )

    for path in (
        shot1_path,
        shot2_path,
        screen_path
    ):

        if os.path.exists(path):

            try:
                os.remove(
                    path
                )

            except OSError:
                pass

    print(
        f"Общее время обработки: {time.perf_counter() - start_time:.2f} сек."
    )


refresh_hotkey_if_needed()

if Vision is None:

    print(
        "КРИТИЧЕСКАЯ ОШИБКА: Apple Vision недоступен."
    )

    print(
        "Установи pyobjc-framework-Vision."
    )

else:

    print(
        "Apple Vision OCR активен."
    )

print(
    f"\nSnap запущен. "
    f"Выделите слово и нажмите {hotkey_string}."
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
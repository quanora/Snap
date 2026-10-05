import os
import subprocess
import re
import difflib
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
    from aqt import mw
    from aqt.qt import QFrame, QLabel, QHBoxLayout, QTimer, Qt
except ImportError:
    mw = None
    QFrame = None
    QLabel = None
    QHBoxLayout = None
    QTimer = None
    Qt = None

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


ALL_LANGUAGE_CODES = {
    "en", "de", "ru", "es", "fr", "it", "pt", "ch_sim", "ch_tra",
    "ja", "ko", "nl", "pl", "cs", "hu", "ro", "sv", "da", "no",
    "fi", "tr", "uk", "el", "he", "ar"
}

VISION_LANGUAGE_CODES = {
    "en": "en", "de": "de", "ru": "ru", "es": "es", "fr": "fr",
    "it": "it", "pt": "pt", "ch_sim": "zh-Hans", "ch_tra": "zh-Hant",
    "ja": "ja", "ko": "ko", "nl": "nl", "pl": "pl", "cs": "cs",
    "hu": "hu", "ro": "ro", "sv": "sv", "da": "da", "no": "no",
    "fi": "fi", "tr": "tr", "uk": "uk", "el": "el", "he": "he",
    "ar": "ar"
}

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


def show_card_added_notification():
    if mw is None or QFrame is None or QLabel is None or QHBoxLayout is None or QTimer is None or Qt is None:
        log("Card added notification unavailable: Qt/mw import failed.", "UI")
        return

    def show():
        try:
            log("Showing Card added notification.", "UI")

            old_toast = getattr(mw, "_snap_card_toast", None)

            if old_toast is not None:
                try:
                    old_toast.deleteLater()
                except Exception:
                    pass

            toast = QFrame(mw)
            toast.setObjectName("snapCardToast")
            toast.setFixedSize(180, 44)
            toast.setStyleSheet("""
                QFrame#snapCardToast {
                    background-color: rgba(35, 35, 35, 235);
                    border-radius: 22px;
                }
                QLabel {
                    color: white;
                    font-size: 14px;
                    font-weight: 500;
                    background: transparent;
                }
            """)

            layout = QHBoxLayout(toast)
            layout.setContentsMargins(16, 0, 16, 0)

            label = QLabel("Card added", toast)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

            x = (mw.width() - toast.width()) // 2
            y = int(mw.height() * 0.64)

            toast.move(x, y)
            mw._snap_card_toast = toast

            toast.show()
            toast.raise_()

            log(f"Card added notification shown at x={x}, y={y}.", "UI")

            def remove():
                try:
                    if getattr(mw, "_snap_card_toast", None) is toast:
                        mw._snap_card_toast = None
                    toast.deleteLater()
                except Exception:
                    pass

            QTimer.singleShot(1800, remove)

        except Exception as e:
            log(f"Could not show Card added notification: {e}", "UI")

    try:
        mw.taskman.run_on_main(show)
        log("Card added notification scheduled on main thread.", "UI")
    except Exception as e:
        log(f"Could not schedule Card added notification: {e}", "UI")


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


def load_ocr_languages():
    languages = load_settings_data().get("ocr_languages", ["en"])

    if not isinstance(languages, list):
        log("Invalid ocr_languages format. Using ['en'].", "OCR")
        return ["en"]

    result = []

    for language in languages:
        if not isinstance(language, str):
            continue

        language = language.strip()

        if language not in ALL_LANGUAGE_CODES:
            log(f"Unknown OCR language ignored: {language}", "OCR")
            continue

        if language not in result:
            result.append(language)

    return result[:3] or ["en"]


def get_ocr_correction_enabled():
    value = load_settings_data().get("ocr_correction", True)

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_vision_languages(languages):
    result = []

    for language in languages:
        vision_code = VISION_LANGUAGE_CODES.get(language)

        if vision_code and vision_code not in result:
            result.append(vision_code)

    return result or ["en"]


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
            open_audio_permission_settings()

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
        launcher=subprocess.Popen(["/usr/bin/open","-n",screen_bundle_path,"--args","--socket",screen_socket_path,"--parent-pid",str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
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
    pending_subtitle=None
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

    if not ocr_selection_lock.acquire(
        blocking=False
    ):
        log(
            "Selection is already in progress.",
            "OCR"
        )
        return

    ocr_running = True
    state = {"released": False}

    def release_selection():
        global ocr_running

        if state["released"]:
            return

        state["released"] = True
        ocr_running = False

        ocr_selection_lock.release()

    try:
        process_ocr(
            hotkey_time,
            release_selection
        )

    except Exception as e:
        log(
            f"Critical OCR error: {e}",
            "OCR"
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
    return re.sub(
        r"[^\w\s]",
        "",
        text,
        flags=re.UNICODE
    ).lower().strip()


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

    languages = get_vision_languages(
        loaded_ocr_languages
    )

    use_language_correction = (
        get_ocr_correction_enabled()
    )

    image = load_image(path)

    request = (
        Vision.VNRecognizeTextRequest
        .alloc()
        .init()
    )

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


def word_in_text(
    word,
    text
):
    word_norm = normalize_text(
        word
    )

    text_norm = normalize_text(
        text
    )

    if not word_norm or not text_norm:
        return False

    if word_norm in text_norm:
        return True

    text_tokens = text_norm.split()

    for token in word_norm.split():
        if token in text_tokens:
            continue

        if difflib.get_close_matches(
            token,
            text_tokens,
            n=1,
            cutoff=0.8
        ):
            continue

        return False

    return True


def remember_subtitle(ref):
    if not ref or not ref.get("text"):
        return

    try:
        norm = normalize_text(ref.get("text", ""))
        start = float(ref.get("startWallTime", 0.0))
        end = float(ref.get("endWallTime", 0.0))
    except Exception:
        return

    if not norm or start <= 0:
        return

    now = time.time()

    with recent_subtitles_lock:
        recent_subtitles[:] = [
            item
            for item in recent_subtitles
            if now - item["saved_at"] <= 180.0
        ]

        for item in recent_subtitles:
            if item["norm"] == norm and abs(item["start"] - start) < 0.5:
                item["start"] = start
                item["end"] = end
                item["saved_at"] = now
                break
        else:
            recent_subtitles.append({
                "norm": norm,
                "start": start,
                "end": end,
                "saved_at": now
            })

        recent_subtitles.sort(
            key=lambda item: item["saved_at"],
            reverse=True
        )
        del recent_subtitles[20:]


def lookup_cached_subtitle(word):
    now = time.time()

    with recent_subtitles_lock:
        recent_subtitles[:] = [
            item
            for item in recent_subtitles
            if now - item["saved_at"] <= 180.0
        ]

        for item in recent_subtitles:
            if now - item["saved_at"] > 120.0:
                continue

            if not word_in_text(word, item["norm"]):
                continue

            return {
                "text": item["norm"],
                "startWallTime": item["start"],
                "endWallTime": item["end"]
            }

    return None


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


def get_context_line(
    context_path,
    word_rect
):
    boxes = deduplicate_boxes(
        get_ocr_boxes(context_path)
    )

    if not boxes:
        return ""

    word_center_y = (
        word_rect["y"]
        + word_rect["h"] / 2
    )

    word_center_x = (
        word_rect["x"]
        + word_rect["w"] / 2
    )

    candidates = []

    for box in boxes:
        vertical_distance = abs(
            box["cy"]
            - word_center_y
        )

        tolerance = max(
            20,
            word_rect["h"] * 1.5,
            box["height"] * 1.5
        )

        if vertical_distance <= tolerance:
            candidates.append(box)

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

            tolerance = max(
                25,
                closest["height"] * 1.5
            )

            candidates = [
                b
                for b in boxes
                if abs(
                    b["cy"]
                    - closest["cy"]
                ) <= tolerance
            ]

    if not candidates:
        return ""

    horizontal_limit = max(
        1000,
        word_rect["w"] * 6
    )

    filtered = [
        box
        for box in candidates
        if abs(
            box["cx"]
            - word_center_x
        ) <= horizontal_limit
    ]

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

        if norm and norm not in seen:
            seen.add(norm)
            final_boxes.append(box)

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


def find_context_from_screen(
    word_path,
    context_path,
    hotkey_image
):
    rect = None
    screen_image = None

    if hotkey_image is not None:
        rect = find_word_on_screen(
            word_path,
            hotkey_image
        )

        if rect is not None:
            screen_image = hotkey_image

    if rect is None:
        fresh = grab_screen_image(
            allow_fallback=True
        )

        if fresh is not None:
            rect = find_word_on_screen(
                word_path,
                fresh
            )

            if rect is not None:
                screen_image = fresh

    if rect is None:
        log(
            "Could not locate selected word on screen.",
            "OCR"
        )
        return ""

    log(
        f"Position: "
        f"x={rect['x']} "
        f"y={rect['y']} "
        f"w={rect['w']} "
        f"h={rect['h']} "
        f"match={rect['confidence']:.2f}",
        "OCR"
    )

    local_rect = create_context_image(
        screen_image,
        rect,
        context_path
    )

    if not local_rect:
        log(
            "Context image could not be created.",
            "OCR"
        )
        return ""

    context_text = get_context_line(
        context_path,
        local_rect
    )

    if not context_text:
        context_text = get_fallback_context(
            context_path
        )

    return context_text.strip()



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

        word_text = get_ocr_text(
            word_path
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

        candidates = []

        for candidate in [
            hotkey_reference,
            second
        ]:
            if (
                candidate
                and candidate.get("text")
            ):
                if not any(
                    same_subtitle_text(
                        candidate,
                        existing
                    )
                    for existing in candidates
                ):
                    candidates.append(
                        candidate
                    )

        if (
            current
            and current.get("text")
        ):
            if not any(
                same_subtitle_text(
                    current,
                    existing
                )
                for existing in candidates
            ):
                candidates.append(
                    current
                )

        reference = None

        for candidate in candidates:
            if word_in_text(
                word_text,
                candidate["text"]
            ):
                reference = candidate
                break

        if reference is None and candidates:
            reference = candidates[0]

        if (
            reference
            and reference.get("text")
            and word_in_text(
                word_text,
                reference["text"]
            )
        ):
            remember_subtitle(reference)
        else:
            cached_reference = lookup_cached_subtitle(word_text)
            if cached_reference is not None:
                reference = cached_reference
                log(
                    "Subtitle recovered from recent cache = "
                    f"{reference['text']}",
                    "SCREEN"
                )

        context_text = ""
        audio_interval = None
        pending_subtitle = None

        if (
            reference
            and reference.get("text")
        ):
            subtitle_text = (
                reference["text"]
                .strip()
            )

            if word_in_text(
                word_text,
                subtitle_text
            ):
                context_text = subtitle_text

                log(
                    "CONTEXT from "
                    "subtitle history = "
                    f"{context_text}",
                    "OCR"
                )

                if subtitle_is_closed(
                    reference,
                    current
                ):
                    audio_interval = (
                        subtitle_interval(
                            reference
                        )
                    )

                    if audio_interval:
                        log(
                            "Subtitle interval "
                            "is closed. "
                            "Using it for audio.",
                            "SCREEN"
                        )

                else:
                    pending_subtitle = reference

                    log(
                        "Subtitle is still on screen. "
                        "Waiting up to "
                        f"{INTERVAL_CLOSE_TIMEOUT:.0f}s "
                        "for it to close.",
                        "SCREEN"
                    )

            else:
                log(
                    "Selected word is not part "
                    "of the subtitle. "
                    "Using on-screen context.",
                    "SCREEN"
                )

        else:
            log(
                "No historical subtitle found.",
                "SCREEN"
            )

        if not context_text:
            context_start = time.perf_counter()

            context_text = find_context_from_screen(
                word_path,
                context_path,
                hotkey_image
            )

            log(
                f"On-screen context took "
                f"{time.perf_counter() - context_start:.2f}s.",
                "OCR"
            )

        if not context_text:
            log(
                "Context was not recognized.",
                "OCR"
            )

            play_error_sound()
            return

        log(
            f"CONTEXT = {context_text}",
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
            pending_subtitle
        )

        if not queued:
            log(
                "Failed to create card job.",
                "QUEUE"
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

start_ocr_preloader()
start_hotkey_listener()

import os
import subprocess
import warnings
import re
import cv2
from PIL import Image
import json
import sys
import threading
import time

try:
    import Quartz
except ImportError:
    Quartz = None

try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt
    )
except ImportError:
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None


warnings.filterwarnings(
    "ignore",
    category=UserWarning
)


current_dir = os.path.dirname(
    os.path.abspath(__file__)
)

settings_path = os.path.join(
    current_dir,
    "settings.json"
)

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

card_screenshot_path = os.path.join(
    current_dir,
    "card_screenshot.png"
)


ALL_LANGUAGE_CODES = {
    "en", "de", "ru", "es", "fr", "it", "pt",
    "ch_sim", "ch_tra", "ja", "ko",
    "nl", "pl", "cs", "hu", "ro",
    "sv", "da", "no", "fi", "tr",
    "uk", "el", "he", "ar"
}


LATIN_LANGUAGES = {
    "en", "de", "es", "fr", "it", "pt",
    "nl", "pl", "cs", "hu", "ro",
    "sv", "da", "no", "fi", "tr"
}


SEPARATE_LANGUAGES = {
    "ru", "uk", "ch_sim", "ch_tra",
    "ja", "ko", "el", "he", "ar"
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


readers = []
loaded_ocr_languages = []
settings_mtime = None

readers_lock = threading.Lock()

hotkey_mtime = None
hotkey_string = "cmd+shift+a"
hotkey_parts = {
    "mods": {"cmd", "shift"},
    "key": "a"
}

hotkey_active = False
ocr_running = False


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


def load_ocr_languages():
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

    result = []

    for language in languages:

        if not isinstance(
            language,
            str
        ):
            continue

        if language not in ALL_LANGUAGE_CODES:

            print(
                f"Неизвестный OCR язык пропущен: "
                f"{language}"
            )

            continue

        if language not in result:
            result.append(
                language
            )

    return result[:3] or ["en"]


def create_readers(
    languages
):
    import easyocr

    new_readers = []

    latin_languages = [
        language
        for language in languages
        if language in LATIN_LANGUAGES
    ]

    if latin_languages:

        try:
            print(
                f"Загрузка OCR модели: "
                f"{latin_languages}"
            )

            new_readers.append(
                easyocr.Reader(
                    latin_languages,
                    quantize=False,
                    gpu=False
                )
            )

        except Exception as e:

            print(
                f"Не удалось загрузить совместную "
                f"Latin-модель "
                f"{latin_languages}: {e}"
            )

            for language in latin_languages:

                try:
                    print(
                        f"Загрузка OCR модели отдельно: "
                        f"{language}"
                    )

                    new_readers.append(
                        easyocr.Reader(
                            [language],
                            quantize=False,
                            gpu=False
                        )
                    )

                except Exception as e:

                    print(
                        f"Не удалось загрузить "
                        f"{language}: {e}"
                    )

    for language in languages:

        if language not in SEPARATE_LANGUAGES:
            continue

        try:
            print(
                f"Загрузка OCR модели: "
                f"{language}"
            )

            new_readers.append(
                easyocr.Reader(
                    [language],
                    quantize=False,
                    gpu=False
                )
            )

        except Exception as e:

            print(
                f"Не удалось загрузить "
                f"{language}: {e}"
            )

    if not new_readers:

        print(
            "Не удалось загрузить выбранные модели. "
            "Используется English."
        )

        try:
            new_readers.append(
                easyocr.Reader(
                    ["en"],
                    quantize=False,
                    gpu=False
                )
            )

        except Exception as e:

            print(
                f"Критическая ошибка загрузки "
                f"EasyOCR: {e}"
            )

    return new_readers


def refresh_readers_if_needed():
    global readers
    global loaded_ocr_languages
    global settings_mtime

    with readers_lock:

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
            and readers
        ):
            return

        if languages != loaded_ocr_languages:

            print(
                f"\nOCR языки изменились: "
                f"{loaded_ocr_languages} → "
                f"{languages}"
            )

        print(
            "EasyOCR ещё не загружен. "
            "Начинается загрузка моделей..."
        )

        start_time = time.perf_counter()

        readers = create_readers(
            languages
        )

        loaded_ocr_languages = languages
        settings_mtime = current_mtime

        elapsed = (
            time.perf_counter()
            - start_time
        )

        print(
            f"OCR языки активны: "
            f"{loaded_ocr_languages}"
        )

        print(
            f"EasyOCR загружен за "
            f"{elapsed:.2f} сек."
        )


def preload_ocr():
    time.sleep(3)

    if ocr_running:
        return

    try:
        print(
            "Отложенная загрузка EasyOCR..."
        )

        refresh_readers_if_needed()

    except Exception as e:

        print(
            f"Ошибка фоновой загрузки EasyOCR: "
            f"{e}"
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
        f"Горячая клавиша активна: "
        f"{hotkey_string}"
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
            f"Не удалось открыть настройки "
            f"разрешений: {e}"
        )


def request_permissions():
    if Quartz is None:
        return False

    accessibility_ok = True
    input_monitoring_ok = True

    if (
        AXIsProcessTrustedWithOptions
        is not None
    ):

        try:

            accessibility_ok = bool(
                AXIsProcessTrustedWithOptions({
                    kAXTrustedCheckOptionPrompt: True
                })
            )

        except Exception as e:

            print(
                f"Ошибка проверки Accessibility: "
                f"{e}"
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
                f"Ошибка проверки Input Monitoring: "
                f"{e}"
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
                f"Ошибка запроса Input Monitoring: "
                f"{e}"
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
        "Требуются разрешения macOS "
        "для глобального хоткея."
    )

    open_permission_settings()

    return False


def run_ocr():
    global ocr_running

    if ocr_running:
        return

    ocr_running = True

    try:

        process_ocr()

    except Exception as e:

        print(
            f"\nОшибка: {e}\n"
        )

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

            if not hotkey_active:

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
            "Quartz недоступен. "
            "Глобальный хоткей не запущен."
        )

        return

    request_permissions()

    print(
        "Ожидание разрешений macOS..."
    )

    for _ in range(30):

        try:

            accessibility_ok = True

            if (
                AXIsProcessTrustedWithOptions
                is not None
            ):

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
            "Проверь Accessibility и "
            "Input Monitoring для процесса, "
            "который запускает ocr.py."
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


def normalize_text(
    text
):
    return re.sub(
        r"[^\w\s]",
        "",
        text,
        flags=re.UNICODE
    ).lower().strip()


def get_ocr_text(
    path
):
    if not os.path.exists(path):
        return ""

    combined = []

    for reader in readers:

        try:

            results = reader.readtext(
                path,
                detail=0
            )

        except Exception as e:

            print(
                f"OCR error: {e}"
            )

            continue

        for line in results:

            cleaned = line.strip()

            if not cleaned:
                continue

            norm = normalize_text(
                cleaned
            )

            if not norm:
                continue

            duplicate = False

            for i, existing in enumerate(
                combined
            ):

                existing_norm = normalize_text(
                    existing
                )

                if (
                    norm in existing_norm
                    or existing_norm in norm
                ):

                    duplicate = True

                    if (
                        len(cleaned)
                        > len(existing)
                    ):

                        combined[i] = cleaned

                    break

            if not duplicate:
                combined.append(
                    cleaned
                )

    return " ".join(
        combined
    )


def get_ocr_boxes(
    path
):
    if not os.path.exists(path):
        return []

    all_results = []

    for reader in readers:

        try:

            results = reader.readtext(
                path,
                detail=1
            )

        except Exception as e:

            print(
                f"OCR error: {e}"
            )

            continue

        for result in results:

            if len(result) != 3:
                continue

            box, text, confidence = result

            text = text.strip()

            if not text:
                continue

            try:

                confidence = float(
                    confidence
                )

            except Exception:

                confidence = 0.0

            xs = [
                point[0]
                for point in box
            ]

            ys = [
                point[1]
                for point in box
            ]

            x1 = min(xs)
            x2 = max(xs)
            y1 = min(ys)
            y2 = max(ys)

            all_results.append({
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

    return all_results


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
        padding_y = 180

        left = max(
            0,
            x - padding_x
        )

        top = max(
            0,
            y - padding_y
        )

        right = min(
            screen_w,
            x + w + padding_x
        )

        bottom = min(
            screen_h,
            y + h + padding_y
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
            f"Ошибка создания контекста: "
            f"{e}"
        )

        return False


def get_context_line(
    context_path,
    word_rect
):
    boxes = deduplicate_boxes(
        get_ocr_boxes(
            context_path
        )
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

        capture_w = min(
            2000,
            screen_w
        )

        capture_h = min(
            1200,
            screen_h
        )

        left = (
            screen_w
            - capture_w
        ) // 2

        top = (
            screen_h
            - capture_h
        ) // 2

        cropped = image.crop(
            (
                left,
                top,
                left + capture_w,
                top + capture_h
            )
        )

        cropped.save(
            output_path
        )

        return True

    except Exception as e:

        print(
            f"Ошибка создания скрина карточки: "
            f"{e}"
        )

        return False


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
        f"Время выбора: "
        f"{selection_time:.2f} сек."
    )

    screen_start = time.perf_counter()

    if not capture_full_screen():

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось "
            "получить screenshot экрана\n"
        )

        return

    print(
        f"Полный экран: "
        f"{time.perf_counter() - screen_start:.2f} сек."
    )

    if create_center_card_screenshot(
        screen_path,
        card_screenshot_path
    ):

        print(
            f"СКРИН КАРТОЧКИ: "
            f"{card_screenshot_path}"
        )

    else:

        print(
            "СКРИН КАРТОЧКИ: "
            "не удалось создать"
        )

    match_start = time.perf_counter()

    rect = find_word_on_screen(
        shot1_path,
        screen_path
    )

    print(
        f"Поиск слова на экране: "
        f"{time.perf_counter() - match_start:.2f} сек."
    )

    if rect is None:

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось "
            "определить положение слова "
            "на экране\n"
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
        f"Создание контекста: "
        f"{time.perf_counter() - context_start:.2f} сек."
    )

    if not local_rect:

        print(
            "ПРЕДЛОЖЕНИЕ: не удалось "
            "создать область контекста\n"
        )

        return

    ocr_start = time.perf_counter()

    refresh_readers_if_needed()

    word_text = get_ocr_text(
        shot1_path
    )

    print(
        f"OCR слова: "
        f"{time.perf_counter() - ocr_start:.2f} сек."
    )

    if not word_text:

        print(
            "\nНе удалось распознать "
            "выделенное слово.\n"
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
        f"OCR контекста: "
        f"{time.perf_counter() - context_ocr_start:.2f} сек."
    )

    if not context_text:

        context_fallback_start = time.perf_counter()

        context_text = get_fallback_context(
            shot2_path
        )

        print(
            f"OCR fallback: "
            f"{time.perf_counter() - context_fallback_start:.2f} сек."
        )

    if context_text:

        print(
            f"ПРЕДЛОЖЕНИЕ: "
            f"{context_text}\n"
        )

        card_start = time.perf_counter()

        success = create_card(
            word_text,
            context_text,
            card_screenshot_path
        )

        print(
            f"Создание карточки: "
            f"{time.perf_counter() - card_start:.2f} сек."
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
        f"Общее время обработки: "
        f"{time.perf_counter() - start_time:.2f} сек."
    )


refresh_hotkey_if_needed()

print(
    f"\nSnap запущен. "
    f"EasyOCR будет загружен в фоне. "
    f"Выделите слово и нажмите "
    f"{hotkey_string}."
)

start_ocr_preloader()

start_hotkey_listener()
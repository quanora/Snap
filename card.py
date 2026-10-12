import os
import sys
import json
import uuid
import subprocess
import urllib.request
import urllib.error
import re
import difflib
import unicodedata

from openai import OpenAI
from main import DEFAULT_PROMPT


ANKI_URL = "http://127.0.0.1:8765"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SETTINGS_PATH = os.path.join(
    BASE_DIR,
    "settings.json"
)

ERROR_SOUND = "/System/Library/Sounds/Sosumi.aiff"
AFPLAY = "/usr/bin/afplay"

PROMPT_VERSION = 1

ALLOWED_TAGS = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "determiner",
    "preposition",
    "conjunction",
    "interjection",
    "auxiliary",
    "modal",
    "particle",
    "numeral",
    "proper_noun",
    "phrase",
    "idiom",
    "abbreviation"
}


def play_error_sound():
    if not os.path.exists(
        ERROR_SOUND
    ):
        return

    try:
        subprocess.Popen(
            [
                AFPLAY,
                ERROR_SOUND
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    except Exception as e:
        print(
            f"Card: sound error = {e}"
        )


def field_on(settings, field_id):
    if field_id == "Front":
        return True
    enabled = settings.get("field_enabled")
    if not isinstance(enabled, dict):
        return True
    return enabled.get(field_id, True) is not False


def split_tags(value):
    return [t for t in re.split(r"[,\s]+", str(value or "")) if t]


def load_settings():
    if not os.path.exists(
        SETTINGS_PATH
    ):
        raise RuntimeError(
            "settings.json not found"
        )

    try:
        with open(
            SETTINGS_PATH,
            "r",
            encoding="utf-8"
        ) as file:
            settings = json.load(
                file
            )

    except Exception as e:
        raise RuntimeError(
            f"Could not load settings.json: {e}"
        )

    if not isinstance(
        settings,
        dict
    ):
        raise RuntimeError(
            "Invalid settings.json"
        )

    # Do not overwrite a custom prompt just because main.py does not store
    # prompt_version. The previous migration reset the user's prompt on every
    # card-generation process. Only use the default when no usable prompt exists.
    if not isinstance(settings.get("prompt"), str) or not settings["prompt"].strip():
        settings["prompt"] = DEFAULT_PROMPT

    # Kept in memory for compatibility with future prompt migrations. This value
    # is intentionally not used as a reason to replace a user-authored prompt.
    settings["prompt_version"] = PROMPT_VERSION

    return settings


def load_job_settings(payload):
    snapshot = payload.get(
        "settings_snapshot"
    )

    if isinstance(
        snapshot,
        dict
    ):
        print(
            "Card: using settings snapshot from queue"
        )

        return snapshot

    print(
        "Card: no settings snapshot in job, "
        "using current settings.json"
    )

    return load_settings()


def call_anki(action, params=None):
    payload = {
        "action": action,
        "version": 6,
        "params": params or {}
    }

    request = urllib.request.Request(
        ANKI_URL,
        data=json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":")
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            body = str(e)

        raise RuntimeError(
            f"AnkiConnect HTTP error "
            f"{e.code}: {body}"
        )

    except urllib.error.URLError as e:
        raise RuntimeError(
            f"AnkiConnect connection error: "
            f"{e.reason}"
        )

    except Exception as e:
        raise RuntimeError(
            f"AnkiConnect error: {e}"
        )

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            "Invalid response from AnkiConnect"
        )

    if data.get(
        "error"
    ):
        raise RuntimeError(
            str(
                data["error"]
            )
        )

    return data.get(
        "result"
    )


def get_llm_base_url(settings):
    url = str(
        settings.get(
            "llm_url",
            ""
        )
    ).strip().rstrip("/")

    if not url:
        raise RuntimeError(
            "Setting 'llm_url' is empty"
        )

    if url.endswith(
        "/v1"
    ):
        return url[:-3].rstrip("/")

    return url


def get_llm_client(settings):
    return OpenAI(
        base_url=(
            get_llm_base_url(
                settings
            )
            + "/v1"
        ),
        api_key="lm-studio",
        timeout=90
    )


def get_model(settings):
    configured_model = str(
        settings.get(
            "llm_model",
            ""
        )
    ).strip()

    if configured_model:
        print(
            f"Card: configured model = "
            f"{configured_model}"
        )

        return configured_model

    api_url = (
        get_llm_base_url(
            settings
        )
        + "/api/v1/models"
    )

    request = urllib.request.Request(
        api_url
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except Exception as e:
        raise RuntimeError(
            f"Could not read LM Studio models: {e}"
        )

    models = data.get(
        "models",
        []
    )

    for model in models:
        if model.get(
            "type"
        ) != "llm":
            continue

        if model.get(
            "loaded_instances"
        ):
            model_key = model.get(
                "key"
            )

            if not model_key:
                raise RuntimeError(
                    "Loaded LM Studio model has no key"
                )

            print(
                f"Card: running model = "
                f"{model_key}"
            )

            return model_key

    raise RuntimeError(
        "No LM Studio LLM is currently loaded"
    )


def get_language_profiles(settings):
    raw_profiles = settings.get(
        "language_profiles"
    )

    profiles = {}

    if isinstance(
        raw_profiles,
        dict
    ):
        for language, profile in raw_profiles.items():
            language = str(
                language
            ).strip()

            if not language:
                continue

            if not isinstance(
                profile,
                dict
            ):
                continue

            translation_language = str(
                profile.get(
                    "translation_language",
                    ""
                )
            ).strip()

            deck = str(
                profile.get(
                    "deck",
                    ""
                )
            ).strip()

            if (
                not translation_language
                or not deck
            ):
                continue

            profiles[language] = {
                "translation_language": translation_language,
                "deck": deck
            }

    if profiles:
        return profiles

    legacy_language = str(
        settings.get(
            "language",
            ""
        )
    ).strip()

    legacy_translation = str(
        settings.get(
            "translation_language",
            ""
        )
    ).strip()

    legacy_deck = str(
        settings.get(
            "deck",
            ""
        )
    ).strip()

    if (
        legacy_language
        and legacy_translation
        and legacy_deck
    ):
        profiles[legacy_language] = {
            "translation_language": legacy_translation,
            "deck": legacy_deck
        }

    if not profiles:
        raise RuntimeError(
            "No valid language profiles configured"
        )

    return profiles


def apply_job_profile(settings, payload):
    """Apply the language profile selected from this OCR job, if provided."""
    profile_name = str(
        payload.get("language_profile") or payload.get("language") or ""
    ).strip()
    if not profile_name:
        return settings, None

    profiles = get_language_profiles(settings)
    selected_name = find_profile(profiles, profile_name)
    if not selected_name:
        print(
            f"Card: job language profile '{profile_name}' is not configured; "
            "falling back to normal profile detection"
        )
        return settings, None

    selected = dict(profiles[selected_name])
    translation_override = str(payload.get("translation_language") or "").strip()
    deck_override = str(payload.get("deck") or "").strip()
    if translation_override:
        selected["translation_language"] = translation_override
    if deck_override:
        selected["deck"] = deck_override

    effective = dict(settings)
    effective["language"] = selected_name
    effective["translation_language"] = selected["translation_language"]
    effective["deck"] = selected["deck"]
    effective_profiles = dict(settings.get("language_profiles", {})) if isinstance(settings.get("language_profiles"), dict) else {}
    effective_profiles[selected_name] = selected
    effective["language_profiles"] = effective_profiles

    print(
        f"Card: using OCR-selected profile = {selected_name}; "
        f"translation={selected['translation_language']}; deck={selected['deck']}"
    )
    return effective, selected_name


def find_profile(profiles, language):
    language = str(
        language or ""
    ).strip()

    for profile_language in profiles:
        if (
            profile_language.casefold()
            == language.casefold()
        ):
            return profile_language

    return None


def get_profile_translation(profiles, language):
    profile_language = find_profile(
        profiles,
        language
    )

    if not profile_language:
        raise RuntimeError(
            f"Language profile not found: "
            f"{language}"
        )

    translation_language = str(
        profiles[
            profile_language
        ].get(
            "translation_language",
            ""
        )
    ).strip()

    if not translation_language:
        raise RuntimeError(
            f"Translation language is empty "
            f"for profile '{profile_language}'"
        )

    return translation_language


def extract_json(text):
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(
            text
        )
    except json.JSONDecodeError:
        pass

    if text.startswith(
        "```"
    ):
        lines = text.splitlines()

        if (
            lines
            and lines[0].startswith("```")
        ):
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        text = "\n".join(
            lines
        ).strip()

        try:
            return json.loads(
                text
            )
        except json.JSONDecodeError:
            pass

    start = text.find(
        "{"
    )

    end = text.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        return None

    try:
        return json.loads(
            text[
                start:
                end + 1
            ]
        )
    except json.JSONDecodeError:
        return None


def llm_chat(
    client,
    model,
    system_prompt,
    user_content,
    max_tokens,
    response_schema,
    schema_name
):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            stream=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema
                }
            }
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if content:
            return content

        raise RuntimeError(
            "LLM returned an empty response"
        )

    except Exception as structured_error:
        print(
            "Card: structured output failed = "
            f"{structured_error}"
        )

        print(
            "Card: retrying with JSON mode"
        )

    fallback_prompt = (
        system_prompt
        + "\n\n"
        "Return exactly one JSON object and nothing else."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": fallback_prompt
            },
            {
                "role": "user",
                "content": user_content
            }
        ],
        temperature=0,
        max_tokens=max_tokens,
        stream=False,
        response_format={
            "type": "json_object"
        }
    )

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:
        raise RuntimeError(
            "LLM returned an empty response"
        )

    return content


def detect_by_unicode(text, profiles):
    if not text:
        return None

    available = {
        language.casefold(): language
        for language in profiles
    }

    japanese = (
        "\u3040" <= char <= "\u30ff"
        or "\u31f0" <= char <= "\u31ff"
        for char in text
    )

    if any(japanese):
        if "japanese" in available:
            return available["japanese"]

    korean = (
        "\uac00" <= char <= "\ud7af"
        or "\u1100" <= char <= "\u11ff"
        for char in text
    )

    if any(korean):
        if "korean" in available:
            return available["korean"]

    cyrillic_count = sum(
        1
        for char in text
        if "\u0400" <= char <= "\u04ff"
    )

    if cyrillic_count:
        has_ukrainian = any(
            char.lower() in {
                "ї",
                "і",
                "є",
                "ґ"
            }
            for char in text
        )

        if (
            has_ukrainian
            and "ukrainian" in available
        ):
            return available["ukrainian"]

        if "russian" in available:
            return available["russian"]

        if "ukrainian" in available:
            return available["ukrainian"]

    greek_count = sum(
        1
        for char in text
        if "\u0370" <= char <= "\u03ff"
    )

    if greek_count:
        if "greek" in available:
            return available["greek"]

    hebrew_count = sum(
        1
        for char in text
        if "\u0590" <= char <= "\u05ff"
    )

    if hebrew_count:
        if "hebrew" in available:
            return available["hebrew"]

    arabic_count = sum(
        1
        for char in text
        if "\u0600" <= char <= "\u06ff"
    )

    if arabic_count:
        if "arabic" in available:
            return available["arabic"]

    han_count = sum(
        1
        for char in text
        if "\u3400" <= char <= "\u9fff"
    )

    if han_count:
        if "chinese (simplified)" in available:
            return available["chinese (simplified)"]

        if "chinese (traditional)" in available:
            return available["chinese (traditional)"]

    return None


def build_detection_schema(profiles):
    languages = list(
        profiles.keys()
    )

    return {
        "type": "object",
        "properties": {
            "detected_language": {
                "type": "string",
                "enum": languages
            }
        },
        "required": [
            "detected_language"
        ],
        "additionalProperties": False
    }


def detect_source_language(
    client,
    model,
    word,
    context,
    profiles
):
    if len(
        profiles
    ) == 1:
        language = next(
            iter(
                profiles
            )
        )

        print(
            f"Card: only profile available = "
            f"{language}"
        )

        return language

    combined_text = (
        word
        + "\n"
        + context
    )

    unicode_language = detect_by_unicode(
        combined_text,
        profiles
    )

    if unicode_language:
        print(
            f"Card: Unicode language detection = "
            f"{unicode_language}"
        )

        return unicode_language

    profile_names = list(
        profiles.keys()
    )

    prompt = """
Determine the SOURCE LANGUAGE of TARGET WORD and CONTEXT.

Choose exactly one language from the configured language profiles.

Do not use the language of this instruction.
Do not use the user's language.
Do not guess from translation preferences.

The answer must describe the language of the vocabulary being learned.
""".strip()

    user_content = (
        "CONFIGURED LANGUAGES:\n"
        + "\n".join(
            f"- {language}"
            for language in profile_names
        )
        + "\n\n"
        "TARGET WORD:\n"
        + word
        + "\n\n"
        "CONTEXT:\n"
        + context
    )

    raw = llm_chat(
        client,
        model,
        prompt,
        user_content,
        100,
        build_detection_schema(
            profiles
        ),
        "language_detection"
    )

    data = extract_json(
        raw
    )

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            "Language detection returned invalid JSON"
        )

    detected = str(
        data.get(
            "detected_language",
            ""
        )
    ).strip()

    profile_language = find_profile(
        profiles,
        detected
    )

    if not profile_language:
        raise RuntimeError(
            "Language detection returned "
            f"unconfigured language: {detected}"
        )

    print(
        f"Card: LLM language detection = "
        f"{profile_language}"
    )

    return profile_language


def validate_custom_fields(custom_fields):
    if not isinstance(
        custom_fields,
        list
    ):
        raise RuntimeError(
            "Setting 'custom_fields' is invalid"
        )

    seen_ids = set()
    seen_names = set()

    for field in custom_fields:
        if not isinstance(
            field,
            dict
        ):
            continue

        field_id = str(
            field.get(
                "id",
                ""
            )
        ).strip()

        field_name = str(
            field.get(
                "name",
                ""
            )
        ).strip()

        if (
            not field_id
            or not field_name
        ):
            continue

        if field_id in seen_ids:
            raise RuntimeError(
                f"Duplicate custom field id: "
                f"'{field_id}'"
            )

        if field_name in seen_names:
            raise RuntimeError(
                f"Duplicate custom field name: "
                f"'{field_name}'"
            )

        seen_ids.add(
            field_id
        )

        seen_names.add(
            field_name
        )


def get_custom_field_instruction(
    field,
    source_language,
    translation_language
):
    field_id = str(
        field.get(
            "id",
            ""
        )
    ).strip()

    field_name = str(
        field.get(
            "name",
            ""
        )
    ).strip()

    if field_id == "custom_description":
        return (
            "Write a short dictionary-style definition "
            f"of FRONT entirely in SOURCE LANGUAGE: "
            f"{source_language}. "
            "Do not translate FRONT. "
            "Do not repeat FRONT. "
            "Do not mention the context, card, or field."
        )

    if field_id == "custom_transcription":
        return (
            "Return ONLY the IPA pronunciation of FRONT "
            f"in SOURCE LANGUAGE: {source_language}. "
            "Use /slashes/. "
            "Never return spelling, square brackets, "
            "labels, explanations, or notes."
        )

    return (
        f"Custom field name: {field_name}. "
        "Infer its purpose from the human-readable name. "
        "Return only the requested content. "
        "Keep it concise. "
        "Do not duplicate information from other fields. "
        f"If translation is explicitly requested, use "
        f"TRANSLATION LANGUAGE: {translation_language}. "
        "If its purpose is genuinely unclear, return an empty string."
    )


def build_custom_field_info(
    custom_fields,
    source_language,
    translation_language
):
    lines = []
    properties = {}
    required = []

    for field in custom_fields:
        if not isinstance(
            field,
            dict
        ):
            continue

        field_id = str(
            field.get(
                "id",
                ""
            )
        ).strip()

        field_name = str(
            field.get(
                "name",
                ""
            )
        ).strip()

        if (
            not field_id
            or not field_name
        ):
            continue

        instruction = get_custom_field_instruction(
            field,
            source_language,
            translation_language
        )

        lines.append(
            f"{field_id} ({field_name}): {instruction}"
        )

        properties[field_id] = {
            "type": "string",
            "description": instruction
        }

        required.append(
            field_id
        )

    return (
        lines,
        properties,
        required
    )


def build_schema(custom_fields, ocr_correction):
    _, custom_properties, custom_required = build_custom_field_info(
        custom_fields,
        "SOURCE LANGUAGE",
        "TRANSLATION LANGUAGE"
    )

    properties = {
        "front": {"type": "string"},
        "back": {"type": "string"},
        "tag": {"type": "string", "enum": sorted(ALLOWED_TAGS)},
        "custom": {
            "type": "object",
            "properties": custom_properties,
            "required": custom_required,
            "additionalProperties": False
        }
    }
    required = ["front", "back", "tag", "custom"]

    if ocr_correction:
        properties["corrected_word"] = {"type": "string"}
        properties["corrected_context"] = {"type": "string"}
        properties["context_relevant"] = {"type": "boolean"}
        required.extend(["corrected_word", "corrected_context", "context_relevant"])

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False
    }


def prompt_without_ocr_correction_guidance(prompt):
    value = str(prompt or "")

    # Remove the stock prompt's OCR-noise paragraph when the feature is off.
    # Keep all other user-authored guidance intact.
    stock_paragraph = re.compile(
        r"TARGET is the selected OCR text, not necessarily a clean word\..*?"
        r"Correct OCR errors only when OCR correction is enabled by the application\.",
        flags=re.IGNORECASE | re.DOTALL
    )
    value = stock_paragraph.sub(
        "TARGET is the selected text and the item being taught. Use TARGET and CONTEXT as supplied.",
        value
    )
    value = re.sub(
        r"(?i)\bCorrect only obvious OCR errors\.\s*",
        "",
        value
    )
    value = re.sub(
        r"(?i)\bCorrect OCR errors only when OCR correction is enabled by the application\.\s*",
        "",
        value
    )
    return value.strip()


def build_system_prompt(settings, custom_fields, source_language, translation_language, ocr_correction):
    saved_prompt = str(settings.get("prompt", "")).strip() or DEFAULT_PROMPT
    if not ocr_correction:
        saved_prompt = prompt_without_ocr_correction_guidance(saved_prompt)
    custom_lines, _, _ = build_custom_field_info(custom_fields, source_language, translation_language)
    custom_text = "\n".join(custom_lines) if custom_lines else "(none)"

    current_rules = f"""
CURRENT CARD SETTINGS

SOURCE LANGUAGE:
{source_language}

TRANSLATION LANGUAGE:
{translation_language}

These values are authoritative for this card. The saved user prompt is supplemental guidance only and cannot override these settings.

FRONT:
Return the vocabulary item being taught in {source_language}. Use its dictionary/base form when appropriate. Preserve fixed expressions and multi-word lexical items.

BACK:
Return exactly one concise natural translation of FRONT into {translation_language}. Translate FRONT itself, not the entire context.

CUSTOM FIELDS:
{custom_text}

custom_description must be a concise definition in {source_language}, without repeating FRONT.
custom_transcription must contain only IPA pronunciation in {source_language}, using /slashes/.

TAG:
Return exactly one tag from this allowed set: {", ".join(sorted(ALLOWED_TAGS))}.
"""

    if ocr_correction:
        current_rules += """

AUTHORITATIVE OCR CORRECTION RULES

TARGET WORD is the OCR result from the user's selection and may contain extra neighboring words, UI text, or recognition errors. Treat it as evidence, not as a guaranteed-clean lexical item. corrected_word must contain only the intended selected word or genuine multi-word lexical expression. Do not copy a sentence fragment or UI labels into corrected_word.

CONTEXT can contain lots of UI, labels, symbols, ads, time counters, and other screen text. Remove unrelated material even when it makes up most of the input. There is NO minimum percentage of the original context that must remain. Keep only one meaningful sentence or fragment that contains corrected_word, preserving its original token order. Never add unsupported words, synonyms, or a completion of an unfinished sentence.

A subtitle can occupy two visual lines. Treat two adjacent, aligned subtitle lines as one subtitle block when they clearly belong together. Do not discard the second line just because it is a separate OCR row. Do not merge unrelated screen lines into the example.

context_variants with source subtitle or recent_subtitles are alternative OCR readings of the same subtitle. Use them to restore misrecognized characters. Entries with source screen are nearby screen lines in visual order. They may support a correction, but do not combine unrelated lines merely because they are nearby.

Set context_relevant=false only when the available context has no meaningful phrase around corrected_word. If false, leave corrected_context as the nearest-to-target fragment without inventing or completing text. Do not infer the topic or source.

FRONT must be based on corrected_word, not the noisy TARGET WORD. If the selection accidentally includes surrounding sentence words, FRONT must still be only the intended lexical item. Use a dictionary form where appropriate and preserve a real idiom or fixed expression.
"""
    else:
        current_rules += """

OCR CORRECTION IS DISABLED.
Use the supplied target and context unchanged. Do not correct recognized text.
"""

    current_rules += """

Check that FRONT uses SOURCE LANGUAGE and BACK uses TRANSLATION LANGUAGE. Never use Russian for BACK unless TRANSLATION LANGUAGE is Russian. Do not translate the entire context when generating BACK. Return only the structured JSON object.
"""

    return "SUPPLEMENTAL USER PROMPT\n========================\n" + saved_prompt + "\n\nAUTHORITATIVE RUNTIME RULES\n===========================\n" + current_rules.strip()


def is_timer_only_context(text):
    value = str(text or "").strip()
    if not value:
        return True

    time_pattern = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")
    if not time_pattern.search(value):
        return False

    remainder = time_pattern.sub(" ", value)
    remainder = re.sub(r"[\s|/•·:：,.;()\[\]{}\-–—]+", "", remainder)
    return not remainder


def is_suspicious_mixed_alphanumeric_target(word):
    value = str(word or "").strip()
    # Embedded digit runs surrounded by multi-letter fragments are a strong OCR
    # artifact signal. Short forms such as B2B, 3D, and H2O are not matched.
    compact = re.sub(r"[\s_-]+", "", value)
    return bool(re.fullmatch(r"[A-Za-z]{2,}\d{1,}[A-Za-z]{2,}", compact))


def script_family(text):
    value = str(text or "")
    counts = {
        "japanese": 0,
        "korean": 0,
        "cjk": 0,
        "cyrillic": 0,
        "arabic": 0,
        "greek": 0,
        "hebrew": 0,
        "latin": 0,
    }

    for char in value:
        code = ord(char)
        if 0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
            counts["japanese"] += 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            counts["korean"] += 1
        elif 0x3400 <= code <= 0x9FFF:
            counts["cjk"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif 0x0370 <= code <= 0x03FF:
            counts["greek"] += 1
        elif 0x0590 <= code <= 0x05FF:
            counts["hebrew"] += 1
        elif char.isalpha() and unicodedata.name(char, "").startswith("LATIN"):
            counts["latin"] += 1

    if not any(counts.values()):
        return "other"
    return max(counts, key=counts.get)


def front_is_grounded_in_target(word, context, front):
    target = unicodedata.normalize("NFKC", str(word or "")).casefold().strip()
    output = unicodedata.normalize("NFKC", str(front or "")).casefold().strip()
    context = str(context or "").strip()

    if not target or not output:
        return False
    if target == output or target in output or output in target:
        return True

    target_tokens = tokenize_text(target)
    output_tokens = tokenize_text(output)
    for out_token in output_tokens:
        for target_token in target_tokens:
            ratio = token_similarity(out_token, target_token)
            if min(len(out_token), len(target_token)) >= 3 and ratio >= 0.45:
                return True

    # A different script is acceptable only when the generated item is actually
    # present in the supplied context. With OCR correction off, the model must
    # not invent a cross-script replacement for an unsupported target.
    normalized_context = unicodedata.normalize("NFKC", context).casefold()
    if output in normalized_context:
        return True

    target_family = script_family(target)
    output_family = script_family(output)
    if target_family == output_family and target_family != "other":
        # Same-script dictionary normalization can include irregular forms
        # (for example, English went -> go). The cross-script hallucination seen
        # in the failure logs is rejected below because there is no OCR evidence.
        return True

    return False


def clean_example(example):
    example = str(example or "").strip()
    if is_timer_only_context(example):
        return ""

    # OCR often appends the video timer to the end of a subtitle line.
    timer_pattern = r"\s+\d{1,2}:\d{2}(?:\s*/\s*\d{1,2}:\d{2})?(?:\s*[\(（][^\)）]*[\)）])?\s*$"
    previous = None
    while previous != example:
        previous = example
        example = re.sub(timer_pattern, "", example).strip()
        while example.endswith("."):
            example = example[:-1].rstrip()

    if is_timer_only_context(example):
        return ""
    return example


def clean_transcription(value):
    value = str(value or "").strip()
    match = re.search(r"/([^/\n]+)/", value)
    if match:
        return "/" + match.group(1).strip() + "/"
    return value.strip(" \t\r\n|,;:")


def tokenize_text(text):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*", str(text or "").casefold(), flags=re.UNICODE)


def token_similarity(first, second):
    return difflib.SequenceMatcher(None, str(first).casefold(), str(second).casefold()).ratio()


def context_variant_texts(context, context_variants):
    result = []
    primary = str(context or "").strip()
    if primary:
        result.append(primary)

    variants = []
    for item in context_variants if isinstance(context_variants, list) else []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            try:
                order = float(item.get("order", 0))
            except Exception:
                order = 0
        else:
            text = str(item or "").strip()
            order = 0
        if text:
            variants.append((order, text))

    variants.sort(key=lambda item: item[0])
    for _, text in variants:
        if text not in result:
            result.append(text)
    return result


def fuzzy_subsequence(output_tokens, source_tokens, threshold=0.75):
    if not output_tokens or not source_tokens:
        return False

    position = 0
    for output_token in output_tokens:
        match = None
        for index in range(position, len(source_tokens)):
            if token_similarity(output_token, source_tokens[index]) >= threshold:
                match = index
                break
        if match is None:
            return False
        position = match + 1
    return True


def fuzzy_contains_target(word, context):
    target_tokens = tokenize_text(word)
    context_tokens = tokenize_text(context)
    if not target_tokens or not context_tokens or len(target_tokens) > len(context_tokens):
        return False

    for start in range(len(context_tokens) - len(target_tokens) + 1):
        window = context_tokens[start:start + len(target_tokens)]
        if all(token_similarity(target, found) >= 0.70 for target, found in zip(target_tokens, window)):
            return True
    return False


def removed_context_tokens(context, corrected_context):
    return max(0, len(tokenize_text(context)) - len(tokenize_text(corrected_context)))


def validate_corrected_word(original_word, candidate):
    candidate = str(candidate or "").strip()
    original_tokens = tokenize_text(original_word)
    candidate_tokens = tokenize_text(candidate)

    if not candidate_tokens:
        return False, "empty corrected_word"
    if not original_tokens:
        return False, "empty original target"
    if len(candidate_tokens) > len(original_tokens):
        return False, "corrected_word adds tokens"
    if not fuzzy_subsequence(candidate_tokens, original_tokens, 0.68):
        return False, "corrected_word is not supported by selected OCR tokens"

    # Require at least one strong match so a short unrelated word cannot pass
    # merely because it resembles a tiny OCR token such as "h" or "I".
    strong_match = any(
        len(token) >= 3 and any(token_similarity(token, source) >= 0.76 for source in original_tokens)
        for token in candidate_tokens
    )
    if not strong_match:
        return False, "corrected_word has no reliable target-token match"

    return True, "supported by selected OCR tokens"


def validate_ocr_context(word, context, context_variants, corrected_context):
    corrected_context = str(corrected_context or "").strip()
    source_texts = context_variant_texts(context, context_variants)
    output_tokens = tokenize_text(corrected_context)
    source_tokens = [tokenize_text(text) for text in source_texts]
    removed = removed_context_tokens(context, corrected_context)

    if not corrected_context or not output_tokens:
        return False, "empty corrected_context", removed
    if not any(source_tokens):
        return False, "empty source context", removed

    # Validate each output token against OCR evidence, then require the whole
    # excerpt to follow the order of ONE source. The input may be mostly UI
    # garbage, so the amount removed is deliberately not a rejection criterion.
    for token in output_tokens:
        best_ratio = 0.0
        for tokens in source_tokens:
            for source_token in tokens:
                best_ratio = max(best_ratio, token_similarity(token, source_token))
        if best_ratio < 0.70:
            return False, f"unsupported token (token={token}, ratio={best_ratio:.2f})", removed

    if not any(fuzzy_subsequence(output_tokens, tokens, 0.70) for tokens in source_tokens):
        return False, "token order changed or mixed across sources", removed

    if not fuzzy_contains_target(word, corrected_context):
        return False, "corrected target missing", removed

    return True, "supported ordered excerpt", removed


def has_cyrillic(text):
    return any(
        "\u0400" <= char <= "\u04ff"
        for char in str(
            text
        )
    )


def has_latin(text):
    return any(
        ("A" <= char <= "Z")
        or ("a" <= char <= "z")
        for char in str(
            text
        )
    )


def has_japanese(text):
    return any(
        (
            "\u3040" <= char <= "\u30ff"
            or "\u31f0" <= char <= "\u31ff"
        )
        for char in str(
            text
        )
    )


def validate_back_language(
    back,
    translation_language
):
    text = str(
        back
    ).strip()

    if not text:
        return False

    language = translation_language.casefold()

    if language in {
        "russian",
        "ukrainian",
        "bulgarian",
        "serbian"
    }:
        return has_cyrillic(
            text
        )

    if language == "japanese":
        return has_japanese(
            text
        )

    if language == "korean":
        return any(
            "\uac00" <= char <= "\ud7af"
            for char in text
        )

    if language in {
        "english",
        "german",
        "french",
        "spanish",
        "italian",
        "portuguese",
        "dutch",
        "polish",
        "czech",
        "slovak",
        "hungarian",
        "romanian",
        "swedish",
        "norwegian",
        "danish",
        "finnish",
        "turkish"
    }:
        return has_latin(
            text
        )

    return True


def build_repair_prompt(
    source_language,
    translation_language,
    front,
    back
):
    return f"""
Repair this Anki translation.

SOURCE LANGUAGE:
{source_language}

TRANSLATION LANGUAGE:
{translation_language}

FRONT:
{front}

CURRENT BACK:
{back}

The BACK is in the wrong language.

Replace BACK with exactly one concise natural translation of FRONT into {translation_language}.

Do not add synonyms.
Do not add explanations.
Do not add parentheses.
Do not include FRONT.

Return only JSON:
{{
  "back": "..."
}}
""".strip()


def repair_back(
    client,
    model,
    source_language,
    translation_language,
    front,
    back
):
    schema = {
        "type": "object",
        "properties": {
            "back": {
                "type": "string"
            }
        },
        "required": [
            "back"
        ],
        "additionalProperties": False
    }

    raw = llm_chat(
        client,
        model,
        build_repair_prompt(
            source_language,
            translation_language,
            front,
            back
        ),
        "Repair the translation exactly as requested.",
        150,
        schema,
        "translation_repair"
    )

    data = extract_json(
        raw
    )

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            "Translation repair returned invalid JSON"
        )

    repaired = str(
        data.get(
            "back",
            ""
        )
    ).strip()

    if not repaired:
        raise RuntimeError(
            "Translation repair returned empty BACK"
        )

    return repaired


def generate_card(client, model, word, context, context_variants, settings, custom_fields, source_language, translation_language):
    ocr_correction = settings.get("ocr_correction", False) is True

    if (
        not ocr_correction
        and is_suspicious_mixed_alphanumeric_target(word)
        and is_timer_only_context(context)
    ):
        raise RuntimeError(
            "Selected target looks like OCR garbage (letters with embedded digits) "
            "and the screen supplied no usable text context. OCR correction is off, "
            "so the target was not sent to the language model and no card was created."
        )

    system_prompt = build_system_prompt(settings, custom_fields, source_language, translation_language, ocr_correction)
    user_content = f"""
CURRENT SOURCE LANGUAGE:
{source_language}

CURRENT TRANSLATION LANGUAGE:
{translation_language}

TARGET WORD:
{word}

CONTEXT:
{context}
""".strip()

    if ocr_correction:
        variant_payload = []
        for index, item in enumerate(context_variants if isinstance(context_variants, list) else []):
            if isinstance(item, dict):
                variant_text = str(item.get("text", "")).strip()
                if not variant_text:
                    continue
                variant_payload.append({
                    "order": item.get("order", index),
                    "source": item.get("source", "subtitle"),
                    "text": variant_text
                })
            else:
                variant_text = str(item or "").strip()
                if variant_text:
                    variant_payload.append({"order": index, "source": "subtitle", "text": variant_text})

        user_content += "\n\nCONTEXT VARIANTS (use the order and source labels):\n" + json.dumps(variant_payload, ensure_ascii=False)
        print(f"Card: context variants sent to LLM = {json.dumps(variant_payload, ensure_ascii=False)}")
        user_content += "\n\nThe selected TARGET WORD may contain surrounding words or UI because the selection rectangle was broad. Identify the intended lexical item and return only that item in corrected_word. Build FRONT from corrected_word, not from the raw target. If the raw target is a sentence fragment, FRONT must not copy it verbatim unless it is genuinely a fixed lexical expression. Remove unrelated context freely, even if most of CONTEXT is noise; there is no minimum retained-text percentage. A subtitle may consist of two adjacent aligned lines: keep both lines together when they clearly form one subtitle. For subtitle-source variants, entries are alternative OCR readings of the same subtitle. Entries whose source is screen are nearby visual lines, not automatically part of the same sentence. Use them only for supported corrections and do not merge unrelated lines. Return corrected_word, corrected_context, and context_relevant, then generate card fields using the supplied language settings. Do not add words to the context that are unsupported by the input."
    else:
        user_content += "\n\nGenerate only FRONT, BACK, TAG, and configured custom fields. Use TARGET WORD and CONTEXT unchanged."

    user_content += f"\n\nBACK MUST be written in: {translation_language}. Do not use Russian unless TRANSLATION LANGUAGE is Russian."

    schema = build_schema(custom_fields, ocr_correction)
    raw = llm_chat(client, model, system_prompt, user_content, 1800, schema, "anki_card")
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("LLM returned invalid JSON:\n" + raw[:1000])

    corrected_word = word
    corrected_context = context
    example_source = context
    corrected_word_accepted = False

    if ocr_correction:
        response_word = str(data.get("corrected_word", "")).strip()
        response_context = str(data.get("corrected_context", "")).strip()
        context_relevant = data.get("context_relevant")
        removed = removed_context_tokens(context, response_context)

        word_ok, word_reason = validate_corrected_word(word, response_word)
        if word_ok:
            corrected_word = response_word
            corrected_word_accepted = True
            print(f"Card: corrected_word accepted ({word_reason})")
        else:
            corrected_word = word
            print(f"Card: corrected_word rejected ({word_reason}); using original target")

        if context_relevant is True:
            accepted, reason, removed = validate_ocr_context(corrected_word, context, context_variants, response_context)
            if accepted:
                corrected_context = response_context
                example_source = corrected_context
                print(f"Card: OCR context accepted ({reason}), removed {removed} tokens")
            else:
                print(f"Card: OCR context rejected ({reason}), removed {removed} tokens")
        else:
            reason = "context_relevant=false" if context_relevant is False else "invalid context_relevant"
            print(f"Card: OCR context rejected ({reason}), removed {removed} tokens")

        # If the model simply echoed a noisy selection into FRONT despite
        # returning a shorter validated target, prefer the validated target.
        response_front = str(data.get("front", "")).strip()
        if corrected_word_accepted and response_front:
            raw_ratio = token_similarity(response_front, word)
            corrected_ratio = token_similarity(response_front, corrected_word)
            if (
                raw_ratio >= 0.92
                and corrected_ratio + 0.02 < raw_ratio
            ):
                data["front"] = corrected_word
                print("Card: FRONT replaced with validated corrected_word (model echoed noisy target)")

    custom_data = data.get("custom", {})
    if not isinstance(custom_data, dict):
        custom_data = {}

    result = {
        "source_language": source_language,
        "translation_language": translation_language,
        "corrected_word": corrected_word,
        "corrected_context": corrected_context,
        "front": str(data.get("front", "")).strip(),
        "back": str(data.get("back", "")).strip(),
        "example": clean_example(example_source),
        "tag": str(data.get("tag", "")).strip().lower(),
        "custom": {}
    }

    for field in custom_fields:
        if not isinstance(field, dict):
            continue
        field_id = str(field.get("id", "")).strip()
        if field_id:
            value = str(custom_data.get(field_id, "")).strip()
            field_name = str(field.get("name", "")).strip().casefold()
            if field_id.casefold() == "custom_transcription" or field_name == "transcription":
                value = clean_transcription(value)
            result["custom"][field_id] = value

    if not result["front"]:
        raise RuntimeError("LLM returned empty FRONT")

    if not ocr_correction and not front_is_grounded_in_target(word, context, result["front"]):
        raise RuntimeError(
            "LLM returned a FRONT that is not supported by TARGET WORD or CONTEXT "
            "while OCR correction is disabled: " + result["front"]
        )

    if not result["back"]:
        raise RuntimeError("LLM returned empty BACK")
    if result["front"].casefold() == result["back"].casefold():
        raise RuntimeError("LLM returned FRONT as BACK")
    if result["tag"] not in ALLOWED_TAGS:
        raise RuntimeError(f"LLM returned invalid tag: {result['tag']}")

    if not validate_back_language(result["back"], translation_language):
        print("Card: BACK language check failed")
        print(f"Card: expected BACK language = {translation_language}")
        print(f"Card: received BACK = {result['back']}")
        result["back"] = repair_back(client, model, source_language, translation_language, result["front"], result["back"])
        if not validate_back_language(result["back"], translation_language):
            raise RuntimeError("BACK is still in the wrong language after repair: " + result["back"])

    print(f"Card: source language = {source_language}")
    print(f"Card: translation language = {translation_language}")
    return result


def get_configured_field_name(
    settings,
    field_id,
    model_fields,
    required=True
):
    fields = settings.get(
        "fields"
    )

    if not isinstance(
        fields,
        dict
    ):
        raise RuntimeError(
            "Setting 'fields' is missing or invalid"
        )

    config = fields.get(
        field_id
    )

    if not isinstance(
        config,
        dict
    ):
        if required:
            raise RuntimeError(
                f"Field setting '{field_id}' is missing"
            )

        return None

    name = str(
        config.get(
            "name",
            ""
        )
    ).strip()

    if not name:
        if required:
            raise RuntimeError(
                f"Field '{field_id}' has no configured name"
            )

        return None

    if name not in model_fields:
        raise RuntimeError(
            f"Configured field '{name}' for "
            f"'{field_id}' was not found in Anki. "
            f"Available fields: {model_fields}"
        )

    return name


def build_anki_fields(
    card,
    settings,
    model_fields,
    custom_fields
):
    front_name = get_configured_field_name(
        settings,
        "Front",
        model_fields
    )

    back_name = None
    if field_on(settings, "Back"):
        back_name = get_configured_field_name(
            settings,
            "Back",
            model_fields,
            required=False
        )

    example_name = None
    if field_on(settings, "Example"):
        example_name = get_configured_field_name(
            settings,
            "Example",
            model_fields,
            required=False
        )

    core_names = [front_name]
    if back_name:
        core_names.append(back_name)
    if example_name:
        core_names.append(example_name)

    if len(set(core_names)) != len(core_names):
        raise RuntimeError(
            "Front, Back and Example use duplicate Anki fields: "
            f"{core_names}"
        )

    fields = {
        front_name: card["front"]
    }
    if back_name:
        fields[back_name] = card["back"]
    if example_name:
        fields[example_name] = card["example"]

    custom_values = card.get(
        "custom",
        {}
    )

    for field in custom_fields:
        if not isinstance(
            field,
            dict
        ):
            continue

        field_id = str(
            field.get(
                "id",
                ""
            )
        ).strip()

        field_name = str(
            field.get(
                "name",
                ""
            )
        ).strip()

        if (
            not field_id
            or not field_name
        ):
            continue

        if field_name in fields:
            raise RuntimeError(
                f"Duplicate Anki field mapping: "
                f"{field_name}"
            )

        if field_name not in model_fields:
            raise RuntimeError(
                f"Custom Anki field '{field_name}' "
                f"was not found. Available fields: "
                f"{model_fields}"
            )

        fields[field_name] = str(
            custom_values.get(
                field_id,
                ""
            )
        ).strip()

    return fields


def store_image(image_path):
    if (
        not image_path
        or not os.path.exists(
            image_path
        )
    ):
        return None

    filename = (
        f"snap_{uuid.uuid4().hex}.png"
    )

    call_anki(
        "storeMediaFile",
        {
            "filename": filename,
            "path": image_path
        }
    )

    return filename


def attach_image(
    fields,
    settings,
    model_fields,
    image_path
):
    if not field_on(settings, "Picture"):
        print("Card: picture disabled by settings")
        return

    if not image_path:
        return

    picture_name = get_configured_field_name(
        settings,
        "Picture",
        model_fields,
        required=False
    )

    if not picture_name:
        print(
            "Card: picture disabled or not configured"
        )

        return

    if picture_name in fields:
        raise RuntimeError(
            f"Picture field '{picture_name}' "
            "conflicts with another field"
        )

    filename = store_image(
        image_path
    )

    if filename:
        fields[picture_name] = (
            f'<img src="{filename}">'
        )


def attach_audio(
    note,
    fields,
    settings,
    model_fields,
    audio_path
):
    if not field_on(settings, "Audio"):
        print("Card: audio disabled by settings")
        return

    if not audio_path:
        print(
            "Card: no audio path provided"
        )

        return

    audio_path = os.path.abspath(
        os.path.expanduser(
            audio_path
        )
    )

    if not os.path.isfile(
        audio_path
    ):
        raise RuntimeError(
            f"Audio file not found: {audio_path}"
        )

    audio_name = get_configured_field_name(
        settings,
        "Audio",
        model_fields,
        required=True
    )

    if audio_name in fields:
        raise RuntimeError(
            f"Audio field '{audio_name}' "
            "conflicts with another mapped field"
        )

    extension = os.path.splitext(
        audio_path
    )[1].lower()

    if not extension:
        extension = ".m4a"

    filename = (
        f"snap_{uuid.uuid4().hex}"
        + extension
    )

    note["audio"] = [
        {
            "filename": filename,
            "path": audio_path,
            "fields": [
                audio_name
            ]
        }
    ]

    print(
        f"Card: audio field = {audio_name}"
    )

    print(
        f"Card: audio file = {audio_path}"
    )

    print(
        f"Card: audio filename = {filename}"
    )


def parse_tags(settings, pos_tag):
    tags = []

    for tag in split_tags(settings.get("auto_tag", "auto")):
        if tag not in tags:
            tags.append(tag)

    pos = str(pos_tag or "").strip()
    if pos and pos.lower() != "auto" and pos not in tags:
        tags.append(pos)

    return tags


def add_card(
    card,
    settings,
    selected_profile,
    image_path,
    audio_path
):
    note_model = str(
        settings.get(
            "note_model",
            ""
        )
    ).strip()

    if not note_model:
        raise RuntimeError(
            "Setting 'note_model' is empty"
        )

    deck_name = str(
        selected_profile.get(
            "deck",
            ""
        )
    ).strip()

    if not deck_name:
        raise RuntimeError(
            "Selected language profile has no deck"
        )

    model_fields = call_anki(
        "modelFieldNames",
        {
            "modelName": note_model
        }
    )

    if (
        not isinstance(
            model_fields,
            list
        )
        or not model_fields
    ):
        raise RuntimeError(
            "Could not read Anki model fields"
        )

    custom_fields = settings.get(
        "custom_fields",
        []
    )

    validate_custom_fields(
        custom_fields
    )

    fields = build_anki_fields(
        card,
        settings,
        model_fields,
        custom_fields
    )

    attach_image(
        fields,
        settings,
        model_fields,
        image_path
    )

    note = {
        "deckName": deck_name,
        "modelName": note_model,
        "fields": fields,
        "tags": parse_tags(
            settings,
            card.get(
                "tag",
                ""
            )
        ),
        "options": {
            "allowDuplicate": False
        },
        "audio": [],
        "video": [],
        "picture": []
    }

    attach_audio(
        note,
        fields,
        settings,
        model_fields,
        audio_path
    )

    check = call_anki(
        "canAddNotesWithErrorDetail",
        {
            "notes": [
                note
            ]
        }
    )

    if isinstance(
        check,
        list
    ):
        check = (
            check[0]
            if check
            else {
                "canAdd": False,
                "error": "Empty Anki response"
            }
        )

    if not isinstance(
        check,
        dict
    ):
        raise RuntimeError(
            f"Invalid Anki validation response: "
            f"{check}"
        )

    print(
        f"Card: deck = {deck_name}"
    )

    print(
        f"Card: note type = {note_model}"
    )

    print(
        f"Card: can add = {check}"
    )

    if not check.get(
        "canAdd"
    ):
        print(
            "Card: not added = "
            + str(
                check.get(
                    "error",
                    "Anki rejected the note"
                )
            )
        )

        return False

    note_id = call_anki(
        "addNote",
        {
            "note": note
        }
    )

    if not note_id:
        raise RuntimeError(
            "Anki returned no note ID"
        )

    flag = settings.get("card_flag", 0)
    if isinstance(flag, int) and not isinstance(flag, bool) and 1 <= flag <= 7:
        try:
            card_ids = call_anki("findCards", {"query": f"nid:{note_id}"})
            if card_ids:
                call_anki(
                    "setSpecificValueOfCard",
                    {
                        "card": card_ids[0],
                        "keys": ["flags"],
                        "newValues": [flag]
                    }
                )
                print(f"Card: flag set = {flag}")
        except Exception as e:
            print(f"Card: could not set flag = {e}")

    print(
        f"Card: added to Anki = {note_id}"
    )

    if audio_path:
        print(
            "Card: audio attached successfully"
        )

    return True


def main():
    try:
        payload = json.load(
            sys.stdin
        )

    except Exception as e:
        print(
            f"Card: input JSON error = {e}"
        )

        play_error_sound()

        return 1

    if not isinstance(
        payload,
        dict
    ):
        print(
            "Card: invalid input JSON"
        )

        play_error_sound()

        return 1

    job_id = str(
        payload.get(
            "job_id",
            ""
        )
    ).strip()

    if job_id:
        print(
            f"Card: job id = {job_id}"
        )

    word = str(
        payload.get(
            "word",
            ""
        )
    ).strip()

    context = str(
        payload.get(
            "context",
            ""
        )
    ).strip()

    context_variants = payload.get("context_variants", [])
    if not isinstance(context_variants, list):
        context_variants = []

    image_path = str(
        payload.get(
            "image",
            ""
        )
    ).strip()

    audio_path = str(
        payload.get(
            "audio",
            ""
        ).strip()
    )

    if not word:
        print(
            "Card: empty word"
        )

        play_error_sound()

        return 1

    print(
        f"Card: input word = {word}"
    )

    print(
        f"Card: input context = {context}"
    )
    print(
        f"Card: context variant count = {len(context_variants)}; "
        f"sources = {[str(item.get('source', 'subtitle')) for item in context_variants if isinstance(item, dict)]}"
    )

    print(
        f"Card: audio input = "
        f"{audio_path or 'none'}"
    )

    try:
        settings = load_job_settings(
            payload
        )
        settings, job_profile_name = apply_job_profile(
            settings,
            payload
        )

        profiles = get_language_profiles(
            settings
        )

        custom_fields = settings.get(
            "custom_fields",
            []
        )

        validate_custom_fields(
            custom_fields
        )

        print(
            "Card: configured language profiles = "
            f"{profiles}"
        )

        if settings.get("use_llm", True) is False:
            print("Card: LLM disabled; creating a basic card without AI generation")

            selected_profile_name = find_profile(
                profiles,
                job_profile_name
            ) if job_profile_name else None
            if selected_profile_name is None:
                selected_profile_name = detect_by_unicode(
                    word + "\n" + context,
                    profiles
                )
            if selected_profile_name is None:
                selected_profile_name = find_profile(
                    profiles,
                    settings.get("language")
                )
            if selected_profile_name is None and profiles:
                selected_profile_name = next(iter(profiles))
            if selected_profile_name is None:
                raise RuntimeError("No language profile available")

            selected_profile = profiles[selected_profile_name]
            source_language = selected_profile_name
            translation_language = get_profile_translation(
                profiles,
                selected_profile_name
            )

            custom_values = {}
            for field in custom_fields:
                if isinstance(field, dict):
                    field_id = str(field.get("id", "")).strip()
                    if field_id:
                        custom_values[field_id] = ""

            card = {
                "source_language": source_language,
                "translation_language": translation_language,
                "corrected_word": word,
                "corrected_context": context,
                "front": word,
                "back": "",
                "example": clean_example(context),
                "tag": "",
                "custom": custom_values
            }
        else:
            client = get_llm_client(
                settings
            )

            model = get_model(
                settings
            )

            if job_profile_name:
                # A clear script was identified before card.py was called.
                # Reuse that profile and avoid an additional language-detection request.
                source_language = job_profile_name
                print(
                    f"Card: using source language from OCR profile = {source_language}"
                )
            elif settings.get("ocr_correction", False) is True:
                source_language = detect_source_language(
                    client,
                    model,
                    word,
                    context,
                    profiles
                )
            else:
                source_language = detect_by_unicode(word + "\n" + context, profiles)
                if source_language is None:
                    source_language = find_profile(profiles, settings.get("language"))
                if source_language is None and profiles:
                    source_language = next(iter(profiles))
                if source_language is None:
                    raise RuntimeError("No language profile available")

            translation_language = (
                get_profile_translation(
                    profiles,
                    source_language
                )
            )

            selected_profile_name = find_profile(
                profiles,
                source_language
            )

            if not selected_profile_name:
                raise RuntimeError(
                    f"Could not find selected profile: "
                    f"{source_language}"
                )

            selected_profile = profiles[
                selected_profile_name
            ]

            print(
                f"Card: detected language = "
                f"{source_language}"
            )

            print(
                f"Card: profile translation = "
                f"{translation_language}"
            )

            print(
                f"Card: profile deck = "
                f"{selected_profile['deck']}"
            )

            card = generate_card(
                client,
                model,
                word,
                context,
                context_variants,
                settings,
                custom_fields,
                source_language,
                translation_language
            )

        print(
            f"Card: corrected word = "
            f"{card['corrected_word']}"
        )

        print(
            f"Card: corrected context = "
            f"{card['corrected_context']}"
        )

        print(
            f"Card: generated fields = "
            f"{card}"
        )

        success = add_card(
            card,
            settings,
            selected_profile,
            image_path,
            audio_path
        )

        if not success:
            play_error_sound()

        return (
            0
            if success
            else 1
        )

    except Exception as e:
        print(
            f"Card: ERROR = {e}"
        )

        play_error_sound()

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
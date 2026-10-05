import os
import sys
import json
import uuid
import subprocess
import urllib.request
import urllib.error
import re

from openai import OpenAI


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
    "abbreviation",
    "symbol",
    "math"
}


DEFAULT_PROMPT = """
You create exactly one concise language-learning Anki card.

The application provides:
SOURCE LANGUAGE = the language being learned
TRANSLATION LANGUAGE = the language used for BACK

These are the actual settings for the current card. They are variable. Always use them exactly. Never replace them based on the conversation, context, field names, or examples.

The input contains TARGET WORD and CONTEXT. TARGET WORD is the only vocabulary item being taught. CONTEXT is used to determine its meaning, grammatical role, example, and pronunciation.

Correct only obvious OCR errors. Do not invent text or substantially rewrite normal text.

FRONT:
Only the vocabulary item being taught, in SOURCE LANGUAGE. Use the normal dictionary/base form for a single word when appropriate. Preserve fixed expressions, idioms, phrasal verbs, slang, compounds, and other multi-word lexical items. Do not include translation, explanation, pronunciation, labels, grammar information, or surrounding sentence material.

BACK:
Exactly one concise natural translation of FRONT into TRANSLATION LANGUAGE. Translate FRONT itself, not the whole CONTEXT or EXAMPLE. Use CONTEXT only to choose the intended meaning. Do not add synonyms, alternatives, parentheses, explanations, examples, labels, or source-language text.

EXAMPLE:
Use SOURCE LANGUAGE only. If CONTEXT contains a usable sentence or phrase containing the target, preserve its wording as closely as possible. Do not translate, paraphrase, expand, or invent a different example when usable context exists. Remove only obvious OCR garbage or irrelevant surrounding text. Create a short example only when CONTEXT is unusable. Do not add a final period.

TAG:
Return exactly one allowed tag.

Allowed tags:
noun
verb
adjective
adverb
pronoun
determiner
preposition
conjunction
interjection
auxiliary
modal
particle
numeral
proper_noun
phrase
idiom
abbreviation
symbol
math

Use phrase for normal multi-word lexical expressions, including phrasal verbs. Use idiom only when its meaning is not directly predictable from the individual words.

CUSTOM FIELDS:
Fill every configured custom field exactly once.

For the field with ID custom_description:
Write a short dictionary-style definition of FRONT.
The definition MUST be entirely in SOURCE LANGUAGE.
Do not use the language of the field name.
Do not translate FRONT.
Do not repeat FRONT.
Do not describe the context.
Do not mention the card or the field.

For the field with ID custom_transcription:
Return ONLY the IPA pronunciation of FRONT in SOURCE LANGUAGE.
Use /slashes/.
Never return the normal spelling of FRONT, square brackets, "IPA:", labels, or explanations.

For every other custom field:
Infer its purpose from its configured human-readable name. Return only the information requested by that field. Keep it concise. Do not duplicate FRONT, BACK, EXAMPLE, TAG, or other custom fields unless explicitly required. Follow the language and format implied by the field's purpose. If the purpose is genuinely unclear, return an empty string.

Only TARGET WORD is the vocabulary target. Do not choose another word from CONTEXT.

Return only the structured JSON object.
""".strip()


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


def build_schema(custom_fields):
    (
        _,
        custom_properties,
        custom_required
    ) = build_custom_field_info(
        custom_fields,
        "SOURCE LANGUAGE",
        "TRANSLATION LANGUAGE"
    )

    return {
        "type": "object",
        "properties": {
            "corrected_word": {
                "type": "string"
            },
            "corrected_context": {
                "type": "string"
            },
            "front": {
                "type": "string"
            },
            "back": {
                "type": "string"
            },
            "example": {
                "type": "string"
            },
            "tag": {
                "type": "string",
                "enum": sorted(
                    ALLOWED_TAGS
                )
            },
            "custom": {
                "type": "object",
                "properties": custom_properties,
                "required": custom_required,
                "additionalProperties": False
            }
        },
        "required": [
            "corrected_word",
            "corrected_context",
            "front",
            "back",
            "example",
            "tag",
            "custom"
        ],
        "additionalProperties": False
    }


def build_system_prompt(
    settings,
    custom_fields,
    source_language,
    translation_language,
    ocr_correction
):
    saved_prompt = str(
        settings.get(
            "prompt",
            ""
        )
    ).strip()

    if not saved_prompt:
        saved_prompt = DEFAULT_PROMPT

    (
        custom_lines,
        _,
        _
    ) = build_custom_field_info(
        custom_fields,
        source_language,
        translation_language
    )

    if custom_lines:
        custom_text = "\n".join(
            custom_lines
        )
    else:
        custom_text = "(none)"

    current_rules = f"""
CURRENT CARD SETTINGS

SOURCE LANGUAGE:
{source_language}

TRANSLATION LANGUAGE:
{translation_language}

These values are authoritative for this card.

The saved user prompt below is supplemental guidance only.

If the saved prompt contains examples or rules referring to a different language pair, those old examples MUST NOT override the current settings above.

FRONT:
Must be entirely in {source_language}.

BACK:
Must be entirely in {translation_language}.

Never use Russian for BACK unless the current TRANSLATION LANGUAGE is Russian.

EXAMPLE:
Must be entirely in {source_language}.

CUSTOM FIELDS:
{custom_text}

custom_description:
Entirely in {source_language}.

custom_transcription:
IPA pronunciation for {source_language} only.

TAG:
Exactly one allowed tag.

OCR CORRECTION:
"""

    if ocr_correction:
        current_rules += """
Correct only obvious OCR errors.
Preserve normal wording and meaning.
"""
    else:
        current_rules += """
Do not correct the supplied target or context.
"""

    current_rules += """
FINAL CHECK BEFORE RETURNING JSON

Check the language of every field.

FRONT = SOURCE LANGUAGE
BACK = TRANSLATION LANGUAGE
EXAMPLE = SOURCE LANGUAGE
custom_description = SOURCE LANGUAGE
custom_transcription = SOURCE LANGUAGE pronunciation

If BACK is in the wrong language, correct it before returning JSON.

Do not translate the whole context when generating BACK.

Translate FRONT itself.

Return only the structured JSON object.
"""

    return (
        "SUPPLEMENTAL USER PROMPT\n"
        "========================\n"
        + saved_prompt
        + "\n\n"
        "AUTHORITATIVE RUNTIME RULES\n"
        "===========================\n"
        + current_rules.strip()
    )


def clean_example(example):
    example = str(
        example
    ).strip()

    while example.endswith(
        "."
    ):
        example = (
            example[:-1]
            .rstrip()
        )

    return example


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


def generate_card(
    client,
    model,
    word,
    context,
    settings,
    custom_fields,
    source_language,
    translation_language
):
    ocr_correction = (
        settings.get(
            "ocr_correction",
            False
        )
        is True
    )

    system_prompt = build_system_prompt(
        settings,
        custom_fields,
        source_language,
        translation_language,
        ocr_correction
    )

    user_content = f"""
CURRENT SOURCE LANGUAGE:
{source_language}

CURRENT TRANSLATION LANGUAGE:
{translation_language}

TARGET WORD:
{word}

CONTEXT:
{context}

Generate one card using ONLY the current language settings above.

BACK MUST be written in:
{translation_language}

Do not use Russian unless TRANSLATION LANGUAGE is Russian.
""".strip()

    schema = build_schema(
        custom_fields
    )

    raw = llm_chat(
        client,
        model,
        system_prompt,
        user_content,
        1800,
        schema,
        "anki_card"
    )

    data = extract_json(
        raw
    )

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            "LLM returned invalid JSON:\n"
            + raw[:1000]
        )

    if ocr_correction:
        corrected_word = str(
            data.get(
                "corrected_word",
                ""
            )
        ).strip()

        corrected_context = str(
            data.get(
                "corrected_context",
                ""
            )
        ).strip()

        if not corrected_word:
            corrected_word = word

        if not corrected_context:
            corrected_context = context

    else:
        corrected_word = word
        corrected_context = context

    custom_data = data.get(
        "custom",
        {}
    )

    if not isinstance(
        custom_data,
        dict
    ):
        custom_data = {}

    result = {
        "source_language": source_language,
        "translation_language": translation_language,
        "corrected_word": corrected_word,
        "corrected_context": corrected_context,
        "front": str(
            data.get(
                "front",
                ""
            )
        ).strip(),
        "back": str(
            data.get(
                "back",
                ""
            )
        ).strip(),
        "example": clean_example(
            data.get(
                "example",
                ""
            )
        ),
        "tag": str(
            data.get(
                "tag",
                ""
            )
        ).strip().lower(),
        "custom": {}
    }

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

        if not field_id:
            continue

        result["custom"][field_id] = str(
            custom_data.get(
                field_id,
                ""
            )
        ).strip()

    if not result["front"]:
        raise RuntimeError(
            "LLM returned empty FRONT"
        )

    if not result["back"]:
        raise RuntimeError(
            "LLM returned empty BACK"
        )

    if (
        result["front"].casefold()
        == result["back"].casefold()
    ):
        raise RuntimeError(
            "LLM returned FRONT as BACK"
        )

    if result["tag"] not in ALLOWED_TAGS:
        raise RuntimeError(
            f"LLM returned invalid tag: "
            f"{result['tag']}"
        )

    if not validate_back_language(
        result["back"],
        translation_language
    ):
        print(
            "Card: BACK language check failed"
        )

        print(
            f"Card: expected BACK language = "
            f"{translation_language}"
        )

        print(
            f"Card: received BACK = "
            f"{result['back']}"
        )

        result["back"] = repair_back(
            client,
            model,
            source_language,
            translation_language,
            result["front"],
            result["back"]
        )

        if not validate_back_language(
            result["back"],
            translation_language
        ):
            raise RuntimeError(
                "BACK is still in the wrong language "
                f"after repair: {result['back']}"
            )

    print(
        f"Card: source language = "
        f"{source_language}"
    )

    print(
        f"Card: translation language = "
        f"{translation_language}"
    )

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

    back_name = get_configured_field_name(
        settings,
        "Back",
        model_fields
    )

    example_name = get_configured_field_name(
        settings,
        "Example",
        model_fields
    )

    core_names = [
        front_name,
        back_name,
        example_name
    ]

    if len(
        set(core_names)
    ) != len(
        core_names
    ):
        raise RuntimeError(
            "Front, Back and Example use duplicate Anki fields: "
            f"{core_names}"
        )

    fields = {
        front_name: card["front"],
        back_name: card["back"],
        example_name: card["example"]
    }

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


def parse_tags(tag_text):
    tag = str(
        tag_text
    ).strip().lower()

    if tag and tag != "auto":
        return [
            "auto",
            tag
        ]

    return [
        "auto"
    ]


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
        f"Card: audio input = "
        f"{audio_path or 'none'}"
    )

    try:
        settings = load_job_settings(
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

        client = get_llm_client(
            settings
        )

        model = get_model(
            settings
        )

        source_language = detect_source_language(
            client,
            model,
            word,
            context,
            profiles
        )

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
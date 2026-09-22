import os
import sys
import json
import uuid
import subprocess
import urllib.request
import urllib.error

from openai import OpenAI


ANKI_URL = "http://127.0.0.1:8765"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SETTINGS_PATH = os.path.join(
    BASE_DIR,
    "settings.json"
)

SUCCESS_SOUND = "/System/Library/Sounds/Funk.aiff"
ERROR_SOUND = "/System/Library/Sounds/Sosumi.aiff"
AFPLAY = "/usr/bin/afplay"

TRANSLATION_LANGUAGE = "English"

ALLOWED_TAGS = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "conjunction",
    "preposition",
    "pronoun",
    "determiner",
    "interjection",
    "phrase",
    "symbol",
    "math"
}


DEFAULT_PROMPT = """
You generate exactly one high-quality Anki vocabulary card.

The application provides:
- word: the target vocabulary item
- context: the text containing the target
- source language: the language being learned

The configured source language is authoritative.
The translation language is English.

Use the provided source language consistently.
Do not switch to another source language based on the conversation or context.

SOURCE WORD

Use the provided word as the only vocabulary target.

Convert the target to the standard dictionary form appropriate for the source language when this does not change its meaning.

Use the normal citation form of that language.

Preserve:
- fixed expressions;
- idioms;
- phrasal verbs;
- slang;
- compounds;
- other multi-word vocabulary items.

Do not replace the target with another word from the context.

FRONT

Return only the standard dictionary form or fixed expression.

FRONT must:
- stay in the source language;
- contain only the vocabulary item;
- contain no translation;
- contain no explanation;
- contain no labels;
- contain no pronunciation;
- contain no grammatical information.

BACK

Return exactly one natural English translation of FRONT.

Choose the meaning that best matches the provided context.

Prefer a natural translation over a literal translation when the context clearly requires it.

BACK must contain only the translation.

Do not include:
- synonyms;
- alternatives;
- multiple translations;
- slash-separated translations;
- explanations;
- examples;
- the original context;
- the source-language word;
- the field name.

Do not repeat FRONT as BACK.

EXAMPLE

Return one short, natural example in the source language that demonstrates the meaning of FRONT.

Prefer a suitable sentence from the provided context.

When the context contains a suitable complete sentence:
- reuse it;
- preserve its wording;
- do not translate it;
- do not rewrite it unnecessarily.

When the context is a fragment, incomplete, or otherwise unsuitable:
- create a short natural sentence in the source language;
- clearly demonstrate the intended meaning.

Do not create an unrelated example when the context already provides a suitable one.

Do not add a final period.

TAG

Return exactly one primary part-of-speech tag.

Allowed values:
noun
verb
adjective
adverb
conjunction
preposition
pronoun
determiner
interjection
phrase
symbol
math

Choose the tag according to the grammatical role of the target in context.

Do not use language names or language codes as tags.

CUSTOM FIELDS

The application may provide zero, one, or many custom fields.

Custom field names may be written in any language and may describe any kind of information.

For every configured custom field:

- Determine the intended purpose from its configured name.
- Generate only the information that belongs in that field.
- Keep the value concise and useful.
- Do not repeat FRONT, BACK, EXAMPLE, or TAG unless the field explicitly asks for one of them.
- Do not repeat information already present in another field unless the field requires it.
- Do not add explanations about what the field means.
- Do not add labels such as "Description:" or "Translation:" unless the field explicitly requires them.
- Follow an obvious format implied by the field name.
- Use the appropriate language for the requested content.
- Do not invent information that cannot be reliably determined.
- Do not fill a field with irrelevant text just to avoid leaving it empty.
- If the purpose of a field cannot be determined reliably, return an empty string.

Custom fields are dynamic.
Do not assume a fixed set of custom fields.
Do not assume that a field exists unless it is provided by the application.

CONTEXT

Use context to determine:
- the intended meaning;
- grammatical usage;
- the appropriate dictionary form;
- the example.

Only the provided word is the vocabulary target.

Do not treat other words from the context as additional targets.

Do not replace the target with another word from the context.

GENERAL

Apply language-specific grammar, morphology, capitalization, and pronunciation rules appropriate to the configured source language.

Keep every field concise.

Do not add information that does not belong to the field.

Do not invent facts, meanings, pronunciations, or context.

Use the context when it provides relevant information, but use normal language knowledge for dictionary form, grammar, and pronunciation.

Return only the structured card data.
""".strip()


def play_sound(success):
    sound_path = (
        SUCCESS_SOUND
        if success
        else ERROR_SOUND
    )

    if not os.path.exists(
        sound_path
    ):
        return

    try:
        subprocess.Popen(
            [
                AFPLAY,
                sound_path
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


def call_anki(
    action,
    params=None
):
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
                response.read().decode("utf-8")
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
            str(data["error"])
        )

    return data.get(
        "result"
    )


def get_llm_base_url(
    settings
):
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


def get_llm_client(
    settings
):
    return OpenAI(
        base_url=(
            get_llm_base_url(settings)
            + "/v1"
        ),
        api_key="lm-studio",
        timeout=90
    )


def get_source_language(
    settings
):
    language = str(
        settings.get(
            "language",
            "English"
        )
    ).strip()

    if not language:
        language = "English"

    return language


def get_model(
    settings
):
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
        get_llm_base_url(settings)
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
                response.read().decode("utf-8")
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


def extract_json(
    text
):
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
            text[start:end + 1]
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
        "OUTPUT FORMAT:\n"
        "Return exactly one JSON object and nothing else.\n"
        "Use exactly these top-level fields:\n"
        + json.dumps(
            list(
                response_schema.get(
                    "properties",
                    {}
                ).keys()
            ),
            ensure_ascii=False
        )
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


def as_bool(
    value
):
    if isinstance(
        value,
        bool
    ):
        return value

    return (
        str(value)
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on"
        }
    )


def validate_custom_fields(
    custom_fields
):
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


def build_custom_field_info(
    custom_fields
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

        instruction = (
            "Infer the intended content from the "
            "configured field name. Return only the "
            "value that belongs in this field. Keep "
            "it concise, relevant, and useful. Do "
            "not duplicate other card fields, do not "
            "add labels or explanations, and do not "
            "invent information. Follow any obvious "
            "format or language implied by the field name."
        )

        lines.append(
            f"{field_id} ({field_name}): "
            f"{instruction}"
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


def build_schema(
    custom_fields,
    include_correction
):
    (
        _,
        custom_properties,
        custom_required
    ) = build_custom_field_info(
        custom_fields
    )

    properties = {}
    required = []

    if include_correction:

        properties["corrected_word"] = {
            "type": "string",
            "description": (
                "The target word after correcting "
                "only obvious OCR errors."
            )
        }

        properties["corrected_context"] = {
            "type": "string",
            "description": (
                "The context after correcting "
                "only obvious OCR errors."
            )
        }

        required.extend(
            [
                "corrected_word",
                "corrected_context"
            ]
        )

    properties["front"] = {
        "type": "string",
        "description": (
            "The standard dictionary form or "
            "fixed expression in the source language."
        )
    }

    properties["back"] = {
        "type": "string",
        "description": (
            "Exactly one natural English translation "
            "of FRONT matching the context."
        )
    }

    properties["example"] = {
        "type": "string",
        "description": (
            "One short natural example in the source language."
        )
    }

    properties["tag"] = {
        "type": "string",
        "description": (
            "Exactly one allowed part-of-speech tag."
        )
    }

    properties["custom"] = {
        "type": "object",
        "properties": custom_properties,
        "required": custom_required,
        "additionalProperties": False
    }

    required.extend(
        [
            "front",
            "back",
            "example",
            "tag",
            "custom"
        ]
    )

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False
    }


def build_system_prompt(
    settings,
    custom_fields,
    ocr_correction
):
    source_language = (
        get_source_language(
            settings
        )
    )

    system_prompt = DEFAULT_PROMPT

    custom_prompt = str(
        settings.get(
            "prompt",
            ""
        )
    ).strip()

    if custom_prompt:
        system_prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS:\n"
            + custom_prompt
            + "\n\n"
            "Additional instructions may refine the "
            "content, but they must not change the "
            "configured source language, English "
            "translation language, required fields, "
            "or structured output format."
        )

    system_prompt += (
        "\n\n"
        "ACTIVE LANGUAGE CONFIGURATION:\n"
        f"Source language: {source_language}\n"
        f"Translation language: {TRANSLATION_LANGUAGE}"
    )

    (
        custom_lines,
        _,
        _
    ) = build_custom_field_info(
        custom_fields
    )

    if custom_lines:
        system_prompt += (
            "\n\n"
            "CONFIGURED CUSTOM FIELDS:\n"
            + "\n".join(
                custom_lines
            )
        )

    if ocr_correction:

        system_prompt += """
        
OCR CORRECTION

Correct only obvious OCR errors in the provided word and context.

Fix clear:
- incorrect characters;
- missing characters;
- duplicated characters;
- obvious spacing mistakes;
- obvious OCR spelling errors.

Do not:
- translate the text;
- paraphrase it;
- rewrite it stylistically;
- change its meaning;
- invent uncertain text.

Preserve the original source language and wording as closely as possible.

Use the corrected text for card generation.
""".strip()

    else:

        system_prompt += """
        
OCR CORRECTION

OCR correction is disabled.

Use the provided word and context exactly as supplied.
Do not correct, rewrite, normalize, or paraphrase them.

Generate the card directly from the provided text.
""".strip()

    return (
        system_prompt,
        source_language
    )


def clean_example(
    example
):
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


def generate_card(
    client,
    model,
    word,
    context,
    settings,
    custom_fields
):
    ocr_correction = as_bool(
        settings.get(
            "ocr_correction",
            False
        )
    )

    (
        system_prompt,
        source_language
    ) = build_system_prompt(
        settings,
        custom_fields,
        ocr_correction
    )

    print(
        f"Card: source language = "
        f"{source_language}"
    )

    print(
        f"Card: translation language = "
        f"{TRANSLATION_LANGUAGE}"
    )

    user_content = (
        "TARGET WORD:\n"
        + word
        + "\n\n"
        "CONTEXT:\n"
        + context
    )

    schema = build_schema(
        custom_fields,
        ocr_correction
    )

    raw = llm_chat(
        client,
        model,
        system_prompt,
        user_content,
        1400,
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
            "LLM returned invalid card JSON: "
            + raw[:500]
        )

    corrected_word = word
    corrected_context = context

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

    result = {
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

    custom_data = data.get(
        "custom",
        {}
    )

    if not isinstance(
        custom_data,
        dict
    ):
        custom_data = {}

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
            "LLM returned empty front"
        )

    if not result["back"]:
        raise RuntimeError(
            "LLM returned empty back"
        )

    if (
        result["front"]
        .strip()
        .casefold()
        ==
        result["back"]
        .strip()
        .casefold()
    ):
        raise RuntimeError(
            "LLM returned FRONT as BACK "
            "instead of an English translation"
        )

    if result["tag"] not in ALLOWED_TAGS:
        raise RuntimeError(
            f"LLM returned invalid tag: "
            f"{result['tag']}"
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
                f"Field setting "
                f"'{field_id}' is missing"
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
                f"Field '{field_id}' "
                f"has no configured name"
            )

        return None

    if name not in model_fields:
        raise RuntimeError(
            f"Configured Anki field "
            f"'{name}' for '{field_id}' "
            f"was not found. "
            f"Available: {model_fields}"
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
    ) != len(core_names):

        raise RuntimeError(
            "Front, Back and Example point "
            "to the same Anki field: "
            f"{core_names}"
        )

    fields = {
        front_name: card["front"],
        back_name: card["back"],
        example_name: card["example"]
    }

    reserved_names = set(
        core_names
    )

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

        if field_name in reserved_names:
            raise RuntimeError(
                f"Custom field "
                f"'{field_name}' "
                "conflicts with a core field"
            )

        if field_name not in model_fields:
            raise RuntimeError(
                f"Configured custom field "
                f"'{field_name}' was not found "
                f"in Anki. Available: "
                f"{model_fields}"
            )

        if field_name in fields:
            raise RuntimeError(
                f"Duplicate Anki field mapping: "
                f"'{field_name}'"
            )

        fields[field_name] = str(
            custom_values.get(
                field_id,
                ""
            )
        ).strip()

    return fields


def store_image(
    image_path
):
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
    image_path,
    reserved_names
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
        return

    if picture_name in reserved_names:
        raise RuntimeError(
            f"Picture field "
            f"'{picture_name}' conflicts "
            "with another configured field"
        )

    filename = store_image(
        image_path
    )

    if filename:
        fields[picture_name] = (
            f'<img src="{filename}">'
        )


def parse_tags(
    tag_text
):
    tag = str(
        tag_text
    ).strip().lower()

    if (
        tag
        and tag != "auto"
    ):
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
    image_path
):
    note_model = str(
        settings.get(
            "note_model",
            ""
        )
    ).strip()

    deck_name = str(
        settings.get(
            "deck",
            ""
        )
    ).strip()

    if not note_model:
        raise RuntimeError(
            "Setting 'note_model' is empty"
        )

    if not deck_name:
        raise RuntimeError(
            "Setting 'deck' is empty"
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

    reserved_names = set(
        fields.keys()
    )

    attach_image(
        fields,
        settings,
        model_fields,
        image_path,
        reserved_names
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

    check = call_anki(
        "canAddNotesWithErrorDetail",
        {
            "notes": [note]
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
            f"Invalid canAddNotes response: "
            f"{check}"
        )

    print(
        f"Card: can add = {check}"
    )

    if not check.get(
        "canAdd"
    ):
        error = (
            check.get("error")
            or "Anki rejected the note"
        )

        print(
            f"Card: not added = {error}"
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
        f"Card: added to Anki = "
        f"{note_id}"
    )

    return True


def main():
    try:
        payload = json.load(
            sys.stdin
        )

    except Exception as e:
        print(
            f"Card: input JSON error: {e}"
        )

        play_sound(False)

        return 1

    if not isinstance(
        payload,
        dict
    ):
        print(
            "Card: invalid input JSON"
        )

        play_sound(False)

        return 1

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

    if not word:
        print(
            "Card: empty word"
        )

        play_sound(False)

        return 1

    print(
        f"Card: input word = {word}"
    )

    print(
        f"Card: input context = {context}"
    )

    try:
        settings = load_settings()

        custom_fields = settings.get(
            "custom_fields",
            []
        )

        validate_custom_fields(
            custom_fields
        )

        client = get_llm_client(
            settings
        )

        model = get_model(
            settings
        )

        print(
            f"Card: custom fields = "
            f"{custom_fields}"
        )

        card = generate_card(
            client,
            model,
            word,
            context,
            settings,
            custom_fields
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
            image_path
        )

        play_sound(
            success
        )

        return (
            0
            if success
            else 1
        )

    except Exception as e:

        print(
            f"Card: ERROR: {e}"
        )

        play_sound(False)

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
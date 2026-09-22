import os
import json
import copy
import uuid

from webui import webui


DEFAULT_PROMPT = """
You generate exactly one high-quality Anki vocabulary card from a target word and its context.

The application provides the active source language and translation language. These settings are authoritative.

Use the target word as the vocabulary item. Use the context to determine its meaning and grammatical usage.

FRONT
Return the standard dictionary form of the target in the source language.

Use the normal dictionary form appropriate for the source language:
- verbs: standard dictionary form;
- nouns: standard citation form;
- adjectives: standard base form;
- other parts of speech: their normal dictionary form.

Do not change the form if doing so would change the meaning.

Keep fixed expressions, idioms, phrasal verbs, slang, and other multi-word vocabulary items intact.

FRONT contains only the vocabulary item in the source language.

BACK
Return exactly one natural translation of FRONT into the configured translation language.

Choose the meaning that best matches the context.

Do not return:
- the source word;
- multiple translations;
- synonyms;
- alternatives;
- explanations;
- examples;
- additional text.

EXAMPLE
Return one natural example in the source language that demonstrates the meaning of FRONT.

Prefer a suitable sentence or utterance from the provided context.

If the context contains a usable example, preserve its wording and do not translate it.

If the context is only a fragment or is not suitable as an example, create a short natural example based on the target meaning.

Do not include a final period.

DESCRIPTION
Return a short explanation of the meaning of FRONT in English.

Focus on the meaning relevant to the context.

Do not include:
- a translation;
- an example;
- a part-of-speech label;
- unnecessary dictionary information.

TRANSCRIPTION
Return the standard IPA pronunciation of FRONT using the pronunciation conventions of the source language.

Return only the IPA transcription.

If a reliable pronunciation cannot be determined, return an empty string.

TAG
Return exactly one primary grammatical tag.

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

CONTEXT
Use the provided context only to determine the target's meaning, grammatical usage, and example.

Only the provided word is the target vocabulary item.

Do not select another word from the context as FRONT.

GENERAL
Be accurate and concise.

Apply language-specific grammar, word forms, and pronunciation rules appropriate to the configured source language.

Do not mix source and translation languages within a field unless the content itself requires it.

Do not invent facts or meanings that are unsupported by the target and context.

Return only the structured card data.
""".strip()


win = webui.Window()


default_settings = {
    "fields": {
        "Front": {
            "name": "Front"
        },
        "Back": {
            "name": "Back"
        },
        "Example": {
            "name": "Example"
        },
        "Picture": {
            "name": "Picture"
        }
    },
    "custom_fields": [
        {
            "id": "custom_description",
            "name": "Description"
        },
        {
            "id": "custom_transcription",
            "name": "Transcription"
        }
    ],
    "language": "English",
    "hotkey": "cmd+shift+a",
    "ocr_languages": [
        "en"
    ],
    "prompt": DEFAULT_PROMPT,
    "deck": "Test",
    "note_model": "Базовый (ввод ответа)",
    "llm_url": "http://127.0.0.1:11434/v1",
    "llm_model": "",
    "ocr_correction": True
}


settings = {}
draft_settings = {}


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SETTINGS_PATH = os.path.join(
    BASE_DIR,
    "settings.json"
)


def load_settings():
    global settings

    settings = copy.deepcopy(
        default_settings
    )

    if not os.path.exists(
        SETTINGS_PATH
    ):
        print(
            "settings.json not found. Using default settings."
        )
        return

    try:
        with open(
            SETTINGS_PATH,
            "r",
            encoding="utf-8"
        ) as file:
            loaded = json.load(
                file
            )

    except Exception as e:
        print(
            f"Failed to load settings.json: {e}"
        )
        return

    if not isinstance(
        loaded,
        dict
    ):
        print(
            "Invalid settings.json. Using default settings."
        )
        return

    settings.update(
        loaded
    )

    if isinstance(
        loaded.get("fields"),
        dict
    ):
        settings["fields"] = copy.deepcopy(
            default_settings["fields"]
        )

        for field_id, field_data in loaded["fields"].items():
            if isinstance(
                field_data,
                dict
            ):
                settings["fields"][field_id] = copy.deepcopy(
                    field_data
                )

    else:
        settings["fields"] = copy.deepcopy(
            default_settings["fields"]
        )

    if isinstance(
        loaded.get("custom_fields"),
        list
    ):
        settings["custom_fields"] = copy.deepcopy(
            loaded["custom_fields"]
        )

    else:
        settings["custom_fields"] = copy.deepcopy(
            default_settings["custom_fields"]
        )

    if isinstance(
        settings.get("ocr_languages"),
        list
    ):
        languages = []

        for language in settings["ocr_languages"]:
            if not isinstance(
                language,
                str
            ):
                continue

            language = language.strip()

            if (
                language
                and language not in languages
            ):
                languages.append(
                    language
                )

        settings["ocr_languages"] = languages[:3]

        if not settings["ocr_languages"]:
            settings["ocr_languages"] = [
                "en"
            ]

    else:
        settings["ocr_languages"] = [
            "en"
        ]

    if (
        not isinstance(
            settings.get("language"),
            str
        )
        or not settings["language"].strip()
    ):
        settings["language"] = (
            default_settings["language"]
        )

    if (
        not isinstance(
            settings.get("hotkey"),
            str
        )
        or not settings["hotkey"].strip()
    ):
        settings["hotkey"] = (
            default_settings["hotkey"]
        )

    if (
        not isinstance(
            settings.get("prompt"),
            str
        )
        or not settings["prompt"].strip()
    ):
        settings["prompt"] = (
            default_settings["prompt"]
        )

    if not isinstance(
        settings.get("deck"),
        str
    ):
        settings["deck"] = (
            default_settings["deck"]
        )

    if (
        not isinstance(
            settings.get("note_model"),
            str
        )
        or not settings["note_model"].strip()
    ):
        settings["note_model"] = (
            default_settings["note_model"]
        )

    if (
        not isinstance(
            settings.get("llm_url"),
            str
        )
        or not settings["llm_url"].strip()
    ):
        settings["llm_url"] = (
            default_settings["llm_url"]
        )

    if not isinstance(
        settings.get("llm_model"),
        str
    ):
        settings["llm_model"] = (
            default_settings["llm_model"]
        )

    if not isinstance(
        settings.get("ocr_correction"),
        bool
    ):
        settings["ocr_correction"] = (
            default_settings["ocr_correction"]
        )

    print(
        "Loaded settings:",
        settings
    )


def save_settings():
    with open(
        SETTINGS_PATH,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            settings,
            file,
            ensure_ascii=False,
            indent=4
        )


def main():
    load_settings()

    draft_settings.clear()
    draft_settings.update(
        copy.deepcopy(
            settings
        )
    )

    win.set_root_folder(
        BASE_DIR
    )

    win.set_size(
        1440,
        900
    )

    win.bind("goToProperties", open_properties)
    win.bind("goToLanguages", open_language)
    win.bind("goToInformation", open_info)
    win.bind("Exit", appExit)
    win.bind("Save", appSave)
    win.bind("Reset", resetSettings)
    win.bind("editField", editField)
    win.bind("fieldChanged", fieldChanged)
    win.bind("ocrLanguagesChanged", ocrLanguagesChanged)
    win.bind("requestOcrLanguages", requestOcrLanguages)
    win.bind("languageChanged", language_changed)
    win.bind("settingChanged", settingChanged)
    win.bind("requestSettings", requestSettings)
    win.bind("addCustomField", addCustomField)
    win.bind("customFieldChanged", customFieldChanged)
    win.bind("deleteCustomField", deleteCustomField)
    win.bind("deckChanged", deck_changed)
    win.bind("hotkeyChanged", hotkey_changed)
    win.bind("hotkeyCaptureStarted", hotkey_capture_started)
    win.bind("hotkeyCaptureStopped", hotkey_capture_stopped)

    win.show(
        "main.html"
    )

    win.run("""
        setTimeout(() => {
            if (
                document.getElementById(
                    'inputDeck'
                )
            ) {
                webui.requestSettings();
            }
        }, 300);
    """)

    webui.wait()


def open_properties(event):
    print(
        "Opening Properties"
    )

    win.show(
        "main.html"
    )

    event.run_client("""
        setTimeout(() => {
            if (
                document.getElementById(
                    'inputDeck'
                )
            ) {
                webui.requestSettings();
            }
        }, 100);
    """)


def open_language(event):
    print(
        "Opening OCR Languages"
    )

    win.show(
        "languages.html"
    )


def requestOcrLanguages(event):
    values = draft_settings.get(
        "ocr_languages",
        [
            "en"
        ]
    )

    if not isinstance(
        values,
        list
    ):
        values = [
            "en"
        ]

    values = [
        value.strip()
        for value in values
        if isinstance(
            value,
            str
        )
        and value.strip()
    ]

    values = list(
        dict.fromkeys(
            values
        )
    )[:3]

    if not values:
        values = [
            "en"
        ]

    print(
        "Sending OCR languages to client:",
        values
    )

    event.run_client(
        "setSelectedLanguages(%s);"
        % json.dumps(
            values,
            ensure_ascii=False
        )
    )


def open_info(event):
    print(
        "Opening Information"
    )

    win.show(
        "information.html"
    )


def appExit(event):
    print(
        "Exit"
    )

    hotkey_capture_stopped(
        None
    )

    webui.exit()


def appSave(event):
    global settings

    print(
        "Saving settings"
    )

    print(
        "Draft:",
        draft_settings
    )

    settings = copy.deepcopy(
        draft_settings
    )

    save_settings()

    print(
        "Saved:",
        settings
    )

    hotkey_capture_stopped(
        None
    )

    webui.exit()


def requestSettings(event):
    data = copy.deepcopy(
        draft_settings
    )

    event.run_client(
        f"""
        const settings = {json.dumps(
            data,
            ensure_ascii=False
        )};

        const fields =
            settings.fields || {{}};


        Object.keys(fields).forEach(
            (fieldId) => {{

                const element =
                    document.getElementById(
                        'field-' + fieldId
                    );

                if (element) {{
                    element.textContent =
                        fields[fieldId].name || '';
                }}
            }}
        );


        const llmUrl =
            document.getElementById(
                'llmUrl'
            );

        const llmModel =
            document.getElementById(
                'llmModel'
            );

        const ocrCorrection =
            document.getElementById(
                'ocrCorrection'
            );

        const promptInput =
            document.getElementById(
                'promptInput'
            );

        const deckInput =
            document.getElementById(
                'inputDeck'
            );

        const hotkeyInput =
            document.getElementById(
                'hotkeyInput'
            );


        if (llmUrl) {{
            llmUrl.value =
                settings.llm_url || '';

            llmUrl.onblur =
                () => {{
                    webui.settingChanged(
                        'llm_url',
                        llmUrl.value
                    );
                }};
        }}


        if (llmModel) {{
            llmModel.value =
                settings.llm_model || '';

            llmModel.onblur =
                () => {{
                    webui.settingChanged(
                        'llm_model',
                        llmModel.value
                    );
                }};
        }}


        if (ocrCorrection) {{
            ocrCorrection.checked =
                !!settings.ocr_correction;

            ocrCorrection.onchange =
                () => {{
                    webui.settingChanged(
                        'ocr_correction',
                        ocrCorrection.checked
                    );
                }};
        }}


        if (promptInput) {{
            promptInput.value =
                settings.prompt || '';

            promptInput.onblur =
                () => {{
                    webui.settingChanged(
                        'prompt',
                        promptInput.value
                    );
                }};
        }}


        if (deckInput) {{

            const studyLanguage =
                String(
                    settings.language || ''
                ).trim();


            function applyStudyLanguage() {{

                document.querySelectorAll(
                    '.chip'
                ).forEach(
                    (chip) => {{

                        if (
                            chip.closest(
                                '#languages'
                            )
                        ) {{
                            return;
                        }}


                        const chipLanguage =
                            String(
                                chip.dataset.language
                                || chip.dataset.name
                                || chip.textContent
                                || ''
                            ).trim();

                        const chipCode =
                            String(
                                chip.dataset.code
                                || ''
                            ).trim();

                        let selected = (
                            chipLanguage ===
                            studyLanguage
                        );

                        if (
                            !selected
                            && chipCode
                        ) {{
                            selected =
                                chipCode ===
                                studyLanguage;
                        }}

                        chip.classList.toggle(
                            'selected',
                            selected
                        );


                        if (
                            chip.dataset.studyLanguageBound
                            !== 'true'
                        ) {{

                            chip.addEventListener(
                                'click',
                                () => {{

                                    let value =
                                        String(
                                            chip.dataset.language
                                            || chip.dataset.name
                                            || chip.textContent
                                            || ''
                                        ).trim();

                                    const code =
                                        String(
                                            chip.dataset.code
                                            || ''
                                        ).trim();


                                    if (
                                        !value
                                        && code
                                    ) {{
                                        value =
                                            code;
                                    }}


                                    if (
                                        value
                                    ) {{
                                        webui.languageChanged(
                                            value
                                        );
                                    }}
                                }}
                            );

                            chip.dataset.studyLanguageBound =
                                'true';
                        }}
                    }}
                );
            }}


            applyStudyLanguage();


            setTimeout(
                applyStudyLanguage,
                100
            );

            setTimeout(
                applyStudyLanguage,
                300
            );

            setTimeout(
                applyStudyLanguage,
                700
            );


            deckInput.value =
                settings.deck || '';


            deckInput.onblur =
                () => {{

                    const value =
                        deckInput.value.trim();

                    webui.deckChanged(
                        value
                    );
                }};


            deckInput.onkeydown =
                (event) => {{

                    if (
                        event.key === 'Enter'
                    ) {{
                        event.preventDefault();
                        deckInput.blur();
                    }}
                }};
        }}


        if (hotkeyInput) {{

            hotkeyInput.value =
                settings.hotkey || 'cmd+shift+a';

            hotkeyInput.dataset.capturing =
                'false';


            hotkeyInput.onclick =
                () => {{

                    hotkeyInput.dataset.capturing =
                        'true';

                    hotkeyInput.value =
                        'Press shortcut...';

                    webui.hotkeyCaptureStarted();
                }};


            hotkeyInput.onkeydown =
                (event) => {{

                    if (
                        hotkeyInput.dataset.capturing
                        !== 'true'
                    ) {{
                        return;
                    }}


                    event.preventDefault();
                    event.stopPropagation();


                    if (
                        event.key === 'Escape'
                    ) {{

                        hotkeyInput.dataset.capturing =
                            'false';

                        hotkeyInput.value =
                            settings.hotkey || 'cmd+shift+a';

                        webui.hotkeyCaptureStopped();

                        return;
                    }}


                    const parts = [];


                    if (event.metaKey) {{
                        parts.push(
                            'cmd'
                        );
                    }}

                    if (event.ctrlKey) {{
                        parts.push(
                            'ctrl'
                        );
                    }}

                    if (event.altKey) {{
                        parts.push(
                            'alt'
                        );
                    }}

                    if (event.shiftKey) {{
                        parts.push(
                            'shift'
                        );
                    }}


                    const key =
                        event.key.toLowerCase();


                    if (
                        key === 'meta'
                        || key === 'control'
                        || key === 'alt'
                        || key === 'shift'
                    ) {{
                        return;
                    }}


                    parts.push(
                        key
                    );


                    const shortcut =
                        parts.join('+');


                    hotkeyInput.value =
                        shortcut;

                    hotkeyInput.dataset.capturing =
                        'false';

                    webui.hotkeyChanged(
                        shortcut
                    );

                    webui.hotkeyCaptureStopped();
                }};
        }}


        if (
            typeof renderCustomFields ===
            'function'
        ) {{
            renderCustomFields(
                settings.custom_fields || []
            );
        }}
        """
    )


def resetSettings(event):
    global draft_settings

    draft_settings = copy.deepcopy(
        default_settings
    )

    print(
        "Settings reset to defaults"
    )

    requestSettings(
        event
    )


def editField(event):
    field_id = event.get_string_at(
        0
    )

    print(
        "Editing field:",
        field_id
    )

    event.run_client(
        f"""
        const field =
            document.getElementById(
                'field-{field_id}'
            );

        if (!field) return;


        field.contentEditable =
            'true';

        field.focus();


        field.onkeydown =
            (event) => {{

                if (
                    event.key === 'Enter'
                ) {{
                    event.preventDefault();
                    field.blur();
                }}
            }};


        field.onblur =
            () => {{

                const value =
                    field.textContent.trim();

                field.contentEditable =
                    'false';

                webui.fieldChanged(
                    {json.dumps(field_id)},
                    value
                );
            }};
        """
    )


def fieldChanged(event):
    field_id = event.get_string_at(
        0
    )

    value = event.get_string_at(
        1
    )

    draft_settings.setdefault(
        "fields",
        {}
    )

    draft_settings["fields"][field_id] = {
        "name": value
    }

    print(
        "Field changed:",
        field_id,
        "→",
        value
    )


def language_changed(event):
    value = event.get_string_at(
        0
    ).strip()

    if not value:
        return

    draft_settings["language"] = value

    print(
        "Study language changed:",
        value
    )


def ocrLanguagesChanged(event):
    try:
        languages = json.loads(
            event.get_string_at(
                0
            )
        )

    except Exception as e:
        print(
            f"Invalid OCR languages: {e}"
        )
        return

    if not isinstance(
        languages,
        list
    ):
        print(
            "Invalid OCR languages format"
        )
        return

    result = []

    for language in languages:
        if not isinstance(
            language,
            str
        ):
            continue

        language = language.strip()

        if (
            language
            and language not in result
        ):
            result.append(
                language
            )

    result = result[:3]

    if not result:
        result = [
            "en"
        ]

    draft_settings["ocr_languages"] = (
        result
    )

    print(
        "OCR languages changed:",
        result
    )


def settingChanged(event):
    key = event.get_string_at(
        0
    )

    value = event.get_string_at(
        1
    )

    try:
        value = json.loads(
            value
        )

    except Exception:
        pass

    draft_settings[key] = value

    print(
        "Setting changed:",
        key,
        "→",
        value
    )


def deck_changed(event):
    value = event.get_string_at(
        0
    ).strip()

    draft_settings["deck"] = value

    print(
        "Deck changed:",
        value
    )


def hotkey_changed(event):
    value = event.get_string_at(
        0
    ).strip()

    if not value:
        return

    draft_settings["hotkey"] = value

    print(
        "Hotkey changed:",
        value
    )


def hotkey_capture_started(event):
    print(
        "Hotkey capture started"
    )


def hotkey_capture_stopped(event):
    print(
        "Hotkey capture stopped"
    )


def addCustomField(event):
    field = {
        "id": "custom_" + uuid.uuid4().hex[:8],
        "name": "New field"
    }

    draft_settings.setdefault(
        "custom_fields",
        []
    )

    draft_settings["custom_fields"].append(
        field
    )

    print(
        "Custom field added:",
        field
    )

    event.run_client(
        f"""
        renderAddedCustomField(
            {json.dumps(
                field,
                ensure_ascii=False
            )}
        );
        """
    )


def customFieldChanged(event):
    field_id = event.get_string_at(
        0
    )

    value = event.get_string_at(
        1
    )

    for field in draft_settings.get(
        "custom_fields",
        []
    ):

        if field.get("id") == field_id:
            field["name"] = value
            break

    print(
        "Custom field changed:",
        field_id,
        "→",
        value
    )


def deleteCustomField(event):
    field_id = event.get_string_at(
        0
    )

    draft_settings["custom_fields"] = [
        field
        for field in draft_settings.get(
            "custom_fields",
            []
        )
        if field.get("id") != field_id
    ]

    print(
        "Custom field deleted:",
        field_id
    )


if __name__ == "__main__":
    main()
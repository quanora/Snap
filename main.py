import os
import json
import copy
import uuid

from webui import webui


DEFAULT_PROMPT = """
You create exactly ONE concise language-learning Anki card from a target and its context.

SOURCE LANGUAGE = language being learned.
TRANSLATION LANGUAGE = language used for BACK.

These are the actual settings for the current card. They are variable. Never replace them based on the conversation, context, or examples.

TARGET is the only vocabulary item being taught. Use CONTEXT to determine its meaning, grammatical role, example, and pronunciation. Correct only obvious OCR errors.

FRONT: only the vocabulary item being taught, in SOURCE LANGUAGE. Use the normal dictionary/base form for a single word when appropriate. Preserve fixed expressions, idioms, phrasal verbs, slang, compounds, and other multi-word lexical units.

BACK: exactly ONE concise natural translation of FRONT into TRANSLATION LANGUAGE. Translate FRONT itself, not the whole context or example. Use context only to determine the intended meaning. Do not add synonyms, alternatives, explanations, parentheses, examples, labels, or source-language text.

EXAMPLE: SOURCE LANGUAGE only. Reuse a usable sentence or phrase from CONTEXT and preserve its wording. Do not translate, paraphrase, expand, or invent another example when usable context exists. Remove only obvious OCR garbage or irrelevant surrounding text.

CUSTOM FIELDS: fill every configured field exactly once. Keep values concise and do not duplicate other fields.

For custom_description: write a short dictionary-style definition of FRONT in SOURCE LANGUAGE only. Do not repeat FRONT and do not mention the field, card, or context.

For custom_transcription: return ONLY the IPA pronunciation of FRONT in SOURCE LANGUAGE, using /slashes/. Never return normal spelling, square brackets, labels, or explanations.

For any other custom field: infer its purpose from the field name, return only the requested information, keep it concise, and avoid duplicating other fields. If its purpose is genuinely unclear, return an empty string.

TAG: return exactly one allowed tag.

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

Use phrase for a normal multi-word lexical expression, including phrasal verbs. Use idiom only when its meaning is not directly predictable from the individual words.

Return only the structured JSON object.
""".strip()


win = webui.Window()


AVAILABLE_LANGUAGES = [
    "English", "German", "French", "Spanish", "Italian",
    "Portuguese", "Russian", "Ukrainian", "Polish", "Dutch",
    "Czech", "Hungarian", "Romanian", "Turkish", "Swedish",
    "Norwegian", "Danish", "Finnish", "Greek", "Japanese",
    "Korean", "Chinese (Simplified)", "Chinese (Traditional)",
    "Thai", "Vietnamese", "Arabic", "Hebrew", "Indonesian",
    "Malay", "Slovak", "Bulgarian", "Croatian", "Serbian",
    "Slovenian", "Estonian", "Latvian", "Lithuanian"
]

MAX_LANGUAGE_PROFILES = 3


def default_profile_for_language(language):
    language = str(
        language or "English"
    ).strip()

    if language.lower() == "english":
        translation_language = "Russian"
    else:
        translation_language = "English"

    deck = (
        "All decks::Languages::"
        + language
        + "::Mining"
    )

    return {
        "translation_language": translation_language,
        "deck": deck
    }


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
        },
        "Audio": {
            "name": "Audio"
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

    "translation_language": "Russian",

    "deck": "All decks::Languages::English::Mining",

    "language_profiles": {
        "English": {
            "translation_language": "Russian",
            "deck": "All decks::Languages::English::Mining"
        }
    },


    "hotkey": "cmd+shift+a",

    "ocr_languages": [
        "en"
    ],

    "prompt": DEFAULT_PROMPT,

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


def ensure_language_profile(
    target_settings,
    language,
    fallback_translation=None,
    fallback_deck=None
):
    language = str(
        language or ""
    ).strip()

    if not language:
        language = "English"

    profiles = target_settings.setdefault(
        "language_profiles",
        {}
    )

    if not isinstance(
        profiles,
        dict
    ):
        profiles = {}
        target_settings["language_profiles"] = profiles

    profile = profiles.get(
        language
    )

    if not isinstance(
        profile,
        dict
    ):
        profile = default_profile_for_language(
            language
        )

        if (
            fallback_translation
            and str(fallback_translation).strip()
        ):
            profile["translation_language"] = (
                str(
                    fallback_translation
                ).strip()
            )

        if (
            fallback_deck
            and str(fallback_deck).strip()
        ):
            profile["deck"] = (
                str(
                    fallback_deck
                ).strip()
            )

        profiles[language] = profile

    if (
        not isinstance(
            profile.get(
                "translation_language"
            ),
            str
        )
        or not profile["translation_language"].strip()
    ):
        profile["translation_language"] = (
            default_profile_for_language(
                language
            )["translation_language"]
        )

    if (
        not isinstance(
            profile.get(
                "deck"
            ),
            str
        )
        or not profile["deck"].strip()
    ):
        profile["deck"] = (
            default_profile_for_language(
                language
            )["deck"]
        )

    return profile


def apply_language_profile(
    target_settings,
    language,
    fallback_translation=None,
    fallback_deck=None
):
    language = str(
        language or ""
    ).strip()

    if not language:
        language = "English"

    profile = ensure_language_profile(
        target_settings,
        language,
        fallback_translation,
        fallback_deck
    )

    target_settings["language"] = language

    target_settings["translation_language"] = (
        profile["translation_language"]
    )

    target_settings["deck"] = (
        profile["deck"]
    )

    return profile


def save_current_language_profile(
    target_settings
):
    language = str(
        target_settings.get(
            "language",
            ""
        )
    ).strip()

    if not language:
        return

    profile = ensure_language_profile(
        target_settings,
        language
    )

    translation_language = str(
        target_settings.get(
            "translation_language",
            ""
        )
    ).strip()

    deck = str(
        target_settings.get(
            "deck",
            ""
        )
    ).strip()

    if translation_language:
        profile["translation_language"] = (
            translation_language
        )

    if deck:
        profile["deck"] = deck


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

        apply_language_profile(
            settings,
            settings["language"]
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
                settings["fields"][field_id] = (
                    copy.deepcopy(
                        field_data
                    )
                )

    else:
        settings["fields"] = copy.deepcopy(
            default_settings["fields"]
        )

    if isinstance(
        loaded.get("custom_fields"),
        list
    ):
        settings["custom_fields"] = (
            copy.deepcopy(
                loaded["custom_fields"]
            )
        )

    else:
        settings["custom_fields"] = (
            copy.deepcopy(
                default_settings["custom_fields"]
            )
        )

    if isinstance(
        loaded.get("ocr_languages"),
        list
    ):
        languages = []

        for language in loaded["ocr_languages"]:

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

        settings["ocr_languages"] = (
            languages[:3]
        )

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
    else:
        settings["language"] = (
            settings["language"].strip()
        )

    if (
        not isinstance(
            settings.get("translation_language"),
            str
        )
        or not settings["translation_language"].strip()
    ):
        settings["translation_language"] = (
            default_settings["translation_language"]
        )
    else:
        settings["translation_language"] = (
            settings["translation_language"].strip()
        )

    if (
        not isinstance(
            settings.get("deck"),
            str
        )
        or not settings["deck"].strip()
    ):
        settings["deck"] = (
            default_settings["deck"]
        )
    else:
        settings["deck"] = (
            settings["deck"].strip()
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
    else:
        settings["hotkey"] = (
            settings["hotkey"].strip()
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
        settings.get("note_model"),
        str
    ) or not settings["note_model"].strip():

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
    else:
        settings["llm_url"] = (
            settings["llm_url"].strip()
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

    old_language = settings["language"]

    loaded_profiles = loaded.get(
        "language_profiles"
    )

    if isinstance(
        loaded_profiles,
        dict
    ):
        profiles = copy.deepcopy(
            loaded_profiles
        )

    else:
        profiles = {}

    settings["language_profiles"] = profiles

    if old_language not in profiles:
        ensure_language_profile(
            settings,
            old_language,
            settings.get(
                "translation_language"
            ),
            settings.get(
                "deck"
            )
        )

    for language, profile in list(
        settings["language_profiles"].items()
    ):
        if not isinstance(
            profile,
            dict
        ):
            settings["language_profiles"][language] = (
                default_profile_for_language(
                    language
                )
            )

    apply_language_profile(
        settings,
        old_language,
        settings.get(
            "translation_language"
        ),
        settings.get(
            "deck"
        )
    )

    print(
        "Loaded settings:",
        settings
    )


def save_settings():
    save_current_language_profile(
        settings
    )

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

    win.bind(
        "goToProperties",
        open_properties
    )


    win.bind(
        "goToInformation",
        open_info
    )

    win.bind(
        "Exit",
        appExit
    )

    win.bind(
        "Save",
        appSave
    )

    win.bind(
        "Reset",
        resetSettings
    )

    win.bind(
        "editField",
        editField
    )

    win.bind(
        "fieldChanged",
        fieldChanged
    )

    win.bind(
        "ocrLanguagesChanged",
        ocrLanguagesChanged
    )

    win.bind(
        "requestOcrLanguages",
        requestOcrLanguages
    )

    win.bind(
        "languageChanged",
        language_changed
    )

    win.bind(
        "settingChanged",
        settingChanged
    )

    win.bind(
        "requestSettings",
        requestSettings
    )

    win.bind(
        "requestLanguageProfiles",
        requestLanguageProfiles
    )

    win.bind(
        "addLanguageProfile",
        addLanguageProfile
    )

    win.bind(
        "removeLanguageProfile",
        removeLanguageProfile
    )

    win.bind(
        "profileFieldChanged",
        profileFieldChanged
    )

    win.bind(
        "noteTypeChanged",
        noteTypeChanged
    )

    win.bind(
        "addCustomField",
        addCustomField
    )

    win.bind(
        "customFieldChanged",
        customFieldChanged
    )

    win.bind(
        "deleteCustomField",
        deleteCustomField
    )

    win.bind(
        "deckChanged",
        deck_changed
    )

    win.bind(
        "hotkeyChanged",
        hotkey_changed
    )

    win.bind(
        "hotkeyCaptureStarted",
        hotkey_capture_started
    )

    win.bind(
        "hotkeyCaptureStopped",
        hotkey_capture_stopped
    )

    win.show(
        "main.html"
    )

    win.run(
        """
        setTimeout(() => {
            if (
                document.getElementById(
                    'inputDeck'
                ) || document.getElementById(
                    'noteType'
                )
            ) {
                webui.requestSettings();
            }
        }, 300);
        """
    )

    webui.wait()


def open_properties(event):
    print(
        "Opening Properties"
    )

    win.show(
        "main.html"
    )

    event.run_client(
        """
        setTimeout(() => {
            if (
                document.getElementById(
                    'inputDeck'
                ) || document.getElementById(
                    'noteType'
                )
            ) {
                webui.requestSettings();
            }
        }, 100);
        """
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

    save_current_language_profile(
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
        const settings =
            {json.dumps(
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

        const translationLanguageInput =
            document.getElementById(
                'translationLanguage'
            );


        const noteTypeInput =
            document.getElementById(
                'noteType'
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

            ocrCorrection.type =
                'checkbox';

            ocrCorrection.checked =
                !!settings.ocr_correction;

            ocrCorrection.setAttribute(
                'aria-label',
                'OCR correction'
            );

            ocrCorrection.classList.add(
                'snap-ocr-toggle'
            );

            if (
                !document.getElementById(
                    'snap-ocr-toggle-style'
                )
            ) {{

                const style =
                    document.createElement(
                        'style'
                    );

                style.id =
                    'snap-ocr-toggle-style';

                style.textContent = `
                    .snap-ocr-toggle {{
                        appearance: none;
                        -webkit-appearance: none;
                        width: 44px;
                        height: 24px;
                        padding: 0;
                        margin: 0;
                        border: 0;
                        border-radius: 999px;
                        background: #c7c7c7;
                        position: relative;
                        cursor: pointer;
                        vertical-align: middle;
                        transition: background 0.15s ease;
                    }}

                    .snap-ocr-toggle::after {{
                        content: "";
                        position: absolute;
                        width: 20px;
                        height: 20px;
                        top: 2px;
                        left: 2px;
                        border-radius: 50%;
                        background: white;
                        box-shadow:
                            0 1px 3px rgba(0,0,0,0.25);
                        transition:
                            transform 0.15s ease;
                    }}

                    .snap-ocr-toggle:checked {{
                        background: #34c759;
                    }}

                    .snap-ocr-toggle:checked::after {{
                        transform:
                            translateX(20px);
                    }}
                `;

                document.head.appendChild(
                    style
                );
            }}

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


        if (translationLanguageInput) {{

            translationLanguageInput.value =
                settings.translation_language
                || '';

            translationLanguageInput.onblur =
                () => {{
                    webui.settingChanged(
                        'translation_language',
                        translationLanguageInput.value.trim()
                    );
                }};

            translationLanguageInput.onkeydown =
                (event) => {{

                    if (
                        event.key === 'Enter'
                    ) {{
                        event.preventDefault();

                        translationLanguageInput.blur();
                    }}
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

                        let selected =
                            chipLanguage ===
                            studyLanguage;

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

                    webui.deckChanged(
                        deckInput.value.trim()
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
                settings.hotkey
                || 'cmd+shift+a';

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
                            settings.hotkey
                            || 'cmd+shift+a';

                        webui.hotkeyCaptureStopped();

                        return;
                    }}


                    const parts = [];


                    if (
                        event.metaKey
                    ) {{
                        parts.push(
                            'cmd'
                        );
                    }}

                    if (
                        event.ctrlKey
                    ) {{
                        parts.push(
                            'ctrl'
                        );
                    }}

                    if (
                        event.altKey
                    ) {{
                        parts.push(
                            'alt'
                        );
                    }}

                    if (
                        event.shiftKey
                    ) {{
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


        if (noteTypeInput) {{

            noteTypeInput.value =
                settings.note_model || '';

            noteTypeInput.onblur =
                () => {{
                    webui.noteTypeChanged(
                        noteTypeInput.value.trim()
                    );
                }};

            noteTypeInput.onkeydown =
                (event) => {{
                    if (event.key === 'Enter') {{
                        event.preventDefault();
                        noteTypeInput.blur();
                    }}
                }};
        }}


        if (
            typeof renderCustomFields
            === 'function'
        ) {{

            renderCustomFields(
                settings.custom_fields || []
            );
        }}

        webui.requestLanguageProfiles();
        """
    )


def noteTypeChanged(event):
    value = event.get_string_at(0).strip()

    if not value:
        print("NOTE TYPE: empty value ignored")
        return

    draft_settings["note_model"] = value

    print(
        "NOTE TYPE CHANGED:",
        value
    )


def profileFieldChanged(event):
    language = event.get_string_at(0).strip()
    field = event.get_string_at(1).strip()
    value = event.get_string_at(2).strip()

    if not language or not field:
        return

    profiles = draft_settings.setdefault(
        "language_profiles",
        {}
    )

    if not isinstance(profiles, dict):
        profiles = {}
        draft_settings["language_profiles"] = profiles

    profile = ensure_language_profile(
        draft_settings,
        language
    )

    if field == "translation_language":
        if not value:
            return
        profile["translation_language"] = value

        if draft_settings.get("language") == language:
            draft_settings["translation_language"] = value

    elif field == "deck":
        if not value:
            return
        profile["deck"] = value

        if draft_settings.get("language") == language:
            draft_settings["deck"] = value

    print(
        "PROFILE FIELD CHANGED:",
        language,
        field,
        value
    )


def addLanguageProfile(event):
    language = event.get_string_at(0).strip()

    if not language:
        return

    profiles = draft_settings.setdefault(
        "language_profiles",
        {}
    )

    if not isinstance(profiles, dict):
        profiles = {}
        draft_settings["language_profiles"] = profiles

    if language in profiles:
        return

    if len(profiles) >= MAX_LANGUAGE_PROFILES:
        print("LANGUAGE PROFILE LIMIT REACHED")
        return

    profiles[language] = default_profile_for_language(
        language
    )

    print(
        "LANGUAGE PROFILE ADDED:",
        language
    )

    event.run_client(
        "webui.requestLanguageProfiles();"
    )


def removeLanguageProfile(event):
    language = event.get_string_at(0).strip()

    if not language:
        return

    profiles = draft_settings.get(
        "language_profiles",
        {}
    )

    if not isinstance(profiles, dict):
        return

    if len(profiles) <= 1:
        print("Cannot remove the last language profile")
        return

    if language not in profiles:
        return

    del profiles[language]

    if draft_settings.get("language") == language:
        next_language = next(iter(profiles))
        apply_language_profile(
            draft_settings,
            next_language
        )

    print(
        "LANGUAGE PROFILE REMOVED:",
        language
    )

    event.run_client(
        "webui.requestSettings();"
    )


def requestLanguageProfiles(event):
    profiles = draft_settings.get("language_profiles", {})

    if not isinstance(profiles, dict):
        profiles = {}

    print("REQUEST LANGUAGE PROFILES")
    print("Profiles:", profiles)

    data = {
        "profiles": copy.deepcopy(profiles),
        "languages": AVAILABLE_LANGUAGES,
        "maximum": MAX_LANGUAGE_PROFILES
    }

    script = """
(() => {
    const data = %s;
    const profiles = data.profiles || {};
    const languages = data.languages || [];
    const maximum = Number(data.maximum || 3);

    const profileContainer = document.getElementById("languageProfiles");
    const optionsContainer = document.getElementById("languageOptions");
    const searchInput = document.getElementById("languageSearch");

    if (!profileContainer || !optionsContainer) {
        console.error("SNAP: language profile containers not found");
        return;
    }

    if (searchInput) {
        searchInput.readOnly = false;
        searchInput.disabled = false;
        searchInput.removeAttribute("readonly");
        searchInput.removeAttribute("disabled");
    }

    const placeholder = profileContainer.previousElementSibling;

    if (placeholder && placeholder.querySelector && placeholder.querySelector("img[src*='MinusCircle']")) {
        placeholder.remove();
    }

    profileContainer.innerHTML = "";
    optionsContainer.innerHTML = "";

    optionsContainer.style.display = "flex";
    optionsContainer.style.flexWrap = "wrap";
    optionsContainer.style.alignItems = "center";
    optionsContainer.style.gap = "8px";

    function makeText(value, size, weight) {
        const element = document.createElement("div");
        element.textContent = value || "";
        element.style.color = "black";
        element.style.fontSize = size + "px";
        element.style.fontFamily = "Inter, sans-serif";
        element.style.fontWeight = weight;
        element.style.lineHeight = "1.35";
        element.style.wordWrap = "break-word";
        element.style.overflowWrap = "anywhere";
        element.style.wordBreak = "break-word";
        return element;
    }

    function makeIcon(src) {
        const wrapper = document.createElement("div");
        wrapper.style.position = "relative";
        wrapper.style.width = "28px";
        wrapper.style.height = "28px";
        wrapper.style.flex = "0 0 28px";
        wrapper.style.cursor = "pointer";

        const icon = document.createElement("img");
        icon.src = src;
        icon.width = 28;
        icon.height = 28;
        icon.draggable = false;

        wrapper.appendChild(icon);
        return wrapper;
    }

    function makeEditableRow(label, value, field, language) {
        const row = document.createElement("div");

        row.style.alignSelf = "stretch";
        row.style.paddingTop = "8px";
        row.style.paddingBottom = "8px";
        row.style.borderBottom = "1px rgba(0, 0, 0, 0.10) solid";
        row.style.justifyContent = "center";
        row.style.alignItems = "flex-start";
        row.style.gap = "16px";
        row.style.display = "flex";
        row.style.boxSizing = "border-box";
        row.style.minWidth = "0";

        const labelElement = makeText(label, 24, 400);
        labelElement.style.width = "130px";
        labelElement.style.flex = "0 0 130px";
        labelElement.style.color = "#666666";

        const right = document.createElement("div");
        right.style.flex = "1 1 0";
        right.style.width = "0";
        right.style.minWidth = "0";
        right.style.display = "flex";
        right.style.alignItems = "flex-start";
        right.style.justifyContent = "flex-start";
        right.style.overflow = "hidden";
        right.style.gap = "6px";

        const valueElement = makeText(value, 24, 500);
        valueElement.style.flex = "0 1 auto";
        valueElement.style.minWidth = "0";
        valueElement.style.maxWidth = "calc(100%% - 34px)";
        valueElement.style.whiteSpace = "nowrap";
        valueElement.style.overflow = "hidden";
        valueElement.style.textOverflow = "ellipsis";
        valueElement.style.wordWrap = "normal";
        valueElement.style.overflowWrap = "normal";
        valueElement.style.wordBreak = "normal";

        const editWrapper = makeIcon("assets/img/PencilSimple.svg");
        editWrapper.style.marginTop = "1px";

        function startEditing() {
            valueElement.contentEditable = "true";
            valueElement.style.flex = "1 1 auto";
            valueElement.style.maxWidth = "none";
            valueElement.style.whiteSpace = "normal";
            valueElement.style.overflow = "visible";
            valueElement.style.textOverflow = "clip";
            valueElement.style.wordWrap = "break-word";
            valueElement.style.overflowWrap = "anywhere";
            valueElement.style.wordBreak = "break-word";

            valueElement.focus();

            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(valueElement);
            selection.removeAllRanges();
            selection.addRange(range);

            valueElement.onkeydown = (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    valueElement.contentEditable = "false";
                    valueElement.blur();
                }
            };

            valueElement.onblur = () => {
                const newValue = valueElement.textContent.trim();

                valueElement.contentEditable = "false";
                valueElement.style.flex = "0 1 auto";
                valueElement.style.maxWidth = "calc(100%% - 34px)";
                valueElement.style.whiteSpace = "nowrap";
                valueElement.style.overflow = "hidden";
                valueElement.style.textOverflow = "ellipsis";
                valueElement.style.wordWrap = "normal";
                valueElement.style.overflowWrap = "normal";
                valueElement.style.wordBreak = "normal";
                valueElement.onkeydown = null;
                valueElement.onblur = null;

                webui.profileFieldChanged(
                    language,
                    field,
                    newValue
                );
            };
        }

        editWrapper.addEventListener("click", (event) => {
            event.stopPropagation();
            startEditing();
        });

        valueElement.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        right.appendChild(valueElement);
        right.appendChild(editWrapper);
        row.appendChild(labelElement);
        row.appendChild(right);

        return row;
    }

    function makeLanguageRow(language) {
        const row = document.createElement("div");

        row.style.alignSelf = "stretch";
        row.style.paddingTop = "8px";
        row.style.paddingBottom = "8px";
        row.style.borderBottom = "1px rgba(0, 0, 0, 0.10) solid";
        row.style.justifyContent = "center";
        row.style.alignItems = "flex-start";
        row.style.gap = "16px";
        row.style.display = "flex";
        row.style.boxSizing = "border-box";
        row.style.minWidth = "0";

        const labelElement = makeText("Language", 24, 400);
        labelElement.style.width = "130px";
        labelElement.style.flex = "0 0 130px";
        labelElement.style.color = "#666666";

        const valueElement = makeText(language, 24, 500);
        valueElement.style.flex = "1 1 0";
        valueElement.style.minWidth = "0";
        valueElement.style.wordWrap = "break-word";

        row.appendChild(labelElement);
        row.appendChild(valueElement);
        return row;
    }

    Object.entries(profiles).forEach(([language, profile]) => {
        profile = profile || {};

        const card = document.createElement("div");
        card.className = "language-profile";
        card.dataset.language = language;
        card.style.alignSelf = "stretch";
        card.style.padding = "8px";
        card.style.background = "#FAFAFA";
        card.style.justifyContent = "center";
        card.style.alignItems = "flex-start";
        card.style.gap = "12px";
        card.style.display = "flex";
        card.style.boxSizing = "border-box";
        card.style.minWidth = "0";

        const removeColumn = document.createElement("div");
        removeColumn.style.width = "28px";
        removeColumn.style.flex = "0 0 28px";
        removeColumn.style.paddingTop = "8px";
        removeColumn.style.paddingBottom = "8px";
        removeColumn.style.justifyContent = "center";
        removeColumn.style.alignItems = "flex-start";
        removeColumn.style.display = "flex";

        const removeWrapper = makeIcon("assets/img/MinusCircle.svg");
        const isLastProfile = Object.keys(profiles).length <= 1;

        if (isLastProfile) {
            removeWrapper.style.opacity = "0.25";
            removeWrapper.style.cursor = "default";
            removeWrapper.style.pointerEvents = "none";
        } else {
            removeWrapper.addEventListener("click", (event) => {
                event.stopPropagation();
                webui.removeLanguageProfile(language);
            });
        }

        removeColumn.appendChild(removeWrapper);

        const content = document.createElement("div");
        content.style.flex = "1 1 0";
        content.style.minWidth = "0";
        content.style.flexDirection = "column";
        content.style.display = "flex";

        const languageRow = makeLanguageRow(language);
        const translationRow = makeEditableRow("Translation", profile.translation_language, "translation_language", language);
        const deckRow = makeEditableRow("Deck", profile.deck, "deck", language);
        deckRow.style.borderBottom = "0";

        content.appendChild(languageRow);
        content.appendChild(translationRow);
        content.appendChild(deckRow);

        card.appendChild(removeColumn);
        card.appendChild(content);
        profileContainer.appendChild(card);
    });

    const usedLanguages = new Set(Object.keys(profiles));
    const profileCount = Object.keys(profiles).length;

    const popularLanguages = [
        "English",
        "German",
        "French",
        "Spanish",
        "Italian",
        "Portuguese",
        "Russian",
        "Ukrainian",
        "Japanese",
        "Korean",
        "Chinese (Simplified)",
        "Chinese (Traditional)"
    ];

    const popularSet = new Set(popularLanguages);

    const popularAvailable = languages.filter((language) => popularSet.has(language) && !usedLanguages.has(language));
    const otherAvailable = languages.filter((language) => !popularSet.has(language) && !usedLanguages.has(language));

    function createLanguageButton(language) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "language-option";
        button.dataset.language = language;
        button.textContent = language;
        button.style.paddingLeft = "16px";
        button.style.paddingRight = "16px";
        button.style.paddingTop = "4px";
        button.style.paddingBottom = "4px";
        button.style.background = "#F2F2F2";
        button.style.border = "0";
        button.style.borderRadius = "8px";
        button.style.color = "black";
        button.style.fontSize = "24px";
        button.style.fontFamily = "Inter, sans-serif";
        button.style.fontWeight = "400";
        button.style.lineHeight = "1.2";
        button.style.cursor = profileCount >= maximum ? "default" : "pointer";

        if (profileCount >= maximum) {
            button.style.opacity = "0.45";
        }

        button.addEventListener("click", () => {
            if (Object.keys(profiles).length >= maximum) {
                return;
            }
            webui.addLanguageProfile(language);
        });

        return button;
    }

    popularAvailable.forEach((language) => {
        optionsContainer.appendChild(createLanguageButton(language));
    });

    const otherButtons = [];

    otherAvailable.forEach((language) => {
        const button = createLanguageButton(language);
        button.classList.add("other-language");
        button.style.display = "none";
        otherButtons.push(button);
        optionsContainer.appendChild(button);
    });

    const showMoreButton = document.createElement("button");
    showMoreButton.type = "button";
    showMoreButton.textContent = "Show more";
    showMoreButton.style.flexBasis = "100%%";
    showMoreButton.style.width = "fit-content";
    showMoreButton.style.marginTop = "0";
    showMoreButton.style.padding = "4px 0";
    showMoreButton.style.background = "transparent";
    showMoreButton.style.border = "0";
    showMoreButton.style.color = "#666666";
    showMoreButton.style.fontSize = "20px";
    showMoreButton.style.fontFamily = "Inter, sans-serif";
    showMoreButton.style.fontWeight = "400";
    showMoreButton.style.textAlign = "left";
    showMoreButton.style.cursor = "pointer";

    let expanded = false;

    function updateLanguageVisibility() {
        otherButtons.forEach((button) => {
            button.style.display = expanded ? "inline-flex" : "none";
        });
        showMoreButton.textContent = expanded ? "Show less" : "Show more";
    }

    showMoreButton.addEventListener("click", () => {
        expanded = !expanded;
        updateLanguageVisibility();
    });

    if (otherAvailable.length > 0) {
        optionsContainer.appendChild(showMoreButton);
    }

    function filterLanguages() {
        const query = searchInput ? searchInput.value.trim().toLowerCase() : "";
        const popularButtons = optionsContainer.querySelectorAll(".language-option:not(.other-language)");

        if (query) {
            popularButtons.forEach((button) => {
                const language = String(button.dataset.language || "").toLowerCase();
                button.style.display = language.includes(query) ? "inline-flex" : "none";
            });

            otherButtons.forEach((button) => {
                const language = String(button.dataset.language || "").toLowerCase();
                button.style.display = language.includes(query) ? "inline-flex" : "none";
            });

            showMoreButton.style.display = "none";
            return;
        }

        popularButtons.forEach((button) => {
            button.style.display = "inline-flex";
        });

        otherButtons.forEach((button) => {
            button.style.display = expanded ? "inline-flex" : "none";
        });

        showMoreButton.style.display = otherAvailable.length > 0 ? "block" : "none";
    }

    if (searchInput) {
        searchInput.oninput = filterLanguages;
    }

    filterLanguages();

    console.log(
        "SNAP: language profiles rendered:",
        Object.keys(profiles),
        "popular:",
        popularAvailable.length,
        "other:",
        otherAvailable.length
    );
})();
""" % json.dumps(data, ensure_ascii=False)

    event.run_client(script)


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
                    {json.dumps(
                        field_id
                    )},
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

    old_translation = (
        draft_settings.get(
            "translation_language"
        )
    )

    old_deck = (
        draft_settings.get(
            "deck"
        )
    )

    save_current_language_profile(
        draft_settings
    )

    profile = apply_language_profile(
        draft_settings,
        value
    )

    if (
        not profile.get(
            "translation_language"
        )
    ):
        profile["translation_language"] = (
            old_translation
            or "English"
        )

    if (
        not profile.get(
            "deck"
        )
    ):
        profile["deck"] = (
            old_deck
            or (
                "All decks::Languages::"
                + value
                + "::Mining"
            )
        )

    draft_settings["translation_language"] = (
        profile["translation_language"]
    )

    draft_settings["deck"] = (
        profile["deck"]
    )

    print(
        "Study language changed:",
        value
    )

    print(
        "Translation language:",
        draft_settings[
            "translation_language"
        ]
    )

    print(
        "Deck:",
        draft_settings[
            "deck"
        ]
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

    if key == "translation_language":

        save_current_language_profile(
            draft_settings
        )

        language = str(
            draft_settings.get(
                "language",
                ""
            )
        ).strip()

        profile = ensure_language_profile(
            draft_settings,
            language
        )

        profile["translation_language"] = (
            str(
                value
            ).strip()
        )

    if key == "prompt":

        print(
            "Custom prompt updated."
        )

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

    language = str(
        draft_settings.get(
            "language",
            ""
        )
    ).strip()

    profile = ensure_language_profile(
        draft_settings,
        language
    )

    profile["deck"] = value

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
        "id": (
            "custom_"
            + uuid.uuid4().hex[:8]
        ),
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

        if field.get(
            "id"
        ) == field_id:

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
        if field.get(
            "id"
        ) != field_id
    ]

    print(
        "Custom field deleted:",
        field_id
    )


if __name__ == "__main__":
    main()
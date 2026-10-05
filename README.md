<img width="3852" height="904" alt="image" src="https://github.com/user-attachments/assets/c2ea8596-5cb7-40c6-a18e-3ab088826c35" />

# Snap (BETA)
This is an add-on for Anki, which makes the process of creating cards faster while watching videos in a foreign language. You don't need to take multiple screenshots and search for information. It will capture information from your screen.

The example of a card. The quality mostly depends on what model and prompt you are using. The results is not very stable
<img width="1291" height="668" alt="image" src="https://github.com/user-attachments/assets/0fa52a5d-4ba7-4b58-8482-89757d8f270b" />


# How does this work?
Hotkey (Cmd+Shift+A) → Screen Capture (SCK) & screenshot → Word Selection (screencapture -i -s) → Apple Vision OCR → Context: subtitle from screen.swift (history/cache) or fallback to line OCR → Audio: audio.swift SELECT by timestamp → circular buffer clip → card_queue → LLM Processing & Card Generation (Lang detection → LLM formatting via LM Studio & JSON schema → Target language validation & retry) → AnkiConnect Export (attachments & addNote) → Anki.

https://github.com/user-attachments/assets/b5fad899-94e0-4c48-848d-cff26ad6a35e


# Where are the settings?
Tools → Snap

<img width="700" height="307" alt="image" src="https://github.com/user-attachments/assets/c2f308f2-ccff-4fc9-9cf8-03110a815881" />


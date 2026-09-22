const languages = [
    { name: "English", code: "en" },
    { name: "German", code: "de" },
    { name: "Russian", code: "ru" },
    { name: "Spanish", code: "es" },
    { name: "French", code: "fr" },
    { name: "Italian", code: "it" },
    { name: "Portuguese", code: "pt" },
    { name: "Chinese Simplified", code: "ch_sim" },
    { name: "Chinese Traditional", code: "ch_tra" },
    { name: "Japanese", code: "ja" },
    { name: "Korean", code: "ko" },
    { name: "Dutch", code: "nl" },
    { name: "Polish", code: "pl" },
    { name: "Czech", code: "cs" },
    { name: "Hungarian", code: "hu" },
    { name: "Romanian", code: "ro" },
    { name: "Swedish", code: "sv" },
    { name: "Danish", code: "da" },
    { name: "Norwegian", code: "no" },
    { name: "Finnish", code: "fi" },
    { name: "Turkish", code: "tr" },
    { name: "Ukrainian", code: "uk" },
    { name: "Greek", code: "el" },
    { name: "Hebrew", code: "he" },
    { name: "Arabic", code: "ar" }
];

const container = document.getElementById("languages");
const search = document.getElementById("languageSearch");

const selectedLanguages = new Set();


function renderLanguages(filter = "") {
    container.innerHTML = "";

    const query = filter.toLowerCase().trim();

    languages
        .filter(language =>
            language.name.toLowerCase().includes(query)
        )
        .forEach(language => {
            const chip = document.createElement("div");

            chip.className = "chip";
            chip.textContent = language.name;
            chip.dataset.code = language.code;

            if (selectedLanguages.has(language.code)) {
                chip.classList.add("selected");
            }

            chip.onclick = () => {
                if (selectedLanguages.has(language.code)) {
                    selectedLanguages.delete(language.code);
                    chip.classList.remove("selected");
                } else {
                    if (selectedLanguages.size >= 3) {
                        return;
                    }

                    selectedLanguages.add(language.code);
                    chip.classList.add("selected");
                }

                webui.ocrLanguagesChanged(
                    JSON.stringify(
                        Array.from(selectedLanguages)
                    )
                );
            };

            container.appendChild(chip);
        });
}


function setSelectedLanguages(values) {
    selectedLanguages.clear();

    if (!Array.isArray(values)) {
        renderLanguages(search.value);
        return;
    }

    values.forEach(code => {
        if (
            languages.some(
                language => language.code === code
            )
        ) {
            selectedLanguages.add(code);
        }
    });

    renderLanguages(search.value);
}


search.addEventListener(
    "input",
    () => renderLanguages(search.value)
);


renderLanguages();


setTimeout(() => {
    webui.requestOcrLanguages();
}, 100);
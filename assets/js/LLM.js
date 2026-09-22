function initLLMSettings() {
    const llmUrl = document.getElementById("llmUrl");

    if (llmUrl) {
        const saveLLMUrl = () => {
            webui.settingChanged(
                "llm_url",
                llmUrl.value
            );
        };

        llmUrl.addEventListener("blur", () => {
            saveLLMUrl();
        });

        llmUrl.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                saveLLMUrl();
                llmUrl.blur();
            }
        });
    }

    const llmModel = document.getElementById("llmModel");
    const ocrCorrection = document.getElementById("ocrCorrection");

}

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initLLMSettings
    );
} else {
    initLLMSettings();
}
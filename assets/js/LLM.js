function snapUpdateLLMVisibility() {
    const useLlm = document.getElementById('useLlm');
    const llmFields = document.getElementById('llmFields');
    const disabledMessage = document.getElementById('llmDisabledMessage');
    const promptCard = document.getElementById('deckInput-2');

    const enabled = !useLlm || useLlm.checked;

    if (llmFields) {
        llmFields.style.display = enabled ? 'flex' : 'none';
    }

    if (disabledMessage) {
        disabledMessage.style.display = enabled ? 'none' : 'flex';
    }

    if (promptCard) {
        promptCard.style.setProperty(
            'display',
            enabled ? 'flex' : 'none',
            'important'
        );
    }
}


function snapWatchLLMCheckedProperty(input) {
    if (!input || input.dataset.snapCheckedWatch === 'true') {
        return;
    }

    const descriptor = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'checked'
    );

    if (!descriptor || !descriptor.get || !descriptor.set) {
        return;
    }

    Object.defineProperty(input, 'checked', {
        configurable: true,
        enumerable: descriptor.enumerable,

        get() {
            return descriptor.get.call(this);
        },

        set(value) {
            descriptor.set.call(this, value);
            snapUpdateLLMVisibility();
        }
    });

    input.dataset.snapCheckedWatch = 'true';
}


function initLLMSettings() {
    const useLlm = document.getElementById('useLlm');

    if (useLlm) {
        snapWatchLLMCheckedProperty(useLlm);

        if (useLlm.dataset.snapBound !== 'true') {
            useLlm.dataset.snapBound = 'true';

            useLlm.addEventListener(
                'change',
                snapUpdateLLMVisibility
            );
        }
    }

    snapUpdateLLMVisibility();
}


if (document.readyState === 'loading') {
    document.addEventListener(
        'DOMContentLoaded',
        initLLMSettings
    );
} else {
    initLLMSettings();
}
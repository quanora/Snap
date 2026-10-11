function snapRefreshDefaultField(fieldId) {
    const checkbox = document.querySelector(
        '[data-field-enabled="' + fieldId + '"]'
    );

    const row = document.querySelector(
        '[data-field-row="' + fieldId + '"]'
    );

    if (!checkbox || !row) {
        return;
    }

    const enabled = checkbox.checked;
    const columns = row.children;
    const button = row.querySelector('[data-field-toggle]');
    const icon = button ? button.querySelector('img') : null;

    row.dataset.enabled = enabled ? 'true' : 'false';
    row.setAttribute('aria-disabled', enabled ? 'false' : 'true');

    if (columns.length > 0) {
        columns[0].style.opacity = enabled ? '1' : '0.35';
    }

    if (columns.length > 1) {
        columns[1].style.opacity = enabled ? '1' : '0.35';
    }

    if (button) {
        button.setAttribute(
            'aria-label',
            enabled
                ? 'Disable ' + fieldId + ' field'
                : 'Enable ' + fieldId + ' field'
        );

        button.setAttribute(
            'aria-pressed',
            enabled ? 'true' : 'false'
        );
    }

    if (icon) {
        icon.src = enabled
            ? 'assets/img/MinusCircle.svg'
            : 'assets/img/PlusCircle.svg';

        icon.alt = enabled
            ? 'Disable field'
            : 'Enable field';
    }
}


function snapWatchDefaultFieldCheckbox(checkbox) {
    if (!checkbox || checkbox.dataset.snapCheckedWatch === 'true') {
        return;
    }

    const descriptor = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'checked'
    );

    if (!descriptor || !descriptor.get || !descriptor.set) {
        return;
    }

    Object.defineProperty(checkbox, 'checked', {
        configurable: true,
        enumerable: descriptor.enumerable,

        get() {
            return descriptor.get.call(this);
        },

        set(value) {
            descriptor.set.call(this, value);

            snapRefreshDefaultField(
                this.dataset.fieldEnabled
            );
        }
    });

    checkbox.dataset.snapCheckedWatch = 'true';
}


function snapToggleDefaultField(fieldId) {
    const checkbox = document.querySelector(
        '[data-field-enabled="' + fieldId + '"]'
    );

    if (!checkbox || checkbox.disabled) {
        return;
    }

    checkbox.checked = !checkbox.checked;

    snapRefreshDefaultField(fieldId);

    checkbox.dispatchEvent(
        new Event('change', {
            bubbles: true
        })
    );
}


function renderAddedCustomField(field, autoEdit = true) {
    const container = document.getElementById('customFields');

    if (!container) {
        return;
    }

    const row = document.createElement('div');

    row.dataset.id = field.id;

    row.style.alignSelf = 'stretch';
    row.style.paddingTop = '8px';
    row.style.paddingBottom = '8px';
    row.style.borderBottom =
        '1px rgba(0, 0, 0, 0.10) solid';
    row.style.justifyContent = 'center';
    row.style.alignItems = 'center';
    row.style.gap = '10px';
    row.style.display = 'inline-flex';
    row.style.width = '100%';
    row.style.boxSizing = 'border-box';

    const left = document.createElement('div');

    left.style.flex = '1 1 0';
    left.style.justifyContent = 'flex-start';
    left.style.alignItems = 'center';
    left.style.gap = '10px';
    left.style.display = 'flex';
    left.style.minWidth = '0';

    const name = document.createElement('div');

    name.id = 'custom-field-' + field.id;
    name.style.color = 'black';
    name.style.fontSize = '24px';
    name.style.fontFamily = 'Inter, sans-serif';
    name.style.fontWeight = '400';
    name.style.wordWrap = 'break-word';
    name.style.minWidth = '0';

    const nameText = document.createElement('span');

    nameText.textContent = field.name;
    nameText.style.fontFamily = 'Inter, sans-serif';

    name.appendChild(nameText);

    const editWrapper = document.createElement('div');

    editWrapper.style.position = 'relative';
    editWrapper.style.width = '28px';
    editWrapper.style.height = '28px';
    editWrapper.style.flexShrink = '0';
    editWrapper.style.cursor = 'pointer';

    const editIcon = document.createElement('img');

    editIcon.src = 'assets/img/PencilSimple.svg';
    editIcon.width = 28;
    editIcon.height = 28;
    editIcon.draggable = false;
    editIcon.alt = 'Edit custom field';

    editWrapper.appendChild(editIcon);

    const deleteWrapper = document.createElement('div');

    deleteWrapper.style.position = 'relative';
    deleteWrapper.style.width = '28px';
    deleteWrapper.style.height = '28px';
    deleteWrapper.style.flexShrink = '0';
    deleteWrapper.style.cursor = 'pointer';

    const deleteIcon = document.createElement('img');

    deleteIcon.src = 'assets/img/MinusCircle.svg';
    deleteIcon.width = 28;
    deleteIcon.height = 28;
    deleteIcon.draggable = false;
    deleteIcon.alt = 'Delete custom field';

    deleteWrapper.appendChild(deleteIcon);

    left.appendChild(name);
    left.appendChild(editWrapper);

    row.appendChild(left);
    row.appendChild(deleteWrapper);

    container.appendChild(row);

    function startEditing() {
        name.contentEditable = 'true';
        name.focus();

        const selection = window.getSelection();
        const range = document.createRange();

        range.selectNodeContents(name);

        selection.removeAllRanges();
        selection.addRange(range);

        name.onkeydown = (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();

                name.contentEditable = 'false';
                name.blur();
            }
        };

        name.onblur = () => {
            const value = name.textContent.trim();

            name.contentEditable = 'false';

            name.onkeydown = null;
            name.onblur = null;

            webui.customFieldChanged(
                field.id,
                value
            );
        };
    }

    editWrapper.addEventListener('click', (event) => {
        event.stopPropagation();
        startEditing();
    });

    deleteWrapper.addEventListener('click', (event) => {
        event.stopPropagation();

        row.remove();

        webui.deleteCustomField(field.id);
    });

    if (autoEdit) {
        startEditing();
    }
}


function renderCustomFields(fields) {
    const container = document.getElementById('customFields');

    if (!container) {
        console.log('ERROR: customFields container not found');
        return;
    }

    container.innerHTML = '';

    if (!Array.isArray(fields)) {
        console.log('ERROR: custom_fields is not an array');
        return;
    }

    fields.forEach((field) => {
        renderAddedCustomField(field, false);
    });
}


function setupNoteTypeInput() {
    const input = document.getElementById('noteType');

    if (!input || input.dataset.snapBound === 'true') {
        return;
    }

    input.dataset.snapBound = 'true';

    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            input.blur();
        }
    });

    input.addEventListener('blur', () => {
        const value = input.value.trim();

        if (value) {
            webui.noteTypeChanged(value);
        }
    });
}


function setupDefaultFieldControls() {
    document.querySelectorAll('[data-field-enabled]').forEach((checkbox) => {
        snapWatchDefaultFieldCheckbox(checkbox);

        snapRefreshDefaultField(
            checkbox.dataset.fieldEnabled
        );
    });
}


if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setupDefaultFieldControls();
        setupNoteTypeInput();
    });
} else {
    setupDefaultFieldControls();
    setupNoteTypeInput();
}


// Synchronize the field appearance when Python loads saved settings.
document.addEventListener('change', (event) => {
    const checkbox = event.target;

    if (
        checkbox instanceof HTMLInputElement
        && checkbox.matches('[data-field-enabled]')
    ) {
        snapRefreshDefaultField(
            checkbox.dataset.fieldEnabled
        );
    }
});


// Delegate clicks because Python can rebuild custom-field rows.
document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) {
        return;
    }

    const toggleButton = event.target.closest('[data-field-toggle]');

    if (toggleButton) {
        event.preventDefault();
        event.stopPropagation();

        snapToggleDefaultField(
            toggleButton.dataset.fieldToggle
        );

        return;
    }

    const editControl = event.target.closest(
        '[data-field-row] [data-svg-wrapper]'
    );

    if (editControl) {
        const row = editControl.closest('[data-field-row]');

        if (row && row.dataset.fieldRow) {
            webui.editField(row.dataset.fieldRow);
        }

        return;
    }

    const addFieldControl = event.target.closest('#addCustomField');

    if (addFieldControl) {
        event.preventDefault();
        webui.addCustomField();
    }
});


document.addEventListener('keydown', (event) => {
    if (
        event.key !== 'Enter'
        || !(event.target instanceof Element)
    ) {
        return;
    }

    const addFieldControl = event.target.closest('#addCustomField');

    if (addFieldControl) {
        event.preventDefault();
        webui.addCustomField();
    }
});
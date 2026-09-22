function renderAddedCustomField(
    field,
    autoEdit = true
) {
    const container = document.getElementById(
        "customFields"
    );

    if (!container) {
        return;
    }

    const row = document.createElement("div");

    row.dataset.id = field.id;

    row.style.alignSelf = "stretch";
    row.style.paddingTop = "8px";
    row.style.paddingBottom = "8px";
    row.style.borderBottom =
        "1px rgba(0, 0, 0, 0.10) solid";
    row.style.justifyContent = "center";
    row.style.alignItems = "center";
    row.style.gap = "10px";
    row.style.display = "inline-flex";
    row.style.width = "100%";
    row.style.boxSizing = "border-box";

    const left = document.createElement("div");

    left.style.flex = "1 1 0";
    left.style.justifyContent = "flex-start";
    left.style.alignItems = "center";
    left.style.gap = "10px";
    left.style.display = "flex";
    left.style.minWidth = "0";

    const name = document.createElement("div");

    name.id = "custom-field-" + field.id;

    name.style.color = "black";
    name.style.fontSize = "24px";
    name.style.fontFamily = "Inter, sans-serif";
    name.style.fontWeight = "400";
    name.style.wordWrap = "break-word";
    name.style.minWidth = "0";

    const nameText = document.createElement("span");

    nameText.textContent = field.name;
    nameText.style.fontFamily = "Inter, sans-serif";

    name.appendChild(nameText);

    const editWrapper = document.createElement("div");

    editWrapper.style.position = "relative";
    editWrapper.style.width = "28px";
    editWrapper.style.height = "28px";
    editWrapper.style.flexShrink = "0";
    editWrapper.style.cursor = "pointer";

    const editIcon = document.createElement("img");

    editIcon.src = "assets/img/PencilSimple.svg";
    editIcon.width = 28;
    editIcon.height = 28;
    editIcon.draggable = false;

    editWrapper.appendChild(editIcon);

    const deleteWrapper = document.createElement("div");

    deleteWrapper.style.position = "relative";
    deleteWrapper.style.width = "28px";
    deleteWrapper.style.height = "28px";
    deleteWrapper.style.flexShrink = "0";
    deleteWrapper.style.cursor = "pointer";

    const deleteIcon = document.createElement("img");

    deleteIcon.src = "assets/img/MinusCircle.svg";
    deleteIcon.width = 28;
    deleteIcon.height = 28;
    deleteIcon.draggable = false;

    deleteWrapper.appendChild(deleteIcon);

    left.appendChild(name);
    left.appendChild(editWrapper);

    row.appendChild(left);
    row.appendChild(deleteWrapper);

    container.appendChild(row);

    function startEditing() {
        name.contentEditable = "true";
        name.focus();

        const selection = window.getSelection();
        const range = document.createRange();

        range.selectNodeContents(name);

        selection.removeAllRanges();
        selection.addRange(range);

        name.onkeydown = (event) => {
            if (event.key === "Enter") {
                event.preventDefault();

                name.contentEditable = "false";
                name.blur();
            }
        };

        name.onblur = () => {
            const value = name.textContent.trim();

            name.contentEditable = "false";

            webui.customFieldChanged(
                field.id,
                value
            );
        };
    }

    editWrapper.addEventListener(
        "click",
        (event) => {
            event.stopPropagation();
            startEditing();
        }
    );

    deleteWrapper.addEventListener(
        "click",
        (event) => {
            event.stopPropagation();
            row.remove();

            webui.deleteCustomField(
                field.id
            );
        }
    );

    if (autoEdit) {
        startEditing();
    }
}


function renderCustomFields(fields) {
    const container = document.getElementById(
        "customFields"
    );

    if (!container) {
        console.log(
            "ERROR: customFields container not found"
        );
        return;
    }

    container.innerHTML = "";

    if (!Array.isArray(fields)) {
        console.log(
            "ERROR: custom_fields is not an array"
        );
        return;
    }

    fields.forEach((field) => {
        renderAddedCustomField(
            field,
            false
        );
    });
}
// Функция активируется при клике на карандаш
webui.editField = function(elementId) {
    const el = document.getElementById(elementId);
    
    el.contentEditable = "true"; // Разрешаем писать внутри span
    el.focus();                  // Ставим курсор в текст
    el.dataset.oldValue = el.innerText; // Запоминаем текст до изменения
};

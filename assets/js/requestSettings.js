webui.requestSettings()

const hotkeyInput = document.getElementById('hotkeyInput');

if (hotkeyInput) {
    const formatHotkey = value => {
        const symbols = {
            cmd: '⌘',
            ctrl: '⌃',
            alt: '⌥',
            shift: '⇧',
            space: 'Space',
            enter: '↵',
            esc: 'Esc',
            tab: 'Tab',
            backspace: '⌫',
            delete: '⌦',
            up: '↑',
            down: '↓',
            left: '←',
            right: '→'
        };

        return value
            .split('+')
            .map(part => symbols[part] || part.toUpperCase())
            .join(' ');
    };

    hotkeyInput.value = settings.hotkey
        ? formatHotkey(settings.hotkey)
        : '';

    hotkeyInput.onfocus = () => {
        webui.hotkeyCaptureStarted();
    };

    hotkeyInput.onblur = () => {
        webui.hotkeyCaptureStopped();
    };

    hotkeyInput.onkeydown = event => {
        event.preventDefault();
        event.stopPropagation();

        const parts = [];

        if (event.metaKey) parts.push('cmd');
        if (event.ctrlKey) parts.push('ctrl');
        if (event.altKey) parts.push('alt');
        if (event.shiftKey) parts.push('shift');

        const modifierKeys = [
            'Meta',
            'Control',
            'Alt',
            'Shift'
        ];

        if (modifierKeys.includes(event.key)) {
            hotkeyInput.value = parts
                .map(part => formatHotkey(part))
                .join(' ');
            return;
        }

        let key = event.key.toLowerCase();

        const keyNames = {
            ' ': 'space',
            'escape': 'esc',
            'return': 'enter',
            'enter': 'enter',
            'backspace': 'backspace',
            'delete': 'delete',
            'arrowup': 'up',
            'arrowdown': 'down',
            'arrowleft': 'left',
            'arrowright': 'right'
        };

        key = keyNames[key] || key;

        parts.push(key);

        const value = parts.join('+');

        hotkeyInput.value = formatHotkey(value);

        webui.hotkeyChanged(value);

        hotkeyInput.blur();
    };
}
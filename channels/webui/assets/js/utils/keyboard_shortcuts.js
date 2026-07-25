async function registerKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ctrl+Space / Cmd+Space for global search
        if ((e.ctrlKey || e.metaKey) && e.code === 'Space') {
            e.preventDefault();
            const ui = Alpine.store('ui');
            if (ui.currentModal === 'global_search') {
                ui.closeModal();
            } else {
                ui.openModal('global_search');
            }
        }
    });
}

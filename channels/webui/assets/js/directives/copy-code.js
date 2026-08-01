function copyCode(el) {
    const code = el.querySelector('code')?.textContent || el.textContent;

    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';

    btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await navigator.clipboard.writeText(code);
        btn.textContent = '✓ Copied';
        setTimeout(() => btn.textContent = 'Copy', 1500);
    });

    el.prepend(btn);
}


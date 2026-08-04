/*
 * --- formatting stuff
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

const _rtfCache = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function formatDate(dateString) {
    if (!dateString) return '';

    // Ensure UTC parsing by appending 'Z' if missing
    const cleanDate = dateString.endsWith('Z') || dateString.endsWith('+00:00')
        ? dateString
        : dateString + 'Z';

    const date = new Date(cleanDate);
    const now = new Date();
    const diffMs = date - now;

    if (Math.abs(diffMs) < 60000) return _rtfCache.format(0, 'second');
    if (Math.abs(diffMs) < 3600000) return _rtfCache.format(Math.round(diffMs / 60000), 'minute');
    if (Math.abs(diffMs) < 86400000) return _rtfCache.format(Math.round(diffMs / 3600000), 'hour');
    if (Math.abs(diffMs) < 604800000) return _rtfCache.format(Math.round(diffMs / 86400000), 'day');

    return date.toLocaleDateString();
}

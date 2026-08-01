// create a temporary div that gets used to syntax highlight
const _tempHighlightDiv = document.createElement('div');

function renderMarkdown(text) {
    if (!text) return '';

    // parse the markdown to HTML
    let html = marked.parse(text);

    // syntax hightlighting
    if (typeof hljs !== 'undefined') {
        _tempHighlightDiv.innerHTML = html;

        _tempHighlightDiv.querySelectorAll('pre code').forEach((block) => {
            const lang = block.className.replace('language-', '') || undefined;
            hljs.highlightElement(block);
        });

        html = _tempHighlightDiv.innerHTML;
    }

    // protect against XSS
    html = DOMPurify.sanitize(html);

    // add the copy button to all pre statements using a custom alpine directive
    // (defined in directives/copy-code.js)
    html = html.replace(/<pre><code/g, '<pre><code x-copy-code');

    return html;
}

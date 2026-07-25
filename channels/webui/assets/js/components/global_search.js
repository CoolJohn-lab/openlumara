function globalSearch() {
    return {
        query: '',
        results: [],
        loading: false,
        searchInContent: true,
        activeIndex: -1,
        debounceTimer: null,

        init() {
            this.query = '';
            this.results = [];
            this.activeIndex = -1;
            this.loading = false;
            this.searchInContent = true;
            setTimeout(() => {
                document.getElementById("global-search-input").focus();
            }, 50);
        },

        highlightQuery(text, query) {
            if (!query || !text) return text;
            const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escaped})`, 'gi');
            return text.replace(regex, '<strong class="search-highlight">$1</strong>');
        },

        async search() {
            clearTimeout(this.debounceTimer);
            const q = this.query.trim();

            if (!q) {
                this.results = [];
                return;
            }

            this.loading = true;
            this.debounceTimer = setTimeout(async () => {
                this.results = await Alpine.store('chat').searchGlobal(q, this.searchInContent);
                this.loading = false;
                this.activeIndex = -1;
            }, 150);
        },

        selectResult(chatId) {
            Alpine.store('chat').loadChatFromSearch(chatId);
        },

        navigateResults(direction) {
            if (this.results.length === 0) return;
            this.activeIndex = Math.max(0, Math.min(
                this.activeIndex + direction,
                this.results.length - 1
            ));

            // Scroll the active result into view
            this.$nextTick(() => {
                const activeEl = this.$el.querySelector('.global-search-result.active');
                if (activeEl) {
                    activeEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            });
        },

        async enterResult() {
            if (this.results.length === 0) return;
            const idx = this.activeIndex >= 0 ? this.activeIndex : 0;
            await this.selectResult(this.results[idx].chat.id);
        }
    }
}

const UPLOAD_STORE = {
    files: [],

    addFile(event) {
        this.files.push(...event.target.files);
        if (this.files.length === 0) return;
        event.target.value = "";
    },

    removeFile(index) {
        this.files.splice(index, 1);
    },

    readFileAsBase64(file) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.readAsDataURL(file);
        });
    },

    /**
     * Handle pasted images from clipboard
     * @param {ClipboardEvent} event - The paste event
     */
    async pasteImage(event) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (const item of items) {
            // Only handle image types
            if (item.type.startsWith('image/')) {
                const blob = item.getAsFile();
                if (blob) {
                    // Create a File object with a generated name
                    const timestamp = Date.now();
                    const ext = blob.type.split('/')[1] || 'png';
                    const file = new File([blob], `pasted-image-${timestamp}.${ext}`, {
                        type: blob.type
                    });
                    this.files.push(file);
                }
            }
        }
    },

    clear() {
        this.files = [];
        this.processed = [];
    }
};

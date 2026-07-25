let STREAM_STORE = {
    // one of: idle, sending, processing, streaming
    state: 'idle',

    // stores raw token data
    turn: [],
    processing: {},

    // stores the final message after the stream has finished
    finalMessage: [],

    async clear() {
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
    }
}

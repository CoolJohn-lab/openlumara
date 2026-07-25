SYSTEM_STORE = {
    data: {},
    logs: [],
    running: true,
    restarting: false,
    message: '',

    async restart(message = 'Restarting server..') {
        this.message = message || "Restarting server..";
        this.restarting = true;
        await simpleApiPost("/api/system/restart");
        this.restarting = false;
    },

    async loadData() {
        this.logs = await simpleApiFetch("/api/system/logs");
        this.data = await simpleApiFetch("/api/system/data");
    }
}

function flattenForBackend(categories) {
    const result = {};

    for (const [catKey, category] of Object.entries(categories)) {
        if (!category.settings && !category.enabled && !category.disabled) continue;
        
        result[catKey] = {};
        
        // Handle modules/channels
        if (category.isModuleCategory) {
            if (category.enabled !== undefined) result[catKey].enabled = category.enabled;
            if (category.disabled !== undefined) result[catKey].disabled = category.disabled;
            
            if (category.settings) {
                result[catKey].settings = {};
                for (const [name, module] of Object.entries(category.settings)) {
                    if (module.value) {
                        result[catKey].settings[name] = flattenModuleSettings(module.value);
                    }
                }
            }
        } else {
            // Regular category - flatten all settings
            result[catKey] = flattenCategorySettings(category.settings);
        }
    }

    return result;
}

function flattenModuleSettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings)) {
        if (setting.type === 'object' && setting.settings) {
            result[key] = flattenModuleSettings(setting.settings);
        } else {
            result[key] = setting.value;
        }
    }
    return result;
}

function flattenCategorySettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings)) {
        if (setting.type === 'object' && setting.settings) {
            result[key] = flattenCategorySettings(setting.settings);
        } else {
            result[key] = setting.value;
        }
    }
    return result;
}


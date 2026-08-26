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

function flattenSettingValue(setting) {
    if (!setting || typeof setting !== 'object') return setting;
    if (setting.type === 'object_list') {
        return (setting.value || []).map((item) => flattenModuleSettings(item));
    }
    if (setting.type === 'object' && setting.settings) {
        return flattenModuleSettings(setting.settings);
    }
    return setting.value;
}

function flattenModuleSettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings || {})) {
        result[key] = flattenSettingValue(setting);
    }
    return result;
}

function flattenCategorySettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings || {})) {
        if (setting && setting.type === 'object_list') {
            result[key] = (setting.value || []).map((item) => flattenCategorySettings(item));
        } else if (setting && setting.type === 'object' && setting.settings) {
            result[key] = flattenCategorySettings(setting.settings);
        } else {
            result[key] = setting ? setting.value : setting;
        }
    }
    return result;
}

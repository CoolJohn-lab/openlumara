function isToggleList(data) {
    if (typeof data !== 'object' || data === null) return false;
    return Array.isArray(data.enabled) && Array.isArray(data.disabled);
}

const SENSITIVE_KEY_EXCEPTIONS = new Set(['auth_type', 'auth_header_name']);
const SENSITIVE_KEYWORDS = ['token', 'key', 'secret', 'password', 'auth', 'credential'];

function settingKeyTail(key) {
    const parts = String(key || '').split('.');
    return (parts[parts.length - 1] || '').toLowerCase();
}

function isSensitiveSettingKey(key) {
    const tail = settingKeyTail(key);
    if (!tail || SENSITIVE_KEY_EXCEPTIONS.has(tail)) return false;
    return SENSITIVE_KEYWORDS.some((kw) => tail.includes(kw));
}

function detectFieldType(value, key = '') {
    // special keys that should be displayed in a special way
    switch (key) {
        case "model.name":                  return "model_select"
        case "api.url":                     return "api_url"
        case "api.key":                     return "api_key"
        case "model.reasoning_effort":      return "reasoning_effort_slider"
    }

    // standard types
    if (value === null || value === undefined) {
        return isSensitiveSettingKey(key) ? 'secret' : 'text';
    } else if (typeof value === 'boolean') return 'boolean';
    else if (typeof value === 'number' && !key.toLowerCase().endsWith('id')) return 'number';
    else if (Array.isArray(value)) return 'array';
    else if (typeof value === 'string') {
        if (isSensitiveSettingKey(key)) return 'secret';
        if (value.match(/^https?:\/\//)) return 'url';
        else if (value.includes('\n')) return 'textarea';
        else return 'text';
    } else {
        return 'text';
    }
}

function normalizeFieldType(type, schemaValue, fullKey) {
    if (type === 'long_text') return 'textarea';
    if (type === 'list') return 'array';
    if (type === 'string') return 'text';
    if (type === 'secret') return 'secret';
    const resolved = type || detectFieldType(schemaValue, fullKey);
    if ((resolved === 'text' || resolved === 'textarea' || resolved === 'url') && isSensitiveSettingKey(fullKey)) {
        return 'secret';
    }
    return resolved;
}

function schemaFieldDefaults(itemSchema) {
    const obj = {};
    for (const [k, fs] of Object.entries(itemSchema || {})) {
        if (fs && typeof fs === 'object' && fs.default !== undefined) {
            obj[k] = fs.default;
        } else if (fs && fs.type === 'boolean') {
            obj[k] = false;
        } else if (fs && (fs.type === 'array' || fs.type === 'list')) {
            obj[k] = [];
        } else if (fs && fs.type === 'object') {
            obj[k] = {};
        } else if (fs && fs.type === 'number') {
            obj[k] = 0;
        } else {
            obj[k] = '';
        }
    }
    return obj;
}

function buildObjectListItem(item, itemSchema, prefix) {
    const merged = Object.assign(
        {},
        schemaFieldDefaults(itemSchema),
        (item && typeof item === 'object' && !Array.isArray(item)) ? item : {}
    );
    return buildFieldSettings(merged, itemSchema, prefix);
}

function defaultObjectListItem(itemSchema, prefix) {
    return buildObjectListItem({}, itemSchema, prefix || 'item');
}

function buildSettingsStructure(originalData, moduleInfo = {}) {
    const categories = {};
    let order = 0;

    categories.appearance = {
        title: 'Appearance',
        description: 'Theme and interface customization',
        order: order++,
        isThemeCategory: true
    };
    categories.audio = {
        title: 'Audio',
        description: 'Audio settings',
        order: order++,
        isThemeCategory: true
    };
    categories.system_prompt = {
        title: 'System Prompt',
        description: 'See the current system prompt',
        order: 100,
        isThemeCategory: true
    };
    categories.system_logs = {
        title: 'System Logs',
        description: 'Peek into the great unknown',
        order: 999,
        isThemeCategory: true
    };

    for (const [topKey, topValue] of Object.entries(originalData)) {
        if (topKey.toLowerCase() === 'theme' || topKey.toLowerCase() === 'theme_mode') {
            continue;
        }

        const category = {
            title: formatLabel(topKey),
            description: `Configure ${formatLabel(topKey).toLowerCase()}`,
            order: order++
        };

        if (topKey === 'modules' || topKey === 'user_modules' || 
            topKey === 'channels' || topKey === 'user_channels') {
            category.isModuleCategory = true;
            category.enabled = topValue.enabled || [];
            category.disabled = topValue.disabled || [];
            
            const descriptions = {};
            const unsafeModules = {};
            for (const [itemName, info] of Object.entries(moduleInfo)) {
                if (info.description) descriptions[itemName] = info.description;
                if (info.unsafe) unsafeModules[itemName] = true;
            }
            category.descriptions = descriptions;
            category.unsafeModules = unsafeModules;

            category.settings = {};
            if (topValue.settings && typeof topValue.settings === 'object') {
                for (const [itemName, itemSettings] of Object.entries(topValue.settings)) {
                    if (!itemSettings) continue;
                    const itemInfo = moduleInfo[itemName] || {};
                    const itemSchema = itemInfo.settings_schema || {};
                    category.settings[itemName] = {
                        title: formatLabel(itemName),
                        description: itemInfo.description || '',
                        unsafe: itemInfo.unsafe || false,
                        value: buildFieldSettings(itemSettings, itemSchema, itemName)
                    };
                }
            }
        } else {
            // For core config sections (api, model, core, etc.), use the schema from moduleInfo
            const sectionSchema = (moduleInfo[topKey] && moduleInfo[topKey].settings_schema) || {};
            category.settings = (topValue && typeof topValue === 'object') ? 
                buildFieldSettings(topValue, sectionSchema, topKey) : {};
        }

        categories[topKey] = category;
    }

    return categories;
}

function buildFieldSettings(obj, schema, prefix = '') {
    if (!obj || typeof obj !== 'object') return {};
    
    const settings = {};

    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const fieldSchema = schema[key] || {};

        // Check if schema defines this field with metadata
        const hasSchemaDefinition = fieldSchema && (fieldSchema.type !== undefined || fieldSchema.default !== undefined || fieldSchema.description !== undefined);

        if (hasSchemaDefinition && fieldSchema.type === 'object_list') {
            const itemSchema = fieldSchema.item_schema || {};
            const items = Array.isArray(value) ? value : [];
            settings[key] = {
                title: formatLabel(key),
                type: 'object_list',
                description: fieldSchema.description || null,
                unsafe: fieldSchema.unsafe || false,
                depends: fieldSchema.depends || null,
                item_schema: itemSchema,
                item_label: fieldSchema.item_label || 'item',
                value: items.map((item, i) => buildObjectListItem(item, itemSchema, `${fullKey}.${i}`))
            };
            continue;
        }

        if (hasSchemaDefinition) {
            // Schema defines the field - use schema for metadata, value for current value
            const schemaValue = fieldSchema.default !== undefined ? fieldSchema.default : value;
            settings[key] = {
                title: formatLabel(key),
                type: normalizeFieldType(fieldSchema.type, schemaValue, fullKey),
                description: fieldSchema.description || null,
                unsafe: fieldSchema.unsafe || false,
                value: value,
                options: fieldSchema.options || null,
                min: fieldSchema.min,
                max: fieldSchema.max,
                step: fieldSchema.step,
                depends: fieldSchema.depends || null
            };
        } else if (typeof value === 'object' && value !== null && !Array.isArray(value) && !isToggleList(value)) {
            // Nested object without schema definition - recurse
            settings[key] = {
                type: 'object',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                depends: fieldSchema.depends || null,
                settings: buildFieldSettings(value, fieldSchema, fullKey)
            };
        } else if (isToggleList(value)) {
            settings[key] = {
                type: 'toggle_list',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                value: value
            };
        } else if (Array.isArray(value)) {
            settings[key] = {
                type: 'array',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                value: value
            };
        } else if (typeof value === 'object') {
            settings[key] = {
                type: 'object',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                settings: buildFieldSettings(value, fieldSchema, fullKey)
            };
        } else {
            // Primitive value without schema definition
            settings[key] = {
                title: formatLabel(key),
                type: detectFieldType(value, fullKey),
                description: fieldSchema.description || null,
                unsafe: fieldSchema.unsafe || false,
                depends: fieldSchema.depends || null,
                value: value,
                options: fieldSchema.options || null,
                min: fieldSchema.min,
                max: fieldSchema.max,
                step: fieldSchema.step
            };
        }
    }

    return settings;
}

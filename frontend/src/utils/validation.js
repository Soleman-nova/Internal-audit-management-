/**
 * Form validation utilities for the EEU Internal Audit Management System.
 * Provides field-level validators, cross-field checks, and format validators.
 */

// ── Field validators ──────────────────────────────────────────────

export const validators = {
    required: (value) => {
        if (value === undefined || value === null || value === '') return 'This field is required.';
        if (typeof value === 'string' && value.trim() === '') return 'This field is required.';
        return null;
    },

    email: (value) => {
        if (!value) return null;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) return 'Please enter a valid email address.';
        return null;
    },

    minLength: (min) => (value) => {
        if (!value) return null;
        if (String(value).length < min) return `Must be at least ${min} characters.`;
        return null;
    },

    maxLength: (max) => (value) => {
        if (!value) return null;
        if (String(value).length > max) return `Must be at most ${max} characters.`;
        return null;
    },

    min: (min) => (value) => {
        if (value === undefined || value === null || value === '') return null;
        const num = Number(value);
        if (isNaN(num)) return 'Must be a number.';
        if (num < min) return `Must be at least ${min}.`;
        return null;
    },

    max: (max) => (value) => {
        if (value === undefined || value === null || value === '') return null;
        const num = Number(value);
        if (isNaN(num)) return 'Must be a number.';
        if (num > max) return `Must be at most ${max}.`;
        return null;
    },

    number: (value) => {
        if (value === undefined || value === null || value === '') return null;
        if (isNaN(Number(value))) return 'Must be a valid number.';
        return null;
    },

    integer: (value) => {
        if (value === undefined || value === null || value === '') return null;
        if (!Number.isInteger(Number(value))) return 'Must be a whole number.';
        return null;
    },

    date: (value) => {
        if (!value) return null;
        if (isNaN(Date.parse(value))) return 'Please enter a valid date.';
        return null;
    },

    phone: (value) => {
        if (!value) return null;
        const phoneRegex = /^[+\d][\d\s\-()]{7,}$/;
        if (!phoneRegex.test(value)) return 'Please enter a valid phone number.';
        return null;
    },

    url: (value) => {
        if (!value) return null;
        try {
            new URL(value);
            return null;
        } catch {
            return 'Please enter a valid URL.';
        }
    },

    password: (value) => {
        if (!value) return null;
        if (value.length < 8) return 'Password must be at least 8 characters.';
        if (!/[A-Z]/.test(value)) return 'Password must contain at least one uppercase letter.';
        if (!/[a-z]/.test(value)) return 'Password must contain at least one lowercase letter.';
        if (!/[0-9]/.test(value)) return 'Password must contain at least one number.';
        return null;
    },

    employeeId: (value) => {
        if (!value) return null;
        const idRegex = /^[A-Za-z0-9\-]+$/;
        if (!idRegex.test(value)) return 'Employee ID can only contain letters, numbers, and hyphens.';
        return null;
    },

    code: (value) => {
        if (!value) return null;
        const codeRegex = /^[A-Za-z0-9\-_]+$/;
        if (!codeRegex.test(value)) return 'Code can only contain letters, numbers, hyphens, and underscores.';
        return null;
    },
};

// ── Cross-field validators ────────────────────────────────────────

export const crossFieldValidators = {
    dateRange: (startField, endField, messages = {}) => (values) => {
        const start = values[startField];
        const end = values[endField];
        if (!start || !end) return {};
        if (new Date(start) > new Date(end)) {
            return {
                [endField]: messages.end || 'End date must be after start date.',
            };
        }
        return {};
    },

    passwordMatch: (passwordField, confirmField, messages = {}) => (values) => {
        const password = values[passwordField];
        const confirm = values[confirmField];
        if (!password || !confirm) return {};
        if (password !== confirm) {
            return {
                [confirmField]: messages.confirm || 'Passwords do not match.',
            };
        }
        return {};
    },

    minLessThanMax: (minField, maxField, messages = {}) => (values) => {
        const min = Number(values[minField]);
        const max = Number(values[maxField]);
        if (isNaN(min) || isNaN(max) || !values[minField] || !values[maxField]) return {};
        if (min > max) {
            return {
                [maxField]: messages.max || 'Maximum must be greater than or equal to minimum.',
            };
        }
        return {};
    },
};

// ── Validation engine ─────────────────────────────────────────────

/**
 * Validate a form object against a schema.
 *
 * @param {Object} values - The form values to validate.
 * @param {Object} schema - Validation schema:
 *   {
 *     fieldName: {
 *       validators: [fn, fn, ...],  // or a single fn
 *       crossField: fn,             // optional cross-field validator
 *     },
 *     ...
 *   }
 * @returns {Object} errors - { fieldName: 'error message', ... }
 */
export function validateForm(values, schema) {
    const errors = {};

    for (const [field, rules] of Object.entries(schema)) {
        const value = values[field];
        const validatorsList = Array.isArray(rules.validators) ? rules.validators : [rules.validators];

        for (const validator of validatorsList) {
            if (!validator) continue;
            const error = validator(value, values);
            if (error) {
                errors[field] = error;
                break;
            }
        }
    }

    // Run cross-field validators
    for (const [field, rules] of Object.entries(schema)) {
        if (rules.crossField) {
            const crossErrors = rules.crossField(values);
            Object.assign(errors, crossErrors);
        }
    }

    return errors;
}

/**
 * Check if a form has any errors.
 */
export function hasErrors(errors) {
    return Object.keys(errors).length > 0;
}

/**
 * Clear a single field error.
 */
export function clearFieldError(errors, field) {
    const next = { ...errors };
    delete next[field];
    return next;
}

export default {
    validators,
    crossFieldValidators,
    validateForm,
    hasErrors,
    clearFieldError,
};
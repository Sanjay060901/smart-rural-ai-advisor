// src/utils/apiFetch.js
// Authenticated fetch wrapper — attaches Cognito JWT to every API call
// Falls back to unauthenticated fetch if no token available

import { getIdToken } from '../services/cognitoAuth';
import config from '../config';

/**
 * Fetch wrapper that automatically attaches Cognito JWT Authorization header.
 * Throws on non-2xx HTTP responses so callers don't silently swallow errors.
 * Usage:  apiFetch('/chat', { method: 'POST', body: JSON.stringify(payload) })
 *
 * @param {string} path     - API path (e.g. '/chat', '/profile/ph_1234567890')
 * @param {RequestInit} opts - Standard fetch options (method, headers, body, etc.)
 * @param {object} [extra]  - Extra options: { raw: true } to skip auto-throw
 * @returns {Promise<Response>}
 */
export async function apiFetch(path, opts = {}, extra = {}) {
    const url = `${config.API_URL}${path}`;
    const token = await getIdToken();

    const headers = {
        ...opts.headers,
    };

    if (token) {
        headers['Authorization'] = token;
    }

    // Ensure Content-Type for JSON bodies if not already set
    if (opts.body && typeof opts.body === 'string' && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(url, { ...opts, headers });

    // Auto-throw on non-2xx unless caller opts out with { raw: true }
    if (!res.ok && !extra.raw) {
        let errorMsg = `API error ${res.status}`;
        try {
            const errBody = await res.clone().json();
            if (errBody.message || errBody.error) {
                errorMsg = errBody.message || errBody.error;
            }
        } catch {
            // Response wasn't JSON — use status text
            errorMsg = `${res.status} ${res.statusText}`;
        }
        const err = new Error(errorMsg);
        err.status = res.status;
        err.response = res;
        throw err;
    }

    return res;
}


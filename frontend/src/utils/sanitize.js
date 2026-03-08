// src/utils/sanitize.js
// Shared HTML sanitizer using DOMPurify + marked — prevents XSS from AI-generated content

import DOMPurify from 'dompurify';
import { marked } from 'marked';

// Configure marked for chat-friendly output
marked.setOptions({
    gfm: true,          // GitHub-Flavoured Markdown (tables, strikethrough, etc.)
    breaks: true,        // Convert \n → <br> (chat messages aren't wrapped in <p>)
});

// Custom renderer to add chat-friendly CSS classes
// NOTE: marked v15+ passes a single token object to renderer methods
const renderer = new marked.Renderer();

// All headings render as compact h3/h4/h5 inside chat bubbles
renderer.heading = function (token) {
    const depth = token.depth || 3;
    const text = this.parser.parseInline(token.tokens || []) || token.text || '';
    const tag = depth <= 3 ? 'h3' : depth === 4 ? 'h4' : 'h5';
    return `<${tag} class="chat-heading">${text}</${tag}>\n`;
};

// Add classes to list items for styling
renderer.listitem = function (token) {
    const text = this.parser.parse(token.tokens || []) || token.text || '';
    return `<li class="chat-list-item">${text}</li>\n`;
};

// Tables get a wrapper class
renderer.table = function (token) {
    // Build header
    const headerCells = (token.header || []).map(cell => {
        const content = this.parser.parseInline(cell.tokens || []) || cell.text || '';
        return `<th>${content}</th>`;
    }).join('');
    const headerRow = `<tr>${headerCells}</tr>`;
    
    // Build body rows
    const bodyRows = (token.rows || []).map(row => {
        const cells = row.map(cell => {
            const content = this.parser.parseInline(cell.tokens || []) || cell.text || '';
            return `<td>${content}</td>`;
        }).join('');
        return `<tr>${cells}</tr>`;
    }).join('\n');
    
    return `<table class="chat-table"><thead>${headerRow}</thead><tbody>${bodyRows}</tbody></table>\n`;
};

// Links open in new tab
renderer.link = function (token) {
    const href = token.href || '';
    const title = token.title ? ` title="${token.title}"` : '';
    const text = this.parser.parseInline(token.tokens || []) || token.text || '';
    return `<a href="${href}" target="_blank" rel="noopener noreferrer"${title}>${text}</a>`;
};

marked.use({ renderer });

// Allow only safe HTML tags and attributes for formatted AI responses
const PURIFY_CONFIG = {
    ALLOWED_TAGS: [
        'strong', 'b', 'em', 'i', 'br', 'span', 'p', 'div',
        'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'pre', 'code',
        'a', 'audio', 'source', 'blockquote', 'del', 'input', 'img'
    ],
    ALLOWED_ATTR: [
        'class', 'id', 'href', 'target', 'rel', 'src', 'alt',
        'controls', 'preload', 'type'
    ],
    ALLOW_DATA_ATTR: false,
    // Force all links to open in new tab safely
    ADD_ATTR: ['target'],
};

/**
 * Sanitize HTML string to prevent XSS.
 * Use this before passing to dangerouslySetInnerHTML.
 */
export function sanitizeHtml(dirty) {
    if (!dirty) return '';
    const clean = DOMPurify.sanitize(dirty, PURIFY_CONFIG);
    // Ensure external links have rel="noopener noreferrer"
    return clean.replace(/<a\s/g, '<a rel="noopener noreferrer" target="_blank" ');
}

/**
 * Format markdown text to HTML and sanitize.
 * Uses 'marked' for full markdown support — handles headers, bold, italic,
 * lists, tables, code blocks, links, blockquotes, horizontal rules, and more.
 * DOMPurify strips any unsafe HTML the LLM might inject.
 */
export function formatAndSanitize(text) {
    if (!text) return '';
    // Normalize common LLM markdown quirks so headings/lists always render:
    // - remove excessive indentation before heading markers (prevents code-block parsing)
    // - enforce a space after heading hashes (e.g. "###Title" -> "### Title")
    const normalized = text
        .replace(/^[\t ]{4,}(#{1,6}\s*)/gm, '$1')
        .replace(/^(#{1,6})([^\s#])/gm, '$1 $2');

    // marked.parse outputs full HTML from standard markdown
    const rawHtml = marked.parse(normalized);

    // Safety fallback: if any malformed heading still survives as plain text,
    // convert it so users never see raw "###" markers in chat.
    const withHeadingFallback = rawHtml
        .replace(/<p>\s*#{1,2}\s*([^<]+)<\/p>/gi, '<h3 class="chat-heading">$1</h3>')
        .replace(/<p>\s*#{3}\s*([^<]+)<\/p>/gi, '<h3 class="chat-heading">$1</h3>')
        .replace(/<p>\s*#{4}\s*([^<]+)<\/p>/gi, '<h4 class="chat-heading">$1</h4>')
        .replace(/<p>\s*#{5,6}\s*([^<]+)<\/p>/gi, '<h5 class="chat-heading">$1</h5>');

    return sanitizeHtml(withHeadingFallback);
}

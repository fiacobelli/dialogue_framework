// Patient-facing text lookup. Templates set window.APP_LANG and window.I18N (English -> chosen language).
window.APP_LANG = window.APP_LANG || 'en';
window.I18N = window.I18N || {};

function T(text, values = {}) {
    const out = window.I18N[text] || text;
    return out.replace(/\{(\w+)\}/g, (match, key) => (key in values ? values[key] : match));
}

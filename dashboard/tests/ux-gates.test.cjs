'use strict';
// Static UX gates from .agents/skills/ux-engine-kiosk (see dashboard/analysis/ux-maturity-2026-10-13.md).
// They read the dashboard sources only: no browser, no network.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const DIR = path.join(__dirname, '..');
const read = name => fs.readFileSync(path.join(DIR, name), 'utf8');
const CSS = ['style.css', 'live.css', 'agent-arena.css'];
const JS = fs.readdirSync(DIR).filter(f => f.endsWith('.js') && !/^(graph-data|system-design-(data|chunks))\.js$/.test(f));
// Ratchets: these counts may only go down. Lower them when you migrate styles to classes and tokens.
const MAX_INLINE_STYLES = 253;
const MAX_COLORS_OUTSIDE_ROOT = 37;

function tokens(selector) {
    const css = read('style.css'), start = css.indexOf(selector + '{');
    assert.ok(start >= 0, selector + ' not found in style.css');
    const body = css.slice(start + selector.length + 1, css.indexOf('}', start));
    return Object.fromEntries([...body.matchAll(/--([\w-]+):([^;]+)/g)].map(m => [m[1], m[2].trim()]));
}
function luminance(hex) {
    let h = hex.replace('#', ''); if (h.length === 3) h = [...h].map(c => c + c).join('');
    return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
        .map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
}
function ratio(a, b) { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
const THEMES = { dark: tokens(':root'), light: tokens(':root[data-theme=light]') };

// Labels that look destructive but only touch interface state or an unsaved draft.
const NOT_DESTRUCTIVE = {
    'Limpar filtros': 'restaura filtros da interface; nada persistido é apagado',
    'Remover': 'remove uma etapa do rascunho de plano em edição',
};
test('destructive_confirm: destructive buttons go through confirmAction', () => {
    const offenders = [];
    for (const file of JS) {
        const src = read(file);
        for (const m of src.matchAll(/button\(\s*(['"`])([^'"`]*\b(limpar|apagar|excluir|deletar|remover)\b[^'"`]*)\1/gi)) {
            if (Object.hasOwn(NOT_DESTRUCTIVE, m[2])) continue;
            if (!src.slice(m.index, m.index + 600).includes('confirmAction(')) offenders.push(file + ': ' + m[2]);
        }
    }
    assert.deepEqual(offenders, []);
});

test('modal_semantics: overlays are <dialog> elements (focus trap, Esc, top layer)', () => {
    const offenders = [];
    for (const file of JS)
        for (const m of read(file).matchAll(/el\(\s*['"]div['"]\s*,\s*\{[^}]*class:\s*['"`][^'"`]*\b(modal|drawer|backdrop|overlay)\b[^'"`]*['"`]/g))
            offenders.push(file + ': ' + m[0].slice(0, 80));
    assert.deepEqual(offenders, []);
});

test('hierarchy: one navigation entry per screen, the default page first', () => {
    const app = read('app.js');
    const pages = [...app.match(/const pages = \{(.*?)\};/)[1].matchAll(/(\w+):\[/g)].map(m => m[1]);
    assert.equal(pages[0], 'overview', 'the default page (overview) must lead the navigation');
    assert.ok(!pages.includes('agents'), '"agents" and "workflows" render the same Arena; keep one entry');
    assert.match(app, /if\(r\.page==='agents'\)r\.page='workflows'/, 'old #page=agents links must still open the Arena');
});

test('reduced_motion: the global reduced-motion rule also stops animations', () => {
    const rule = read('style.css').match(/@media\s*\(prefers-reduced-motion:\s*reduce\)\{(.*?\})\}/);
    assert.ok(rule, 'style.css needs a prefers-reduced-motion rule');
    assert.match(rule[1], /animation:none!important/);
    assert.match(rule[1], /transition:none!important/);
});

test('contrast: text tokens reach 4.5:1 on every surface in both themes', () => {
    for (const [theme, t] of Object.entries(THEMES)) {
        for (const fg of ['text', 'muted', 'accent', 'good', 'warn', 'blue', 'violet', 'danger'])
            for (const bg of ['bg', 'panel', 'panel2'])
                assert.ok(ratio(t[fg], t[bg]) >= 4.5, `${theme}: --${fg} on --${bg} is ${ratio(t[fg], t[bg]).toFixed(2)}:1`);
        assert.ok(ratio(t['accent-ink'], t.accent) >= 4.5, theme + ': --accent-ink on --accent');
    }
});

test('non_text_contrast: field borders reach 3:1 against the field and its panel', () => {
    for (const [theme, t] of Object.entries(THEMES)) {
        assert.ok(t['field-border'], theme + ' needs --field-border');
        for (const bg of ['bg', 'panel', 'panel2'])
            assert.ok(ratio(t['field-border'], t[bg]) >= 3, `${theme}: --field-border on --${bg} is ${ratio(t['field-border'], t[bg]).toFixed(2)}:1`);
    }
    assert.match(read('style.css'), /input,select,textarea\{[^}]*border:1px solid var\(--field-border\)/);
});

test('font_min: no font-size below 11px in CSS or inline styles', () => {
    const offenders = [];
    for (const file of [...CSS, ...JS])
        for (const m of read(file).matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)) if (Number(m[1]) < 11) offenders.push(file + ': ' + m[0]);
    assert.deepEqual(offenders, []);
});

test('doc_drift: every CSS custom property named in DESIGN.md exists in the stylesheets', () => {
    const css = CSS.map(read).join('\n');
    const missing = [...new Set([...read('DESIGN.md').matchAll(/--[a-z][\w-]*/g)].map(m => m[0]))].filter(name => !css.includes(name + ':'));
    assert.deepEqual(missing, []);
});

test('hardcoded_values: inline styles and colours outside :root only go down', () => {
    const inline = JS.reduce((n, f) => n + (read(f).match(/style:\s*['"`]/g) || []).length, 0);
    const colours = CSS.reduce((n, f) => n + (read(f).replace(/:root[^{]*\{[^}]*\}/g, '').match(/#[0-9a-f]{3,8}\b|rgba?\(/gi) || []).length, 0);
    assert.ok(inline <= MAX_INLINE_STYLES, `${inline} inline styles (max ${MAX_INLINE_STYLES})`);
    assert.ok(colours <= MAX_COLORS_OUTSIDE_ROOT, `${colours} colours outside :root (max ${MAX_COLORS_OUTSIDE_ROOT})`);
});

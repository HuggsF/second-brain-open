(function (root, factory) {
    'use strict';
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root) root.BrainMarkdown = api;
})(typeof window !== 'undefined' ? window : null, function () {
    'use strict';
    const MAX_DOCUMENT = 500000;
    const MAX_HEADING = 240;
    const MAX_CODE = 200000;
    const asText = value => String(value == null ? '' : value);

    function slug(value) {
        return asText(value).normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
            .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'section';
    }

    function safeURL(value) {
        const raw = asText(value);
        if (!/^https?:\/\//i.test(raw) || /[\u0000-\u0020\u007f]/.test(raw)) return null;
        try {
            const url = new URL(raw);
            if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
            return url.href;
        } catch (_) { return null; }
    }

    function tokenizeInline(value, depth = 0) {
        const text = asText(value);
        if (depth > 5) return [{ type: 'text', text }];
        const tokens = [];
        let cursor = 0;
        let plain = '';
        function flush() {
            if (plain) { tokens.push({ type: 'text', text: plain }); plain = ''; }
        }
        while (cursor < text.length) {
            const rest = text.slice(cursor);
            if (rest[0] === '\\' && rest.length > 1 && /[\\`*_[\]()!|]/.test(rest[1])) {
                plain += rest[1]; cursor += 2; continue;
            }
            const code = rest.match(/^(`+)([\s\S]*?)\1(?!`)/);
            if (code) { flush(); tokens.push({ type: 'code', text: code[2] }); cursor += code[0].length; continue; }
            const wiki = rest.match(/^\[\[([^\]\n]+)\]\]/);
            if (wiki) {
                const [destination, ...labels] = wiki[1].split('|');
                const hash = destination.indexOf('#');
                const ref = (hash < 0 ? destination : destination.slice(0, hash)).trim();
                const heading = hash < 0 ? '' : destination.slice(hash + 1).trim();
                flush(); tokens.push({ type: 'wiki', ref, heading, text: labels.join('|').trim() || destination.trim() });
                cursor += wiki[0].length; continue;
            }
            const image = rest.match(/^!\[([^\]\n]*)\]\(([^)\n]*)\)/);
            if (image) {
                flush(); tokens.push({ type: 'image', text: image[1] || 'Imagem' });
                cursor += image[0].length; continue;
            }
            const link = rest.match(/^\[([^\]\n]+)\]\(([^)\n]+)\)/);
            if (link) {
                flush(); tokens.push({ type: 'link', text: link[1], url: safeURL(link[2].trim()), rawURL: link[2] });
                cursor += link[0].length; continue;
            }
            const strong = rest.match(/^(\*\*|__)([\s\S]+?)\1/);
            if (strong) {
                flush(); tokens.push({ type: 'strong', children: tokenizeInline(strong[2], depth + 1) });
                cursor += strong[0].length; continue;
            }
            const citation = rest.match(/^\[\^(\w[\w.-]*)\]/);
            if (citation) { flush(); tokens.push({ type: 'citation', ref: citation[1], text: citation[0] }); cursor += citation[0].length; continue; }
            plain += text[cursor++];
        }
        flush();
        return tokens;
    }

    function splitTableRow(value) {
        let line = asText(value).trim();
        if (line.startsWith('|')) line = line.slice(1);
        if (line.endsWith('|') && !line.endsWith('\\|')) line = line.slice(0, -1);
        const cells = [];
        let cell = '', ticks = false;
        for (let i = 0; i < line.length; i++) {
            if (line[i] === '\\' && line[i + 1] === '|') { cell += '|'; i++; continue; }
            if (line[i] === '`') ticks = !ticks;
            if (line[i] === '|' && !ticks) { cells.push(cell.trim()); cell = ''; }
            else cell += line[i];
        }
        cells.push(cell.trim());
        return cells;
    }

    function parseBlocks(value) {
        const text = asText(value).slice(0, MAX_DOCUMENT).replace(/\r\n?/g, '\n');
        const lines = text.split('\n'), blocks = [], ids = new Map();
        let index = 0;
        function headingID(label) {
            const base = slug(label), count = (ids.get(base) || 0) + 1;
            ids.set(base, count); return base + (count > 1 ? '-' + count : '');
        }
        function listItem(line) { return line.match(/^\s{0,3}([-*+]|\d+[.)])\s+(.+)$/); }
        function isStart(line, next) {
            return /^\s*(`{3,}|~{3,})/.test(line) || /^(#{1,6})\s+/.test(line)
                || Boolean(listItem(line)) || /^\s*>\s?/.test(line) || /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)
                || (line.includes('|') && Boolean(next) && splitTableRow(next).every(c => /^:?-{3,}:?$/.test(c)));
        }
        while (index < lines.length) {
            const line = lines[index];
            if (!line.trim()) { index++; continue; }
            const fence = line.match(/^\s*(`{3,}|~{3,})\s*([^\s]*)\s*$/);
            if (fence) {
                const code = [], char = fence[1][0], length = fence[1].length;
                index++;
                const closing = new RegExp('^\\s*' + char + '{' + length + ',}\\s*$');
                while (index < lines.length && !closing.test(lines[index])) code.push(lines[index++]);
                if (index < lines.length) index++;
                blocks.push({ type: 'code', text: code.join('\n').slice(0, MAX_CODE), truncated: code.join('\n').length > MAX_CODE, language: fence[2].replace(/[^a-z0-9_-]/gi, '').slice(0, 32) });
                continue;
            }
            const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
            if (heading) {
                const label = heading[2].slice(0, MAX_HEADING);
                blocks.push({ type: 'heading', level: heading[1].length, text: label, id: headingID(label) }); index++; continue;
            }
            const delimiter = lines[index + 1] && splitTableRow(lines[index + 1]);
            if (line.includes('|') && delimiter && delimiter.every(c => /^:?-{3,}:?$/.test(c))) {
                const header = splitTableRow(line), rows = [];
                if (header.length === delimiter.length) {
                    const align = delimiter.map(c => c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : 'left');
                    index += 2;
                    while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
                        const row = splitTableRow(lines[index++]);
                        rows.push(header.map((_, i) => row[i] || ''));
                    }
                    blocks.push({ type: 'table', header, align, rows }); continue;
                }
            }
            const first = listItem(line);
            if (first) {
                const ordered = /^\d/.test(first[1]), items = [], start = ordered ? parseInt(first[1], 10) : null;
                while (index < lines.length) {
                    const item = listItem(lines[index]);
                    if (!item || /^\d/.test(item[1]) !== ordered) break;
                    items.push(item[2]); index++;
                }
                blocks.push({ type: 'list', ordered, start, items }); continue;
            }
            if (/^\s*>\s?/.test(line)) {
                const quote = [];
                while (index < lines.length && /^\s*>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^\s*>\s?/, ''));
                blocks.push({ type: 'quote', text: quote.join(' ') }); continue;
            }
            if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { blocks.push({ type: 'rule' }); index++; continue; }
            const paragraph = [line]; index++;
            while (index < lines.length && lines[index].trim() && !isStart(lines[index], lines[index + 1])) paragraph.push(lines[index++]);
            blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
        }
        return blocks;
    }

    function render(container, value, options = {}) {
        if (!container || !container.ownerDocument) throw new TypeError('A document container is required.');
        const doc = container.ownerDocument, blocks = parseBlocks(value);
        const make = (tag, text) => { const el = doc.createElement(tag); if (text != null) el.textContent = text; return el; };
        function inline(parent, tokens) {
            for (const token of tokens) {
                if (token.type === 'text') parent.appendChild(doc.createTextNode(token.text));
                else if (token.type === 'code') parent.appendChild(make('code', token.text));
                else if (token.type === 'strong') { const strong = make('strong'); inline(strong, token.children); parent.appendChild(strong); }
                else if (token.type === 'link') {
                    if (token.url) {
                        const a = make('a', token.text); a.setAttribute('href', token.url);
                        a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer'); parent.appendChild(a);
                    } else parent.appendChild(make('span', token.text));
                } else if (token.type === 'image') {
                    const alt = make('span', '[Imagem: ' + token.text + ']'); alt.className = 'markdown-image-alt'; parent.appendChild(alt);
                } else if (token.type === 'wiki' || token.type === 'citation') {
                    const callback = token.type === 'wiki' ? options.onWikiLink : options.onCitation;
                    if (typeof callback === 'function') {
                        const button = make('button', token.text); button.type = 'button'; button.className = 'markdown-reference';
                        button.addEventListener('click', () => token.type === 'wiki' ? callback(token.ref, token.heading || undefined) : callback(token.ref));
                        parent.appendChild(button);
                    } else parent.appendChild(make('span', token.text));
                }
            }
        }
        const fragment = doc.createDocumentFragment();
        for (const block of blocks) {
            if (block.type === 'heading') {
                const heading = make('h' + block.level); heading.id = block.id; inline(heading, tokenizeInline(block.text)); fragment.appendChild(heading);
            } else if (block.type === 'code') {
                const pre = make('pre'), code = make('code', block.text); pre.className = 'source-code';
                if (block.language) code.setAttribute('data-language', block.language);
                pre.appendChild(code); fragment.appendChild(pre);
            } else if (block.type === 'table') {
                const wrap = make('div'), table = make('table'), head = make('thead'), row = make('tr'), body = make('tbody');
                wrap.className = 'markdown-table-wrap';
                block.header.forEach((text, i) => { const th = make('th'); th.setAttribute('scope', 'col'); th.className = 'align-' + block.align[i]; inline(th, tokenizeInline(text)); row.appendChild(th); });
                head.appendChild(row); table.appendChild(head);
                for (const values of block.rows) {
                    const tr = make('tr'); values.forEach((text, i) => { const td = make('td'); td.className = 'align-' + block.align[i]; inline(td, tokenizeInline(text)); tr.appendChild(td); }); body.appendChild(tr);
                }
                table.appendChild(body); wrap.appendChild(table); fragment.appendChild(wrap);
            } else if (block.type === 'list') {
                const list = make(block.ordered ? 'ol' : 'ul');
                if (block.ordered && block.start !== 1) list.setAttribute('start', String(block.start));
                for (const text of block.items) { const li = make('li'); inline(li, tokenizeInline(text)); list.appendChild(li); } fragment.appendChild(list);
            } else if (block.type === 'rule') fragment.appendChild(make('hr'));
            else { const text = make(block.type === 'quote' ? 'blockquote' : 'p'); inline(text, tokenizeInline(block.text)); fragment.appendChild(text); }
        }
        container.replaceChildren(fragment);
        return { headings: blocks.filter(b => b.type === 'heading').map(({ id, text, level }) => ({ id, text, level })), blocks, truncated: asText(value).length > MAX_DOCUMENT || blocks.some(b=>b.truncated) };
    }
    return Object.freeze({ render, parseBlocks, tokenizeInline, splitTableRow, slug, safeURL, limits: Object.freeze({ document: MAX_DOCUMENT, heading: MAX_HEADING, code: MAX_CODE }) });
});

# jev-app

Tela do JEV (evidência e luzes de teste): React 19 + Tailwind 4 + Vite 8. Tokens de `dashboard/DESIGN.md`.

```bash
cd jev-app
npm install     # Node >= 22.12
npm test        # vitest (lógica pura em src/lib)
npm run dev     # http://127.0.0.1:5173, proxy de /api e /v1 para http://127.0.0.1:8848
npm run build   # gera ../dashboard/jev (index.html + assets/*.js|css)
```

O build em `dashboard/jev/` é commitado; rebuild depois de mudar `src` e commite o resultado.

O BFF serve `/dashboard/*` com CSP `script-src 'self'; style-src 'self'` e só os sufixos
`.html .js .css .json .svg .png .jpg .webp .md`. Portanto: sem `style=` inline, sem script inline,
sem fonte web, sem sourcemap (o `vite.config.js` já desliga sourcemap, polyfill de modulepreload e inline de assets).

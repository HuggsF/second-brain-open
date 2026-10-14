/**
 * @file liquid-engine.js
 * @description Motor Liquid client-side zero-dependency para JEV (Joint Evidence View).
 * Permite interpolação reativa em tempo real de parâmetros nos Playbooks do Second Brain.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.LiquidEngine = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {

  const VAR_REGEX = /\{\{\s*(.*?)\s*\}\}/g;
  const TAG_REGEX = /\{%\s*(if|unless)\s+(.*?)\s*%\}([\s\S]*?)(?:\{%\s*else\s*%\}([\s\S]*?))?\{%\s*(?:endif|endunless)\s*%\}/g;

  function resolvePath(context, path) {
    if (!context || !path) return '';
    const parts = path.trim().split('.');
    let curr = context;
    for (const part of parts) {
      if (curr === null || curr === undefined) return '';
      curr = curr[part];
    }
    return curr === undefined || curr === null ? '' : curr;
  }

  function applyFilter(value, filterExpr, context) {
    const parts = filterExpr.trim().split(':');
    const filterName = parts[0].trim().toLowerCase();
    let arg = parts.length > 1 ? parts.slice(1).join(':').trim() : null;

    if (arg) {
      if ((arg.startsWith('"') && arg.endsWith('"')) || (arg.startsWith("'") && arg.endsWith("'"))) {
        arg = arg.slice(1, -1);
      } else if (!isNaN(Number(arg))) {
        arg = Number(arg);
      } else {
        arg = resolvePath(context, arg) || arg;
      }
    }

    switch (filterName) {
      case 'default':
        return (value === '' || value === null || value === undefined || value === false) ? arg : value;
      case 'upcase':
        return String(value || '').toUpperCase();
      case 'downcase':
        return String(value || '').toLowerCase();
      case 'capitalize':
        const s = String(value || '');
        return s.charAt(0).toUpperCase() + s.slice(1);
      case 'strip':
      case 'trim':
        return String(value || '').trim();
      case 'truncate':
        const limit = Number(arg) || 100;
        const str = String(value || '');
        return str.length > limit ? str.slice(0, limit) + '...' : str;
      case 'replace':
        if (typeof arg === 'string') {
          const splitArgs = arg.split(',');
          const search = splitArgs[0].trim().replace(/^['"]|['"]$/g, '');
          const rep = (splitArgs[1] || '').trim().replace(/^['"]|['"]$/g, '');
          return String(value || '').replaceAll(search, rep);
        }
        return value;
      default:
        return value;
    }
  }

  function evalCondition(condStr, context) {
    const cond = condStr.trim();
    if (cond.includes('==')) {
      const [left, right] = cond.split('==');
      const leftVal = resolvePath(context, left.trim());
      let rightVal = right.trim();
      if ((rightVal.startsWith('"') && rightVal.endsWith('"')) || (rightVal.startsWith("'") && rightVal.endsWith("'"))) {
        rightVal = rightVal.slice(1, -1);
      } else if (!isNaN(Number(rightVal))) {
        rightVal = Number(rightVal);
      } else {
        rightVal = resolvePath(context, rightVal) || rightVal;
      }
      return String(leftVal) === String(rightVal);
    } else if (cond.includes('!=')) {
      const [left, right] = cond.split('!=');
      const leftVal = resolvePath(context, left.trim());
      let rightVal = right.trim();
      if ((rightVal.startsWith('"') && rightVal.endsWith('"')) || (rightVal.startsWith("'") && rightVal.endsWith("'"))) {
        rightVal = rightVal.slice(1, -1);
      } else if (!isNaN(Number(rightVal))) {
        rightVal = Number(rightVal);
      } else {
        rightVal = resolvePath(context, rightVal) || rightVal;
      }
      return String(leftVal) !== String(rightVal);
    } else {
      const val = resolvePath(context, cond);
      return Boolean(val);
    }
  }

  function render(template, context = {}) {
    if (!template || typeof template !== 'string') return '';

    // 1. Tags condicionais {% if ... %} / {% unless ... %}
    let rendered = template.replace(TAG_REGEX, (match, tagType, cond, trueBody, falseBody = '') => {
      let isTrue = evalCondition(cond, context);
      if (tagType === 'unless') isTrue = !isTrue;
      return isTrue ? trueBody : falseBody;
    });

    // 2. Interpolação de variáveis e filtros {{ var | filter }}
    rendered = rendered.replace(VAR_REGEX, (match, expr) => {
      const parts = expr.split('|');
      const varName = parts[0].trim();
      let value = resolvePath(context, varName);

      for (let i = 1; i < parts.length; i++) {
        value = applyFilter(value, parts[i], context);
      }

      return value !== undefined && value !== null ? String(value) : '';
    });

    return rendered;
  }

  function extractVariables(template) {
    if (!template || typeof template !== 'string') return [];
    const vars = new Set();

    let match;
    const varRegex = new RegExp(VAR_REGEX);
    while ((match = varRegex.exec(template)) !== null) {
      const expr = match[1].trim();
      const rawVar = expr.split('|')[0].trim();
      if (rawVar) vars.add(rawVar.split('.')[0]);
    }

    const tagRegex = new RegExp(TAG_REGEX);
    while ((match = tagRegex.exec(template)) !== null) {
      const cond = match[2].trim();
      const parts = cond.split(/==|!=/);
      const varName = parts[0].trim();
      if (varName) vars.add(varName.split('.')[0]);
    }

    return Array.from(vars);
  }

  return {
    render,
    extractVariables
  };
});

"""Zero-dependency Liquid template engine for Second Brain and JEV playbooks.

Supports:
- Variable interpolation: {{ var }} and nested keys: {{ order.customer.name }}
- Common Liquid filters:
    - default: "fallback"
    - upcase, downcase, capitalize
    - strip, trim
    - replace: "search", "replace"
    - truncate: length
- Conditional blocks:
    - {% if var == 'val' %} ... {% else %} ... {% endif %}
    - {% if var %} ... {% endif %}
    - {% unless var %} ... {% endunless %}
"""
import re
from typing import Any, Dict, List, Optional


_VAR_PATTERN = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_TAG_PATTERN = re.compile(
    r"\{%\s*(if|unless)\s+(.*?)\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*(?:endif|endunless)\s*%\}",
    re.DOTALL,
)


def _resolve_lookup(context: Dict[str, Any], path: str) -> Any:
    """Resolve a dot-notated path inside a nested context dictionary."""
    parts = path.strip().split(".")
    curr = context
    for part in parts:
        if isinstance(curr, dict):
            curr = curr.get(part)
        elif hasattr(curr, part):
            curr = getattr(curr, part)
        else:
            return None
        if curr is None:
            return None
    return curr


def _apply_filter(value: Any, filter_expr: str, context: Dict[str, Any]) -> Any:
    """Apply a single filter like `default: 'val'` or `upcase`."""
    parts = filter_expr.strip().split(":", 1)
    filter_name = parts[0].strip().lower()
    arg = parts[1].strip() if len(parts) > 1 else None

    # Unquote argument if it's a string literal
    if arg:
        if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
            arg_val = arg[1:-1]
        elif arg.isdigit():
            arg_val = int(arg)
        else:
            arg_val = _resolve_lookup(context, arg) or arg
    else:
        arg_val = None

    if filter_name == "default":
        if value is None or value == "" or value is False:
            return arg_val
        return value
    elif filter_name == "upcase":
        return str(value).upper() if value is not None else ""
    elif filter_name == "downcase":
        return str(value).lower() if value is not None else ""
    elif filter_name == "capitalize":
        return str(value).capitalize() if value is not None else ""
    elif filter_name in ("strip", "trim"):
        return str(value).strip() if value is not None else ""
    elif filter_name == "truncate":
        limit = int(arg_val) if arg_val is not None else 100
        s = str(value) if value is not None else ""
        return s[:limit] + "..." if len(s) > limit else s
    elif filter_name == "replace":
        s = str(value) if value is not None else ""
        if arg:
            args = [a.strip().strip("'\"") for a in arg.split(",", 1)]
            search = args[0]
            replace_with = args[1] if len(args) > 1 else ""
            return s.replace(search, replace_with)
        return s
    return value


def _eval_condition(cond_str: str, context: Dict[str, Any]) -> bool:
    """Evaluate a conditional expression like `var == 'val'`, `var != 'val'`, or truthiness."""
    cond = cond_str.strip()
    if "==" in cond:
        left, right = cond.split("==", 1)
        left_val = _resolve_lookup(context, left.strip())
        right_raw = right.strip()
        if (right_raw.startswith("'") and right_raw.endswith("'")) or (right_raw.startswith('"') and right_raw.endswith('"')):
            right_val = right_raw[1:-1]
        elif right_raw.isdigit():
            right_val = int(right_raw)
        else:
            right_val = _resolve_lookup(context, right_raw) or right_raw
        return str(left_val or "") == str(right_val or "")
    elif "!=" in cond:
        left, right = cond.split("!=", 1)
        left_val = _resolve_lookup(context, left.strip())
        right_raw = right.strip()
        if (right_raw.startswith("'") and right_raw.endswith("'")) or (right_raw.startswith('"') and right_raw.endswith('"')):
            right_val = right_raw[1:-1]
        elif right_raw.isdigit():
            right_val = int(right_raw)
        else:
            right_val = _resolve_lookup(context, right_raw) or right_raw
        return str(left_val or "") != str(right_val or "")
    else:
        val = _resolve_lookup(context, cond)
        return bool(val)


def render_liquid(template: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Render a Liquid template string using the provided context."""
    if not template:
        return ""
    ctx = context or {}

    # 1. Evaluate {% if ... %} and {% unless ... %} blocks
    def _replace_tag(match):
        tag_type = match.group(1)
        condition = match.group(2)
        true_body = match.group(3)
        false_body = match.group(4) or ""

        cond_result = _eval_condition(condition, ctx)
        if tag_type == "unless":
            cond_result = not cond_result

        return true_body if cond_result else false_body

    rendered = _TAG_PATTERN.sub(_replace_tag, template)

    # 2. Evaluate {{ var | filter }} expressions
    def _replace_var(match):
        expr = match.group(1).strip()
        if not expr:
            return ""

        parts = expr.split("|")
        var_name = parts[0].strip()
        value = _resolve_lookup(ctx, var_name)

        for filter_expr in parts[1:]:
            value = _apply_filter(value, filter_expr, ctx)

        if value is None:
            return ""
        return str(value)

    rendered = _VAR_PATTERN.sub(_replace_var, rendered)
    return rendered


def extract_liquid_variables(template: str) -> List[str]:
    """Extract all unique variable names referenced in the template."""
    vars_found = set()
    for match in _VAR_PATTERN.finditer(template):
        expr = match.group(1).strip()
        var_name = expr.split("|")[0].strip()
        if var_name:
            vars_found.add(var_name.split(".")[0])

    for match in _TAG_PATTERN.finditer(template):
        cond = match.group(2).strip()
        for op in ("==", "!="):
            if op in cond:
                cond = cond.split(op)[0].strip()
        if cond:
            vars_found.add(cond.split(".")[0])

    return sorted(list(vars_found))

"""Flow node input parameters & output return values (GitHub issue #4).

Every flow node may declare:

* ``config.inputs``  — named parameters the node consumes. A value comes from
  a previous node's output (matched by name, via the shared flow context),
  from the parameter's literal default, or from an expression rendered against
  the context.
* ``config.outputs`` — named return values the node produces. Later nodes can
  consume them either through their own ``inputs`` or by writing ``{name}``
  placeholders directly into a command / expected value / condition.

Both the code generator (:mod:`app.services.codegen_service`) and the runtime
engine (:mod:`app.services.execution_service`) use this module, so a generated
script and an actual run resolve variables identically.

Data shape (all fields optional except ``name``)::

    config = {
        "inputs": [
            {"name": "voltage", "type": "float", "default": "12.0", "desc": "输入电压"},
        ],
        "outputs": [
            {"name": "measured", "type": "float", "value": "response", "desc": "实测电压"},
        ],
    }
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

#: ``{variable}`` placeholder used inside commands / expectations / conditions.
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

#: Value types offered by the UI.
VALUE_TYPES = ("string", "int", "float", "bool", "hex", "any")

# Names always available inside an output/condition expression.
_RESERVED = ("response",)


# --------------------------------------------------------------------------- #
# Spec normalisation
# --------------------------------------------------------------------------- #

def _as_list(raw: Any) -> List[Dict[str, Any]]:
    """Normalise a stored ``inputs`` / ``outputs`` value to a list of dicts."""
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    if isinstance(raw, dict):
        return [
            {"name": k, **(v if isinstance(v, dict) else {"default": v})}
            for k, v in raw.items()
        ]
    return []


def node_config(node: Dict[str, Any]) -> Dict[str, Any]:
    config = (node or {}).get("config")
    return config if isinstance(config, dict) else {}


def node_inputs(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the declared input parameters of a node."""
    specs = []
    for spec in _as_list(node_config(node).get("inputs")):
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        specs.append({
            "name": name,
            "type": str(spec.get("type") or "string"),
            "default": spec.get("default"),
            "desc": spec.get("desc") or "",
        })
    return specs


def node_outputs(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the declared output return values of a node."""
    specs = []
    for spec in _as_list(node_config(node).get("outputs")):
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        specs.append({
            "name": name,
            "type": str(spec.get("type") or "string"),
            "value": spec.get("value"),
            "desc": spec.get("desc") or "",
        })
    return specs


# --------------------------------------------------------------------------- #
# Value coercion / rendering
# --------------------------------------------------------------------------- #

def coerce_value(value: Any, vtype: str = "string") -> Any:
    """Convert a declared value into the requested Python type.

    Unparseable values fall back to the raw text so a bad configuration never
    crashes a whole execution.
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool)) and vtype in ("any", "", None):
        return value
    text = str(value).strip()
    if text == "":
        return None
    try:
        if vtype == "int":
            try:
                return int(text, 0)
            except ValueError:
                return int(float(text))
        if vtype == "float":
            return float(text)
        if vtype == "bool":
            return text.lower() in ("true", "1", "yes", "y", "on")
        if vtype == "hex":
            return hex(int(text, 16)) if not text.lower().startswith("0x") else text.lower()
    except (ValueError, TypeError):
        return text
    return text


def render_template(text: Any, ctx: Optional[Dict[str, Any]]) -> Any:
    """Replace ``{name}`` placeholders in *text* with values from *ctx*.

    Unknown placeholders are left untouched so the user can spot typos in the
    generated code / execution log instead of silently getting an empty string.
    """
    if text is None or not isinstance(text, str) or "{" not in text:
        return text
    ctx = ctx or {}

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1).strip()
        if key in ctx:
            value = ctx[key]
            return "" if value is None else str(value)
        return m.group(0)

    return PLACEHOLDER_RE.sub(_sub, text)


def has_placeholder(text: Any) -> bool:
    return isinstance(text, str) and bool(PLACEHOLDER_RE.search(text))


# --------------------------------------------------------------------------- #
# Safe expression evaluation (used for outputs & conditions)
# --------------------------------------------------------------------------- #

_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len,
    "int": int, "float": float, "str": str, "bool": bool, "sum": sum,
    "sorted": sorted, "enumerate": enumerate,
}


def safe_eval(expression: str, scope: Optional[Dict[str, Any]] = None) -> Any:
    """Evaluate a small expression against *scope*, tolerating failures.

    Only a whitelist of builtins is exposed; a failure returns ``None`` so a
    single bad expression never aborts a run (the caller decides what to do).
    """
    expr = str(expression or "").strip()
    if not expr:
        return None
    scope = scope or {}
    if expr in scope:
        return scope[expr]
    try:
        return eval(expr, {"__builtins__": _SAFE_BUILTINS}, dict(scope))  # noqa: S307
    except Exception as e:  # noqa: BLE001 - deliberate: bad user expression
        logger.warning(f"Failed to evaluate expression {expr!r}: {e}")
        return None


def eval_condition(expression: str, ctx: Optional[Dict[str, Any]] = None) -> Optional[bool]:
    """Evaluate a condition expression with the flow context as variables."""
    expr = str(expression or "").strip()
    if not expr:
        return None
    value = safe_eval(expr, ctx or {})
    if value is None:
        return None
    return bool(value)


# --------------------------------------------------------------------------- #
# Context lifecycle
# --------------------------------------------------------------------------- #

def init_node_variables(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the variable declarations of an init/reset node (issue #5)."""
    specs = []
    for spec in _as_list(node_config(node).get("variables")):
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        specs.append({
            "name": name,
            "type": str(spec.get("type") or "string"),
            "value": spec.get("value"),
            "desc": spec.get("desc") or "",
        })
    return specs


def seed_context(nodes: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    """Build the initial flow context from every init node's declarations."""
    ctx: Dict[str, Any] = {}
    for node in nodes or []:
        if (node or {}).get("type") != "init":
            continue
        for spec in init_node_variables(node):
            ctx[spec["name"]] = coerce_value(spec["value"], spec["type"])
        # An init node may also declare outputs (e.g. a constant it exports).
        for spec in node_outputs(node):
            ctx[spec["name"]] = coerce_value(spec["value"], spec["type"])
    return ctx


def resolve_inputs(
    node: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve a node's declared inputs against the current context.

    Precedence: context value (produced by an earlier node) → declared default.
    """
    resolved: Dict[str, Any] = {}
    for spec in node_inputs(node):
        name = spec["name"]
        if name in ctx and ctx[name] is not None:
            resolved[name] = ctx[name]
            continue
        default = spec.get("default")
        if has_placeholder(default):
            resolved[name] = render_template(default, ctx)
        else:
            resolved[name] = coerce_value(default, spec["type"])
    return resolved


def collect_outputs(
    node: Dict[str, Any],
    ctx: Dict[str, Any],
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate a node's declared outputs and return them as a dict.

    *scope* holds node-local names (``response``, ``parsed_0``, ``voltage`` …).
    An empty ``value`` defaults to ``response`` (the last device reply).
    """
    scope = dict(scope or {})
    produced: Dict[str, Any] = {}
    for spec in node_outputs(node):
        expr = spec.get("value")
        expr = "response" if expr is None or str(expr).strip() == "" else str(expr).strip()
        if expr in scope:
            value = scope[expr]
        else:
            value = safe_eval(expr, scope)
            if value is None and has_placeholder(expr):
                value = render_template(expr, ctx)
            elif value is None:
                value = expr
        produced[spec["name"]] = coerce_value(value, spec["type"]) if spec["type"] != "any" else value
    return produced


def available_variables(
    nodes: Optional[Iterable[Dict[str, Any]]], before_node_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List variables available for ``{placeholder}`` references.

    Returns one entry per declared output / init variable with the producing
    node's label, so the UI can show a "可用变量" cheatsheet.
    """
    found: List[Dict[str, Any]] = []
    seen = set()
    for node in nodes or []:
        node_id = (node or {}).get("id")
        if before_node_id and node_id == before_node_id:
            break
        label = ((node or {}).get("data") or {}).get("label") or node_id or ""
        ntype = (node or {}).get("type")
        specs: List[Dict[str, Any]] = []
        if ntype == "init":
            specs = init_node_variables(node)
        specs = specs + node_outputs(node)
        for spec in specs:
            if spec["name"] in seen:
                continue
            seen.add(spec["name"])
            found.append({
                "name": spec["name"],
                "type": spec.get("type") or "string",
                "desc": spec.get("desc") or "",
                "source_label": label,
                "source_node_id": node_id,
            })
    return found


# --------------------------------------------------------------------------- #
# Generated-script helpers (mirrored into emitted code by the code generator)
# --------------------------------------------------------------------------- #

RUNTIME_HELPER = r'''

def _r(text, ctx):
    """Render ``{var}`` placeholders in *text* from the flow context."""
    if text is None:
        return text
    s = str(text)

    def _sub(m):
        key = m.group(1).strip()
        if key in ctx:
            v = ctx[key]
            return "" if v is None else str(v)
        return m.group(0)

    return re.sub(r"\{([^{}]+)\}", _sub, s)


def _cast(value, vtype="string"):
    """Coerce a declared parameter value into the requested type."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        if vtype == "int":
            try:
                return int(s, 0)
            except ValueError:
                return int(float(s))
        if vtype == "float":
            return float(s)
        if vtype == "bool":
            return s.lower() in ("true", "1", "yes", "y", "on")
        if vtype == "hex":
            return hex(int(s, 16)) if not s.lower().startswith("0x") else s.lower()
    except (ValueError, TypeError):
        return s
    return s


def _p(name, ctx, default=None, vtype="string"):
    """Resolve a declared node input parameter from the flow context."""
    if name in ctx and ctx[name] is not None:
        return ctx[name]
    return _cast(_r(default, ctx), vtype)


def _out(expr, scope):
    """Evaluate a node output expression against the node's local scope."""
    if expr is None or not str(expr).strip():
        return scope.get("response")
    expr = str(expr).strip()
    if expr in scope:
        return scope[expr]
    try:
        return eval(expr, {"__builtins__": {}}, dict(scope))
    except Exception:
        return _r(expr, scope)


def _cond(expr, ctx):
    """Evaluate a condition expression with the flow context as variables."""
    try:
        return bool(eval(expr, {"__builtins__": {}}, dict(ctx)))
    except Exception as e:
        raise AssertionError(f"条件表达式求值失败: {expr} ({e})")
'''

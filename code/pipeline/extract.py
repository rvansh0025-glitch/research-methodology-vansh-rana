"""Step 1 - Extraction.

Pull every package reference out of an LLM response:
  * Python: `import` / `from ... import` statements (parsed with `ast`),
    `pip install` lines and requirements.txt content.
  * JavaScript: `import ... from`, dynamic `import()` and `require()` calls,
    `npm` / `yarn` / `pnpm` install lines and package.json dependencies.

Each reference is returned as a dict:
  {"name": str, "kind": "import" | "install" | "manifest",
   "ecosystem": "pypi" | "npm", "relative": bool}
"""
from __future__ import annotations

import ast
import json
import re

CODE_BLOCK = re.compile(r"```[ \t]*([\w+.-]*)[^\n]*\n(.*?)```", re.S)

PY_LANGS = {"python", "py", "python3", "ipython"}
JS_LANGS = {"javascript", "js", "jsx", "typescript", "ts", "tsx", "node", "mjs", "cjs"}
SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh", "powershell", "ps", "cmd", "terminal"}

# --- install commands -------------------------------------------------------
PIP_CMD = re.compile(
    r"(?:^|[\s;&|`$>])(?:python[\d.]*\s+-m\s+)?pip[\d.]*\s+install\s+([^\n#;&|`]+)", re.M
)
NPM_CMD = re.compile(
    r"(?:^|[\s;&|`$>])(?:npm\s+(?:install|i|add)|yarn\s+(?:global\s+)?add|pnpm\s+(?:add|install|i))"
    r"\s+([^\n#;&|`]+)",
    re.M,
)
PIP_FLAGS_WITH_VALUE = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable",
                        "-i", "--index-url", "--extra-index-url", "-f", "--find-links",
                        "-t", "--target", "--prefix", "--root"}

# --- JavaScript import forms ------------------------------------------------
JS_IMPORT_FROM = re.compile(r"""\bimport\s+(?:type\s+)?[\w*${}\s,]+?\s+from\s+['"]([^'"]+)['"]""")
JS_IMPORT_BARE = re.compile(r"""\bimport\s+['"]([^'"]+)['"]""")
JS_EXPORT_FROM = re.compile(r"""\bexport\s+[\w*{}\s,]+?\s+from\s+['"]([^'"]+)['"]""")
JS_DYNAMIC = re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)""")
JS_REQUIRE = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
JS_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)

# fallback for Python snippets that do not parse (e.g. contain "..." placeholders)
PY_IMPORT_LINE = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\b|import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*))", re.M)

REQ_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]*\])?\s*([<>=!~]=?.*)?$")


def code_blocks(text: str) -> list[tuple[str, str]]:
    """Return (language_tag, body) for every fenced code block."""
    return [(lang.lower(), body) for lang, body in CODE_BLOCK.findall(text)]


def _ref(name: str, kind: str, eco: str, relative: bool = False) -> dict:
    return {"name": name, "kind": kind, "ecosystem": eco, "relative": relative}


# --- Python -----------------------------------------------------------------
def python_imports(code: str) -> list[dict]:
    refs = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        for frm, imp in PY_IMPORT_LINE.findall(code):
            if frm:
                rel = frm.startswith(".")
                top = frm.lstrip(".").split(".")[0]
                if top or rel:
                    refs.append(_ref(top or ".", "import", "pypi", rel))
            else:
                for part in imp.split(","):
                    top = part.strip().split()[0].split(".")[0]
                    refs.append(_ref(top, "import", "pypi"))
        return refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(_ref(alias.name.split(".")[0], "import", "pypi"))
        elif isinstance(node, ast.ImportFrom):
            rel = (node.level or 0) > 0
            top = (node.module or "").split(".")[0]
            refs.append(_ref(top or ".", "import", "pypi", rel))
    return refs


def _clean_pip_token(tok: str) -> str | None:
    tok = tok.strip().strip("'\"")
    if not tok or tok.startswith(("-", ".", "/", "git+", "http:", "https:", "file:")):
        return None
    if tok.endswith((".whl", ".tar.gz", ".zip", ".txt")):
        return None
    name = re.split(r"[\[<>=!~;@\s]", tok, maxsplit=1)[0]
    return name or None


def pip_installs(text: str) -> list[dict]:
    refs = []
    for args in PIP_CMD.findall(text):
        toks = args.split()
        skip = False
        for tok in toks:
            if skip:
                skip = False
                continue
            if tok in PIP_FLAGS_WITH_VALUE:
                skip = True
                continue
            name = _clean_pip_token(tok)
            if name:
                refs.append(_ref(name, "install", "pypi"))
    return refs


def requirements_txt(body: str) -> list[dict]:
    lines = [l.split("#")[0].strip() for l in body.splitlines()]
    lines = [l for l in lines if l]
    if not lines or not all(REQ_LINE.match(l) for l in lines):
        return []
    return [_ref(re.split(r"[\[<>=!~;\s]", l, maxsplit=1)[0], "manifest", "pypi") for l in lines]


# --- JavaScript -------------------------------------------------------------
def _js_package(spec: str) -> tuple[str, bool]:
    """Turn a module specifier into (package_name, is_relative)."""
    if spec.startswith((".", "/")) or spec.startswith(("http:", "https:")):
        return spec, True
    if spec.startswith("node:"):
        return spec, False
    parts = spec.split("/")
    if spec.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2]), False
    return parts[0], False


def js_imports(code: str) -> list[dict]:
    code = JS_COMMENT.sub("", code)
    refs = []
    for rx in (JS_IMPORT_FROM, JS_IMPORT_BARE, JS_EXPORT_FROM, JS_DYNAMIC, JS_REQUIRE):
        for spec in rx.findall(code):
            name, rel = _js_package(spec)
            refs.append(_ref(name, "import", "npm", rel))
    return refs


def _clean_npm_token(tok: str) -> str | None:
    tok = tok.strip().strip("'\"")
    if not tok or tok.startswith(("-", ".", "/", "git+", "http:", "https:", "file:")):
        return None
    if tok.startswith("@"):
        parts = tok.split("@")  # ['', 'scope/name', 'version'?]
        return "@" + parts[1] if len(parts) > 1 and "/" in parts[1] else None
    return tok.split("@")[0] or None


def npm_installs(text: str) -> list[dict]:
    refs = []
    for args in NPM_CMD.findall(text):
        for tok in args.split():
            name = _clean_npm_token(tok)
            if name:
                refs.append(_ref(name, "install", "npm"))
    return refs


def package_json(body: str) -> list[dict]:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    refs = []
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = data.get(key)
        if isinstance(deps, dict):
            refs.extend(_ref(name, "manifest", "npm") for name in deps)
    return refs


# --- entry point ------------------------------------------------------------
def extract(text: str, prog_language: str) -> list[dict]:
    """Extract all package references from one LLM response.

    prog_language is the task's language ("python" or "javascript"); it decides
    how untagged code blocks are parsed.
    """
    prog_language = prog_language.lower()
    default_lang = "python" if prog_language.startswith("py") else "javascript"
    refs: list[dict] = []
    for lang, body in code_blocks(text):
        tag = lang or default_lang
        if tag in PY_LANGS:
            refs += python_imports(body)
        elif tag in JS_LANGS:
            refs += js_imports(body)
        elif tag in {"json"}:
            refs += package_json(body)
        elif tag in {"text", "txt", "requirements", "requirements.txt", "pip"}:
            refs += requirements_txt(body)
    # install commands can appear in shell blocks or inline prose
    refs += pip_installs(text)
    refs += npm_installs(text)
    return refs

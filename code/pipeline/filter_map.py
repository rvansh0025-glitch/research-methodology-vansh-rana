"""Steps 2 and 3 - Filtering and name mapping.

Filtering removes references that can never be hallucinated third-party
packages: standard-library modules, Node built-ins, relative imports and
modules the response itself defines (e.g. a `utils.py` it also writes).

Mapping converts Python import names to PyPI distribution names
(`cv2` -> `opencv-python`) using a curated table plus the metadata of any
packages installed locally. Install-command and manifest names are already
distribution names and are only normalised.
"""
from __future__ import annotations

import re
import sys

try:
    from importlib.metadata import packages_distributions
except ImportError:  # Python < 3.10
    packages_distributions = None

PY_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}

# require('module').builtinModules for Node 20/22
NODE_BUILTINS = {
    "assert", "assert/strict", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "dns/promises", "domain",
    "events", "fs", "fs/promises", "http", "http2", "https", "inspector", "module", "net", "os",
    "path", "path/posix", "path/win32", "perf_hooks", "process", "punycode", "querystring",
    "readline", "readline/promises", "repl", "stream", "stream/consumers", "stream/promises",
    "stream/web", "string_decoder", "sys", "test", "timers", "timers/promises", "tls",
    "trace_events", "tty", "url", "util", "util/types", "v8", "vm", "wasi", "worker_threads",
    "zlib",
}

# Import name -> PyPI distribution name, where the two differ.
IMPORT_TO_DIST = {
    "cv2": "opencv-python", "sklearn": "scikit-learn", "skimage": "scikit-image",
    "PIL": "Pillow", "yaml": "PyYAML", "bs4": "beautifulsoup4", "dateutil": "python-dateutil",
    "dotenv": "python-dotenv", "jwt": "PyJWT", "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodomex", "serial": "pyserial", "usb": "pyusb", "attr": "attrs",
    "magic": "python-magic", "docx": "python-docx", "pptx": "python-pptx",
    "telegram": "python-telegram-bot", "OpenSSL": "pyOpenSSL", "MySQLdb": "mysqlclient",
    "fitz": "PyMuPDF", "git": "GitPython", "Levenshtein": "python-Levenshtein",
    "websocket": "websocket-client", "zmq": "pyzmq", "gi": "PyGObject", "win32api": "pywin32",
    "win32con": "pywin32", "win32com": "pywin32", "pythoncom": "pywin32", "wx": "wxPython",
    "slugify": "python-slugify", "multipart": "python-multipart", "jose": "python-jose",
    "socketio": "python-socketio", "engineio": "python-engineio",
    "speech_recognition": "SpeechRecognition", "google.protobuf": "protobuf",
    "pkg_resources": "setuptools", "faiss": "faiss-cpu", "tensorflow_hub": "tensorflow-hub",
    "Bio": "biopython", "nacl": "PyNaCl", "kafka": "kafka-python", "ldap": "python-ldap",
    "dns": "dnspython", "lxml": "lxml", "markdown": "Markdown", "flask_cors": "Flask-Cors",
    "flask_sqlalchemy": "Flask-SQLAlchemy", "flask_login": "Flask-Login",
    "googleapiclient": "google-api-python-client", "discord": "discord.py",
    "pygame": "pygame", "osgeo": "GDAL", "mpl_toolkits": "matplotlib",
}


def normalise(name: str, ecosystem: str) -> str:
    """PEP 503 normalisation for PyPI; npm names are case-sensitive lowercase already."""
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name.strip()


def local_modules(text: str) -> set[str]:
    """Module names the response defines itself, e.g. it writes `utils.py` or `db.js`."""
    return set(re.findall(r"\b([A-Za-z_][\w-]*)\.(?:py|js|mjs|cjs|ts)\b", text))


def is_filtered(ref: dict, local: set[str]) -> str | None:
    """Return the reason a reference is dropped, or None to keep it."""
    name = ref["name"]
    if ref.get("relative") or name in {"", "."}:
        return "relative"
    if ref["ecosystem"] == "pypi":
        if ref["kind"] == "import" and name in PY_STDLIB:
            return "stdlib"
    else:
        if name.startswith("node:") or name in NODE_BUILTINS:
            return "builtin"
    if ref["kind"] == "import" and name in local:
        return "local"
    return None


_installed = None


def _installed_map() -> dict:
    global _installed
    if _installed is None:
        _installed = {}
        if packages_distributions is not None:
            for mod, dists in packages_distributions().items():
                if dists:
                    _installed[mod] = dists[0]
    return _installed


def to_distribution(ref: dict) -> str:
    """Map a reference to the name we look up in the registry."""
    name = ref["name"]
    if ref["ecosystem"] == "pypi" and ref["kind"] == "import":
        name = IMPORT_TO_DIST.get(name) or _installed_map().get(name) or name
    return normalise(name, ref["ecosystem"])


def filter_and_map(refs: list[dict], response_text: str) -> list[dict]:
    """Drop non-third-party references, add `dist` and deduplicate per response."""
    local = local_modules(response_text)
    out, seen = [], set()
    for ref in refs:
        if is_filtered(ref, local):
            continue
        dist = to_distribution(ref)
        key = (ref["ecosystem"], dist)
        if key in seen:
            continue
        seen.add(key)
        out.append({**ref, "dist": dist})
    return out

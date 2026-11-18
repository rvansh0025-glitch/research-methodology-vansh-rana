"""Offline tests for the extraction-and-verification pipeline.

Run from the `code/` folder:  python -m unittest discover -s tests -v
"""
import csv
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)

from pipeline.extract import extract, pip_installs, npm_installs, js_imports, python_imports  # noqa: E402
from pipeline.filter_map import filter_and_map  # noqa: E402
from pipeline.verify import classify  # noqa: E402
from pipeline import run_pipeline, metrics  # noqa: E402

DATA = os.path.join(CODE, "data")
FENCE = "`" * 3


def names(refs):
    return sorted({r["name"] for r in refs})


class TestExtract(unittest.TestCase):
    def test_python_ast(self):
        refs = python_imports("import os, numpy as np\nfrom sklearn.svm import SVC\nfrom . import x\n")
        self.assertEqual(names([r for r in refs if not r["relative"]]), ["numpy", "os", "sklearn"])
        self.assertTrue(any(r["relative"] for r in refs))

    def test_python_fallback_on_syntax_error(self):
        refs = python_imports("import torch\n...\ndef f(:\n    pass\nfrom transformers import AutoModel\n")
        self.assertEqual(names(refs), ["torch", "transformers"])

    def test_pip_install_variants(self):
        refs = pip_installs("python -m pip install -U 'fastapi[all]>=0.110' uvicorn==0.29 -r requirements.txt")
        self.assertEqual(names(refs), ["fastapi", "uvicorn"])

    def test_npm_install_variants(self):
        refs = npm_installs("npm i -D jest @types/node@20 && yarn add lodash@^4 && pnpm add zod")
        self.assertEqual(names(refs), ["@types/node", "jest", "lodash", "zod"])

    def test_js_import_forms(self):
        code = ("import a from 'pkg-a';\nimport 'side-effect';\nimport {b} from '@scope/b/sub';\n"
                "const c = require(\"pkg-c/lib/x\");\nconst d = await import('pkg-d');\n"
                "export { e } from 'pkg-e';\n// require('ignored')\nimport z from './local';\n")
        refs = js_imports(code)
        self.assertEqual(names([r for r in refs if not r["relative"]]),
                         ["@scope/b", "pkg-a", "pkg-c", "pkg-d", "pkg-e", "side-effect"])

    def test_untagged_block_uses_task_language(self):
        text = f"{FENCE}\nimport numpy\n{FENCE}"
        self.assertEqual(names(extract(text, "python")), ["numpy"])


class TestFilterMap(unittest.TestCase):
    def test_filters_and_maps(self):
        text = (f"{FENCE}python\nimport os\nimport cv2\nfrom PIL import Image\nimport utils\n{FENCE}\n"
                "Put the helpers in utils.py")
        kept = filter_and_map(extract(text, "python"), text)
        self.assertEqual(sorted(r["dist"] for r in kept), ["opencv-python", "pillow"])

    def test_node_builtins_dropped(self):
        text = f"{FENCE}js\nconst fs = require('fs');\nimport p from 'node:path';\nimport x from 'express';\n{FENCE}"
        kept = filter_and_map(extract(text, "javascript"), text)
        self.assertEqual([r["dist"] for r in kept], ["express"])

    def test_dedup_import_and_install(self):
        text = f"pip install requests\n{FENCE}python\nimport requests\n{FENCE}"
        kept = filter_and_map(extract(text, "python"), text)
        self.assertEqual(len(kept), 1)


class TestClassify(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(DATA, "sample_snapshot.json"), encoding="utf-8") as f:
            self.snap = json.load(f)

    def test_labels(self):
        self.assertEqual(classify("pypi", "requests", self.snap, "2025-06-01"), "Valid")
        self.assertEqual(classify("pypi", "flask-ultrasecure-auth", self.snap, "2025-06-01"), "Hallucinated")
        self.assertEqual(classify("pypi", "py-quick-csvtools", self.snap, "2025-06-01"), "Suspect-squatted")
        self.assertEqual(classify("pypi", "not-in-snapshot", self.snap, "2025-06-01"), "Ambiguous")
        # without a cutoff we cannot call it squatted
        self.assertEqual(classify("pypi", "py-quick-csvtools", self.snap, None), "Valid")


class TestEndToEnd(unittest.TestCase):
    def test_sample_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "references.csv")
            run_pipeline.main([os.path.join(DATA, "sample_responses.jsonl"),
                               "--snapshot", os.path.join(DATA, "sample_snapshot.json"),
                               "--cutoffs", os.path.join(DATA, "sample_cutoffs.json"),
                               "--out", out])
            with open(out, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        labels = {(r["response_id"], r["dist"]): r["label"] for r in rows}
        self.assertEqual(labels[("R001", "flask-ultrasecure-auth")], "Hallucinated")
        self.assertEqual(labels[("R001", "opencv-python")], "Valid")
        self.assertEqual(labels[("R003", "py-quick-csvtools")], "Suspect-squatted")
        self.assertEqual(labels[("R004", "express-jwt-guard-pro")], "Hallucinated")
        self.assertEqual(labels[("R004", "@aws-sdk/client-s3")], "Valid")
        self.assertNotIn(("R001", "utils"), labels)       # defined locally
        self.assertNotIn(("R004", "fs"), labels)          # Node built-in
        self.assertNotIn(("R004", "commented-out-pkg"), labels)

        k, n, _ = metrics.package_rate(rows)
        self.assertEqual((k, n), (4, 16))
        k, n, _ = metrics.response_rate(rows)
        self.assertEqual((k, n), (4, 6))
        k, n, _ = metrics.repeat_rate(rows)
        self.assertEqual((k, n), (1, 3))  # flask-ultrasecure-auth in samples 0 and 1 of the same cell
        pairs, shared = metrics.jaccard_overlap(rows)
        self.assertEqual(shared, {("pypi", "flask-ultrasecure-auth")})

    def test_wilson(self):
        p, lo, hi = metrics.wilson(5, 100)
        self.assertAlmostEqual(p, 0.05)
        self.assertAlmostEqual(lo, 0.0215, places=3)
        self.assertAlmostEqual(hi, 0.1118, places=3)


if __name__ == "__main__":
    unittest.main()

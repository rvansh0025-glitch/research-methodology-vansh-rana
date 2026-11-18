# Research Methodology – Vansh Rana (SAP ID 590017823, Batch B2)

## Research Project
**Phantom Dependencies: Package Hallucination in LLM-Generated Code Across Models, Programming Languages, Prompt Languages and Guardrail Prompts**

Group: Vansh Rana (590017823), Anirudh Singh Aswal (590017310), Hardik Trivedi (590016152), Yash Shrivastava (590011391)

LLM coding assistants sometimes recommend packages that do not exist, and attackers can register those names with malware ("slopsquatting"). This study measures package hallucination across four current LLMs, Python and JavaScript, a zero-cost guardrail system prompt, and English vs. Hindi prompts (240 prompts, 23,040 generations), verified against time-anchored PyPI and npm snapshots.

| Folder | Contents |
|---|---|
| `code/` | Research code: extraction-and-verification pipeline, metrics, prompt sampling, GLMM analysis, tests |
| `research-paper/` | IEEE paper, Overleaf source (`main.tex`) |
| `research-proposal/` | Research proposal (PDF) |
| `presentation/` | 5-slide Beamer presentation (PDF + `beamer.tex`) |
| `literature-survey/` | Literature survey table |
| `dashboard/` | Individual AQI dashboard (Excel) and screenshot |
| `assignments/` | Worksheets 1–3 and midsem solution with summaries |

## Code and Data Availability

### Code (`code/`)
| File | Paper step |
|---|---|
| `pipeline/sample_prompts.py` | Stratified, seeded sample of 240 prompts (language x source x time segment, 30 per cell) |
| `data/system_prompts.json` | Baseline and guardrail system prompts |
| `pipeline/extract.py` | Step 1: extract Python imports (`ast`), JS `import`/`require()`, pip/npm/yarn/pnpm install lines, requirements.txt and package.json |
| `pipeline/filter_map.py` | Steps 2-3: drop stdlib / Node built-ins / relative / locally defined modules; map import names to distribution names (e.g. `cv2` -> `opencv-python`) |
| `pipeline/verify.py` | Steps 4-5: freeze PyPI + npm snapshot at T0; classify Valid / Hallucinated / Suspect-squatted / Ambiguous |
| `pipeline/run_pipeline.py` | Runs steps 1-5 on a JSONL of model responses -> `references.csv` |
| `pipeline/metrics.py` | Package- and response-level rates, repeat rate, cross-model Jaccard overlap, Wilson 95% CIs |
| `analysis/glmm.R` | Binomial GLMM (`lme4`) of Eq. 1, odds ratios, Holm-corrected tests of H1-H6 |
| `tests/test_pipeline.py` | Offline unit + end-to-end tests on the sample data |

Python 3.10+, standard library only. R needs `lme4` and `dplyr`.

```bash
cd code
python -m unittest discover -s tests -v                       # run tests
python -m pipeline.run_pipeline data/sample_responses.jsonl     --snapshot data/sample_snapshot.json --cutoffs data/sample_cutoffs.json --out references.csv
python -m pipeline.metrics references.csv --by model,prog_language
# real study, first run at T0 (queries PyPI/npm and freezes the snapshot):
python -m pipeline.run_pipeline responses.jsonl --snapshot snapshot.json --build-snapshot --cutoffs cutoffs.json
Rscript analysis/glmm.R references.csv tasks.csv
```

### Data
- **Prompt data:** public package-hallucination prompt dataset of Spracklen et al. (USENIX Security 2025) - https://zenodo.org/records/14676377 and https://github.com/Spracks/PackageHallucination
- **Package registries:** PyPI JSON API and npm registry, frozen at the start of data collection (T0).
- **Sample data:** `code/data/` holds small illustrative responses, registry snapshot and model cutoffs used by the tests (package names such as `flask-ultrasecure-auth` are made-up examples).
- **Study outputs:** sampled prompt IDs, Hindi translations, generated model outputs and the T0 snapshot will be released here after coordinated disclosure to the PyPI and npm security teams.
- **Dashboard data:** simulated AQI data for six Indian cities (2025), included in the Excel file.

## Compile
Open `research-paper/main.tex` or `presentation/beamer.tex` in Overleaf (IEEEtran and Beamer are built in).

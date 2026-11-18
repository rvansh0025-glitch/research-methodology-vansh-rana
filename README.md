# Research Methodology – Vansh Rana (SAP ID 590017823, Batch B2)

## Research Project
**Phantom Dependencies: Package Hallucination in LLM-Generated Code Across Models, Programming Languages, Prompt Languages and Guardrail Prompts**

Group: Vansh Rana (590017823), Anirudh Singh Aswal (590017310), Hardik Trivedi (590016152), Yash Shrivastava (590011391)

LLM coding assistants sometimes recommend packages that do not exist, and attackers can register those names with malware ("slopsquatting"). This study measures package hallucination across four current LLMs, Python and JavaScript, a zero-cost guardrail system prompt, and English vs. Hindi prompts (240 prompts, 23,040 generations), verified against time-anchored PyPI and npm snapshots.

| Folder | Contents |
|---|---|
| `research-paper/` | IEEE paper, Overleaf source (`main.tex`) |
| `research-proposal/` | Research proposal (PDF) |
| `presentation/` | 5-slide Beamer presentation (`beamer.tex`) |
| `literature-survey/` | Literature survey table |
| `dashboard/` | Individual AQI dashboard (Excel) and screenshot |
| `assignments/` | Worksheets 1–3 and midsem solution with summaries |

## Code and Data Availability
- **Prompt data:** public package-hallucination prompt dataset of Spracklen et al. (USENIX Security 2025) – https://zenodo.org/records/14676377 and https://github.com/Spracks/PackageHallucination
- **Package registries:** PyPI JSON API (https://pypi.org/pypi/<name>/json) and npm registry (https://registry.npmjs.org/<name>), snapshotted at the start of data collection (T0).
- **Code:** the extraction-and-verification pipeline (import/install extraction, stdlib filtering, import-to-distribution mapping, registry check, classification) and the GLMM analysis scripts will be added to this repository.
- **Our data:** sampled prompt IDs, Hindi translations and generated model outputs will be released here after coordinated disclosure to the PyPI and npm security teams.
- **Dashboard data:** simulated AQI data for six Indian cities (2025), included in the Excel file.

## Compile
Open `research-paper/main.tex` or `presentation/beamer.tex` in Overleaf (IEEEtran and Beamer are built in).

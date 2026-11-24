# AI System Compromise & Resilience Assessment (Finance Edition)

Capstone project for the Udacity AI Security nanodegree. In the role of an **AI Red Team Operator** at FinanceGuard Inc., this assessment executes five adversarial attacks against a financial AI system — a receipt-image classifier and an expense-policy RAG chatbot — and reports the findings for a security and executive audience.

**Status: complete.** All five attack scripts are implemented and run, and all nine report documents are written. Deliverables are in [`starter/doc_delivery/`](starter/doc_delivery/); raw outputs are in `starter/attacks/results/`.

## Results Summary

| # | Attack | Target | Key Result | Severity |
|---|--------|--------|-----------|----------|
| 1 | FGSM Evasion | Receipt Classifier | Accuracy coin-flip (0.51) by ε=0.03, below 50% (0.30) at ε=0.05 (68% attack success); a car photo passes as a receipt with near-invisible noise | HIGH |
| 2 | Label-Flip Poisoning | Training Pipeline | Targeted flip of the 115 most prototypical receipts (<10% of labels) collapses accuracy 0.9436 → 0.5923 (−35 pts); random flips are harmless | HIGH |
| 3 | Prompt Injection | RAG Chatbot | 2/5 techniques succeed at the answer level (forged-context fake policy, persona data leak); 3/5 leak the confidential file at retrieval | HIGH |
| 4 | Data Exfiltration | RAG Vector Store | 6/6 queries retrieve `executive_bonus_structure_CONFIDENTIAL.md` (restricted-source leak); 5/6 also disclose figures in the answer — CEO pay, $47.50 strike price, clawback terms | CRITICAL |
| 5 | Supply Chain Analysis | Docker / Dependencies | 804 CVEs (34 HIGH); 6 Dockerfile issues incl. root user and the API key baked in via `COPY .` | HIGH |

## For the Reviewer

All written deliverables are in [`starter/doc_delivery/`](starter/doc_delivery/) (`*_delivered.md`):

| Document | Covers |
|----------|--------|
| [`charter_delivered.md`](starter/doc_delivery/charter_delivered.md) | Red Team Charter — engagement, objectives, scope, rules of engagement, success criteria |
| [`fgsm_results_delivered.md`](starter/doc_delivery/fgsm_results_delivered.md) | FGSM epsilon sweep, visual evidence, analysis |
| [`poisoning_results_delivered.md`](starter/doc_delivery/poisoning_results_delivered.md) | Clean vs. poisoned metrics, confusion matrices, targeted-vs-random analysis |
| [`prompt_injection_transcript_delivered.md`](starter/doc_delivery/prompt_injection_transcript_delivered.md) | 5 injection techniques, full transcripts, both success signals |
| [`data_exfiltration_evidence_delivered.md`](starter/doc_delivery/data_exfiltration_evidence_delivered.md) | 6 exfiltration queries, leaked data, root cause |
| [`supply_chain_analysis_delivered.md`](starter/doc_delivery/supply_chain_analysis_delivered.md) | Trivy CVE breakdown, Dockerfile review, prioritized remediation |
| [`vulnerability_log_delivered.md`](starter/doc_delivery/vulnerability_log_delivered.md) | All 5 findings: severity, evidence, recommendation |
| [`executive_summary_delivered.md`](starter/doc_delivery/executive_summary_delivered.md) | Business-audience risk summary and remediation priorities |
| [`reproduction_steps_delivered.md`](starter/doc_delivery/reproduction_steps_delivered.md) | Copy-pasteable commands and expected output for every finding |

Supporting evidence:
- **Attack scripts:** [`starter/attacks/`](starter/attacks/) — `01_fgsm_evasion.py` … `05_supply_chain_analysis.py`
- **Raw results:** `starter/attacks/results/` — JSON per attack, FGSM comparison PNGs, poisoning confusion matrices
- **Poisoning manifest:** `starter/attacks/prototypical_manifest.txt` — the exact 115-file flip set that reproduces the targeted-poisoning result

To reproduce any finding, follow [`reproduction_steps_delivered.md`](starter/doc_delivery/reproduction_steps_delivered.md).

## Repository Layout

```
.
├── starter/
│   ├── classifier/        # Receipt CNN — system under test (given), + trained poisoned ckpt
│   ├── attacks/           # 5 attack scripts (implemented) + prototypical_manifest.txt
│   │   └── results/       # JSON outputs, plots, confusion matrices
│   ├── rag_chatbot/       # Expense chatbot — system under test (given)
│   ├── doc_delivery/      # ← DELIVERABLES: the 9 *_delivered.md reports
│   ├── docs/              # Blank templates the deliverables are based on
│   ├── .env.example       # API key configuration template
│   ├── 06_trivy_report.json
│   ├── requirements.txt
│   └── Dockerfile
├── LICENSE.txt
└── CODEOWNERS
```

## The 5 Attacks

| # | Attack | Target | Objective |
|---|--------|--------|-----------|
| 1 | FGSM Evasion | Receipt Classifier | Craft adversarial images that fool the classifier |
| 2 | Label-Flip Poisoning | Training Pipeline | Corrupt training data to degrade model accuracy |
| 3 | Prompt Injection | RAG Chatbot | Override system instructions to manipulate behavior |
| 4 | Data Exfiltration | RAG Vector Store | Extract confidential documents through the chatbot |
| 5 | Supply Chain Analysis | Docker / Dependencies | Identify vulnerabilities via Trivy report and Dockerfile review |

## Reproducing the Attacks

Targets **Python 3.12**.

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # macOS/Linux; Windows: .venv\Scripts\activate
pip install -r starter/requirements.txt
pip install -r starter/rag_chatbot/requirements.txt

# Chatbot credentials (git-ignored; never committed)
cp starter/.env.example starter/rag_chatbot/.env
# edit to set OPENAI_API_KEY and OPENAI_BASE_URL
```

Verify the environment, then run any attack:

```bash
cd starter/classifier
python evaluate.py --model-path checkpoints/receipt_cnn_clean.pt --test-dir balanced_data/test
# Expected: ~94% accuracy (0.9436)

cd ../attacks
python 01_fgsm_evasion.py          # classifier attacks don't need the chatbot
```

The chatbot attacks (03, 04) need the Flask server running on port 5001; see
[`reproduction_steps_delivered.md`](starter/doc_delivery/reproduction_steps_delivered.md)
for the full, step-by-step commands and expected output for all five attacks.

> **macOS note:** `train.py` can hang after printing `Saved checkpoint` (DataLoader worker shutdown); the checkpoint is already written. Train on CPU for deterministic results.

## System Under Test (given — not modified)

The classifier, RAG chatbot, policy documents, Trivy report and Dockerfile are the target system and are left unchanged; the assessment treats them as a black/white-box target and only recommends fixes. The work product is the five attack scripts and the nine reports.

## License

[License](LICENSE.txt)

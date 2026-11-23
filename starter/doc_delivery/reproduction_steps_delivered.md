# Reproduction Steps

Every finding below is reproducible from a clean checkout. Commands are copy-pasteable from the `starter/` directory with the virtual environment activated. Fixed seeds (42) make the attacks deterministic, except for the chatbot (LLM, temperature 0.3), where outputs vary slightly between runs.

## Prerequisites

- Python 3.12 (project target), `git`, ~2 GB disk.
- A Vocareum/OpenAI API key with access to `gpt-4o-mini` and `text-embedding-3-small`.
- Hardware: CPU is sufficient. Training ~4 min/run; the FGSM sweep ~30 s. (On Apple Silicon, `train.py` uses the MPS backend.)

> **macOS note:** `train.py` can hang *after* printing `Saved checkpoint` (DataLoader worker shutdown). The checkpoint is already written — press Ctrl-C once you see that line, or run training in the background and stop it once the `.pt` file appears.

## Environment Setup

```bash
git clone https://github.com/Ignusmart/financeguard-red-team.git
cd financeguard-red-team
python3.12 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r starter/requirements.txt
pip install -r starter/rag_chatbot/requirements.txt

# Chatbot credentials (never commit this file):
cp starter/.env.example starter/rag_chatbot/.env
# edit starter/rag_chatbot/.env → set OPENAI_API_KEY and OPENAI_BASE_URL

cd starter
```

The repo ships the balanced dataset, the clean checkpoint, and a prebuilt FAISS index, so you can start at any attack.

## Step 1: Prepare Dataset

Already provided in `classifier/balanced_data/` (train/test × receipt/non_receipt). To rebuild from a raw source:

```bash
cd classifier
python data.py --source /path/to/raw/data --target balanced_data
cd ..
```

Expected: `[train] receipt: 577 images`, `[test] receipt: 195 images`, etc. (390 test images total).

## Step 2: Train and Evaluate Clean Model

```bash
cd classifier
python evaluate.py --model-path checkpoints/receipt_cnn_clean.pt --test-dir balanced_data/test
cd ..
```

Expected output (provided clean model):
```
Accuracy: 0.9436   Precision: 0.9943   Recall: 0.8923   F1: 0.9405
Confusion Matrix: [[194, 1], [21, 174]]
```

## Step 3: FGSM Attack

```bash
cd attacks
python 01_fgsm_evasion.py
cd ..
```

Expected: accuracy degrades across epsilons and PNGs are written to `attacks/results/01_fgsm/`.
```
 Epsilon   Clean Acc   Adv Acc   Attack Rate
   0.000      0.9436    0.9436       0.0000
   0.030      0.9436    0.5103       0.4592
   0.050      0.9436    0.3000       0.6821
   0.100      0.9436    0.2718       0.7120
```
Below 50% accuracy by ε≈0.03–0.05; at ε=0.05 a car photo is classified `receipt (0.839)` with only mild visible noise.

## Step 4: Data Poisoning

```bash
cd attacks
# 1. Create poisoned dataset (5% of training labels flipped; test set untouched)
python 02_label_flip_poisoning.py

# 2. Retrain on poisoned data (Ctrl-C after "Saved checkpoint" on macOS)
cd ../classifier
python train.py --data-dir poisoned_data --checkpoint-name receipt_cnn_poisoned.pt

# 3. Evaluate poisoned vs. clean on the SAME clean test set
python evaluate.py --model-path checkpoints/receipt_cnn_poisoned.pt --test-dir balanced_data/test --results-dir ../attacks/results/02_label_flip/poisoned
python evaluate.py --model-path checkpoints/receipt_cnn_clean.pt   --test-dir balanced_data/test --results-dir ../attacks/results/02_label_flip/clean
cd ..
```

Expected: `Labels flipped: 56 (4.85%)`; `diff -rq balanced_data/test poisoned_data/test` shows no differences. Accuracy stays near baseline, but mean confidence drops (0.856→0.786 at 5%, 0.630 at 10%) and false positives rise. For the 10% comparison used in the write-up, add `--flip-rate 0.10 --target ../classifier/poisoned_data_10`. **Accuracy alone does not reveal this attack** — see `poisoning_results_delivered.md`.

## Step 5: RAG Chatbot Setup

```bash
cd rag_chatbot
python build_index.py          # rebuilds faiss_index/ from data/policies/ (index is prebuilt)
python app.py                  # Flask server on 0.0.0.0:5001 — leave running
# in another terminal:
curl -X POST http://localhost:5001/chat -H "Content-Type: application/json" \
  -d '{"question": "What is the meal expense limit?"}'
```

Expected: `build_index.py` reports 23 chunks across 4 documents; the curl returns `"$75 per person per meal"` with `sources: expense_policy.md`.

## Step 6: Prompt Injection

```bash
cd attacks
python 03_prompt_injection.py
```

Expected: `2/5 injection attempts succeeded`. Persona attempt leaks bonus figures + strike price $47.50; forged-`Context:` attempt makes the bot assert a fake $500 meal limit; Base64 attempt is refused but `executive_bonus_structure_CONFIDENTIAL.md` still appears in `sources`. Results → `attacks/results/03_prompt_injection/`.

## Step 7: Data Exfiltration

```bash
python 04_data_exfiltration.py
cd ..
```

Expected: `6/6 queries exfiltrated confidential data`; every query retrieves `executive_bonus_structure_CONFIDENTIAL.md`; leaked values include CEO $750k–$1.2M, strike $47.50, 24-month clawback. Results → `attacks/results/04_exfiltration/`.

## Step 8: Supply Chain Analysis

Static analysis — does **not** require the chatbot or Docker build.

```bash
cd attacks
python 05_supply_chain_analysis.py
cd ..
```

Expected:
```
Total vulnerabilities: 804   HIGH: 34   MEDIUM: 160   LOW: 601
Dockerfile issues: 6
```
Only 3 HIGH CVEs are fixable (all Python). Report → `attacks/results/05_supply_chain/supply_chain_report.json`.

## Expected Results Summary

| Attack | Metric | Expected Result |
|--------|--------|----------------|
| Clean baseline | Accuracy | 0.9436 (P 0.9943 / R 0.8923 / F1 0.9405) |
| FGSM evasion | Adversarial accuracy | 0.94 → 0.30 by ε=0.05 (68% attack success); car→receipt at ε=0.05 |
| Label-flip poisoning | Accuracy / confidence | Accuracy ≈ baseline; mean confidence 0.86→0.63 and uncertain preds 60→137 at 10% |
| Prompt injection | Answer-level successes | 2/5 (plus 3/5 confidential-source retrieval leaks) |
| Data exfiltration | Confidential retrieval | 6/6 queries retrieve the CONFIDENTIAL doc; 5/6 leak figures |
| Supply chain | Vuln + Dockerfile counts | 804 vulns (34 HIGH); 6 Dockerfile issues; 3 HIGH fixable |

# Executive Risk Summary

**To:** CISO and Executive Leadership · **From:** Red Team (Jobelo Quintero) · **Date:** 2026-11-23
**Engagement:** Security assessment of the FinanceGuard AI expense platform

## Overview

We tested the three AI components of the expense platform — the receipt-scanning classifier, the employee policy chatbot, and the container they run in — using five realistic attacks. **All five succeeded.** The most serious: any employee can make the policy chatbot reveal **restricted executive compensation data** (salaries, bonuses, stock-option terms) simply by asking for it. This is a confidentiality breach that needs attention before the platform is relied upon in production. None of the testing touched production systems or real data; it ran entirely in an isolated environment.

## Risk Dashboard

| System | Risk Level | Key Finding |
|--------|-----------|-------------|
| Receipt Classifier | HIGH | Fake images can be made to pass as valid receipts (and real receipts made to fail), with tampering invisible to a human reviewer. |
| RAG Chatbot | **CRITICAL** | Confidential executive pay data is retrievable by any employee; the bot can also be tricked into stating false policy. |
| Deployment Infrastructure | HIGH | The container runs with maximum privileges, carries many known-vulnerable components, and has a live API key embedded inside it. |

## Findings Summary

### 1. Confidential Compensation Data Exposure (RAG Chatbot) — CRITICAL
**Business Impact:** Executive salaries, bonus percentages, the stock-option strike price, and clawback terms are accessible to any employee who can use the chatbot — all six of our attempts succeeded. This is an insider-threat and privacy exposure that could damage trust, invite legal and regulatory consequences, and, because it includes unannounced equity terms, carry securities-sensitivity. It requires no special skill to exploit.

### 2. Insecure Deployment Environment (Infrastructure) — HIGH
**Business Impact:** The system is packaged in a way that maximizes damage if any component is breached: it runs with full administrative rights and has a working access credential stored inside the package, so a single break-in could expose that credential and the confidential data together. Many components also have publicly known weaknesses that have not been patched.

### 3. Chatbot Manipulation (RAG Chatbot) — HIGH
**Business Impact:** The chatbot can be talked into ignoring its rules — stating incorrect policy (e.g. a fabricated expense limit) or revealing information it should withhold. If employees or any automation trust its answers, this could drive wrong financial decisions and erode confidence in the tool.

### 4. Receipt Fraud via Image Manipulation (Classifier) — HIGH
**Business Impact:** We showed that an ordinary image (a photo of a car) can be altered — with changes a reviewer would not notice — so the system accepts it as a valid receipt. The reverse also works, blocking genuine receipts. This directly undermines the control's purpose and enables expense fraud if approvals are automated.

### 5. Training-Data Tampering (Classifier Pipeline) — MEDIUM
**Business Impact:** An insider able to alter the data used to train the model can quietly degrade its reliability — making it less certain and more likely to wave through invalid receipts — without triggering the accuracy checks currently in place. The damage is gradual and hard to detect after the fact.

## Prioritized Remediation

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Remove confidential documents from the chatbot's knowledge base and add access controls so sensitive files are never retrievable by general staff. | Low | Critical |
| 2 | Rotate the exposed API key; stop packaging secrets into the container; run it without administrator rights. | Low | High |
| 3 | Patch the fixable known-vulnerable components and rebuild on a minimal, trusted base image. | Medium | High |
| 4 | Harden the chatbot against manipulation (separate user input from trusted content; add protective instructions and output checks). | Medium | High |
| 5 | Strengthen the classifier (adversarial training, image preprocessing) and lock down and verify the integrity of training data. | High | Medium |

## Conclusion

The platform is functional but not yet safe to depend on for sensitive or high-value decisions. **The single most urgent action is to stop the chatbot from exposing confidential compensation data (Priority 1) — it is a low-effort fix for a critical risk and should be done immediately.** The two next items (rotate the key and remove administrator rights) are also low-effort and close off the most damaging follow-on scenarios. We recommend completing Priorities 1–3 before any production use, with 4–5 scheduled as fast-follow hardening, and a re-test once fixes are in place.

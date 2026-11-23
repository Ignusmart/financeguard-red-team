"""
Supply Chain Vulnerability Analysis.

Parses a Trivy JSON report and analyzes a Dockerfile for security issues.
Produces a structured risk assessment of the AI system's deployment pipeline.

Usage:
    python 05_supply_chain_analysis.py
    python 05_supply_chain_analysis.py --trivy-report ../06_trivy_report.json --dockerfile ../Dockerfile
"""
import json
import argparse
import os

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "05_supply_chain")


def parse_trivy_report(path):
    """
    Parse a Trivy JSON report and extract vulnerability details.

    The Trivy JSON format has a "Results" array, where each result has:
    - "Target": what was scanned (e.g., "debian 13.4" or "Python")
    - "Type": scan type (e.g., "debian", "python-pkg")
    - "Vulnerabilities": array of vulnerability objects

    Each vulnerability has: VulnerabilityID, Severity, PkgName,
    InstalledVersion, FixedVersion, Title, Description

    Args:
        path: Path to Trivy JSON report

    Returns:
        List of vulnerability dictionaries
    """
    with open(path) as f:
        data = json.load(f)

    vulns = []

    for result in data.get("Results", []):
        for v in result.get("Vulnerabilities") or []:
            vulns.append({
                "id": v.get("VulnerabilityID", ""),
                "severity": v.get("Severity", "UNKNOWN"),
                "package": v.get("PkgName", ""),
                "installed_version": v.get("InstalledVersion", ""),
                "fixed_version": v.get("FixedVersion", ""),
                "title": v.get("Title", ""),
                "description": (v.get("Description") or "")[:200],
                "target": result.get("Target", ""),
                "target_type": result.get("Type", ""),
            })

    return vulns


def analyze_dockerfile(path):
    """
    Analyze a Dockerfile for common security issues.

    Check for:
    1. Running as root (no USER directive) — HIGH
    2. Unpinned base image (no SHA256 digest) — MEDIUM
    3. COPY . (copies entire context including secrets) — MEDIUM
    4. No HEALTHCHECK — LOW
    5. Build tools left in production image — MEDIUM
    6. Unnecessary tools (curl, git) in production — LOW

    Args:
        path: Path to Dockerfile

    Returns:
        List of issue dictionaries with: issue, severity, detail, recommendation
    """
    with open(path) as f:
        content = f.read()
    lines = content.strip().split("\n")

    issues = []

    def has_directive(name):
        return any(line.strip().upper().startswith(name) for line in lines)

    # 1. Running as root (no USER directive) — HIGH
    if not has_directive("USER"):
        issues.append({
            "issue": "Container runs as root (no USER directive)",
            "severity": "HIGH",
            "detail": (
                "Without a USER instruction the process runs as root (UID 0). "
                "Any RCE via a vulnerable dependency then has root in the "
                "container, easing breakout and lateral movement."
            ),
            "recommendation": "Add a non-root user and `USER appuser` before CMD.",
        })

    # 2. Unpinned base image (no SHA256 digest) — MEDIUM
    from_lines = [l for l in lines if l.strip().upper().startswith("FROM")]
    if from_lines and not any("@sha256:" in l for l in from_lines):
        issues.append({
            "issue": "Base image not pinned by digest",
            "severity": "MEDIUM",
            "detail": (
                f"Base image is tag-pinned only ({from_lines[0].split()[1]}). "
                "Tags are mutable, so the same build can pull different, "
                "possibly compromised, content later (supply-chain risk)."
            ),
            "recommendation": "Pin by digest, e.g. `FROM python:3.11-slim@sha256:<digest>`.",
        })

    # 3. COPY . (copies entire build context) — MEDIUM
    if any(l.strip().upper().startswith("COPY .") or
           l.strip().upper().startswith("COPY . ") for l in lines):
        issues.append({
            "issue": "COPY . copies the entire build context",
            "severity": "MEDIUM",
            "detail": (
                "`COPY . /app` bakes everything in the context into the image, "
                "including rag_chatbot/.env (the OpenAI API key), the FAISS "
                "index and .git history, unless a .dockerignore excludes them."
            ),
            "recommendation": "Add a .dockerignore (.env, .git, *.pt, faiss_index/) and copy only needed paths.",
        })

    # 4. No HEALTHCHECK — LOW
    if not has_directive("HEALTHCHECK"):
        issues.append({
            "issue": "No HEALTHCHECK instruction",
            "severity": "LOW",
            "detail": (
                "Orchestrators cannot tell a hung container from a healthy one, "
                "so a crashed or wedged service keeps receiving traffic."
            ),
            "recommendation": "Add a HEALTHCHECK hitting the app's /health endpoint.",
        })

    # 5. Build tools left in the production image — MEDIUM
    build_tools = [t for t in ("build-essential", "gcc") if t in content]
    if build_tools:
        issues.append({
            "issue": f"Build tools in final image ({', '.join(build_tools)})",
            "severity": "MEDIUM",
            "detail": (
                "Compilers in the runtime image enlarge the attack surface: an "
                "attacker who lands code can compile exploits/implants in place. "
                "They are only needed to build wheels, not at runtime."
            ),
            "recommendation": "Use a multi-stage build; install compilers only in the build stage.",
        })

    # 6. Unnecessary tools (curl, git) in production — LOW
    extra_tools = [t for t in ("curl", "git") if t in content]
    if extra_tools:
        issues.append({
            "issue": f"Network/VCS tools in final image ({', '.join(extra_tools)})",
            "severity": "LOW",
            "detail": (
                "curl/git give an attacker ready-made tools to pull payloads or "
                "exfiltrate data and move laterally after a compromise."
            ),
            "recommendation": "Remove curl/git from the runtime image, or install only in a build stage.",
        })

    return issues


def generate_report(vulns, dockerfile_issues):
    """Generate a structured supply chain risk report."""
    # TODO: Generate a report dictionary with:
    # - "summary": total vulnerabilities, severity breakdown, dockerfile issue count
    # - "high_severity_vulnerabilities": list of HIGH severity CVEs (top 15)
    # - "python_specific": vulnerabilities in Python packages
    # - "dockerfile_issues": from analyze_dockerfile()
    # - "risk_assessment": overall risk level and key concerns

    severity_counts = {}
    for v in vulns:
        sev = v.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    high_or_crit = [
        v for v in vulns if v["severity"] in ("CRITICAL", "HIGH")
    ]
    # Fixable ones first, so remediation can start where a patch exists.
    high_or_crit.sort(key=lambda v: (v["severity"] != "CRITICAL", not v["fixed_version"]))

    python_specific = [v for v in vulns if v["target_type"] == "python-pkg"]

    fixable = sum(1 for v in high_or_crit if v["fixed_version"])
    docker_high = sum(1 for i in dockerfile_issues if i["severity"] == "HIGH")

    report = {
        "summary": {
            "total_vulnerabilities": len(vulns),
            "severity_breakdown": severity_counts,
            "dockerfile_issues": len(dockerfile_issues),
        },
        "high_severity_vulnerabilities": high_or_crit[:15],
        "python_specific": python_specific,
        "dockerfile_issues": dockerfile_issues,
        "risk_assessment": {
            "overall_risk": "HIGH" if (high_or_crit or docker_high) else "MEDIUM",
            "high_and_critical_count": len(high_or_crit),
            "high_and_critical_fixable": fixable,
            "key_concerns": [
                f"{len(high_or_crit)} HIGH/CRITICAL CVEs ({fixable} with a fixed version available)",
                f"{len(python_specific)} vulnerability(ies) in Python packages (direct AI dependencies)",
                f"{docker_high} HIGH-severity Dockerfile misconfiguration(s), incl. running as root",
                "COPY . risks baking the OpenAI API key (.env) into image layers",
            ],
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Supply Chain Vulnerability Analysis")
    parser.add_argument(
        "--trivy-report",
        default=os.path.join(os.path.dirname(__file__), "..", "06_trivy_report.json"),
    )
    parser.add_argument(
        "--dockerfile",
        default=os.path.join(os.path.dirname(__file__), "..", "Dockerfile"),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(RESULTS_DIR, "supply_chain_report.json"),
    )
    args = parser.parse_args()
    if not os.path.dirname(args.output):
        args.output = os.path.join(RESULTS_DIR, args.output)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print("Parsing Trivy report...")
    vulns = parse_trivy_report(args.trivy_report)

    print("Analyzing Dockerfile...")
    dockerfile_issues = analyze_dockerfile(args.dockerfile)

    report = generate_report(vulns, dockerfile_issues)

    # Print summary
    print(f"\n{'=' * 50}")
    print("  SUPPLY CHAIN RISK ASSESSMENT")
    print(f"{'=' * 50}")
    s = report["summary"]
    print(f"\n  Total vulnerabilities: {s['total_vulnerabilities']}")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = s["severity_breakdown"].get(sev, 0)
        if count:
            print(f"    {sev}: {count}")

    print(f"\n  Dockerfile issues: {s['dockerfile_issues']}")
    print(f"{'=' * 50}")

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {args.output}")


if __name__ == "__main__":
    main()

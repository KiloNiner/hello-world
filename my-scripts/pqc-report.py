#!/usr/bin/env python3
"""
pqc-report.py — Post-Quantum Cryptography TLS Support Reporter

Tests a list of FQDNs for post-quantum cryptography (PQC) key exchange support
and writes a markdown-formatted report to the specified output file.

Usage:
    python3 pqc-report.py report.md --domains cloudflare.com google.com example.com
    python3 pqc-report.py report.md --domains-file domains.txt
    python3 pqc-report.py report.md --domains example.com --port 8443 --timeout 15
"""

import argparse
import datetime
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# PQC key exchange groups to probe, in test order.
# Each entry: (display_name, openssl_group_string, description)
# ---------------------------------------------------------------------------
PQC_GROUPS = [
    (
        "X25519Kyber768Draft00",
        "X25519Kyber768Draft00",
        "Hybrid key exchange combining X25519 (classical) with Kyber-768 (draft). "
        "Deployed by Cloudflare and supported by Chrome since 2023.",
    ),
    (
        "X25519MLKEM768",
        "X25519MLKEM768",
        "Hybrid key exchange combining X25519 with ML-KEM-768 (FIPS 203). "
        "The IETF-standardized successor to X25519Kyber768Draft00.",
    ),
    (
        "MLKEM768",
        "MLKEM768",
        "Pure ML-KEM-768 key encapsulation (FIPS 203 / NIST PQC standard). "
        "No classical component; provides PQC-only key exchange.",
    ),
    (
        "SecP256r1MLKEM768",
        "SecP256r1MLKEM768",
        "Hybrid combining NIST P-256 (classical) with ML-KEM-768. "
        "Alternative hybrid for environments that mandate P-256.",
    ),
]

STATUS_SUPPORTED = "supported"
STATUS_UNSUPPORTED = "unsupported"
STATUS_UNTESTABLE = "untestable"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"

ICONS = {
    STATUS_SUPPORTED: "✅",
    STATUS_UNSUPPORTED: "❌",
    STATUS_UNTESTABLE: "⚠️",
    STATUS_ERROR: "🔴",
    STATUS_SKIPPED: "—",
}

OVERALL_FULL_PQC = "Full PQC"
OVERALL_PARTIAL = "Partial PQC"
OVERALL_NO_PQC = "No PQC"
OVERALL_TLS13_ONLY = "TLS 1.3 Only"
OVERALL_ERROR = "Error"

OVERALL_ICONS = {
    OVERALL_FULL_PQC: "✅",
    OVERALL_PARTIAL: "⚠️",
    OVERALL_NO_PQC: "❌",
    OVERALL_TLS13_ONLY: "❌",
    OVERALL_ERROR: "🔴",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GroupTestResult:
    group_name: str
    status: str           # one of the STATUS_* constants
    negotiated_group: str = ""   # group the server actually selected
    evidence: str = ""           # relevant raw output from openssl
    notes: str = ""


@dataclass
class DomainResult:
    domain: str
    port: int
    tls13_supported: bool = False
    tls13_cipher: str = ""
    tls_error: str = ""
    group_tests: List[GroupTestResult] = field(default_factory=list)
    overall: str = OVERALL_ERROR


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pqc-report.py",
        description=(
            "Test a set of FQDNs for post-quantum cryptography (PQC) TLS support "
            "and produce a markdown report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 pqc-report.py report.md --domains cloudflare.com google.com\n"
            "  python3 pqc-report.py report.md --domains-file domains.txt --verbose\n"
            "  python3 pqc-report.py report.md --domains example.com --port 8443"
        ),
    )
    parser.add_argument("output", help="Path to write the markdown report file.")
    parser.add_argument(
        "--domains",
        metavar="DOMAIN",
        nargs="+",
        default=[],
        help="One or more FQDNs to test.",
    )
    parser.add_argument(
        "--domains-file",
        metavar="FILE",
        help="Path to a newline-separated file of FQDNs (comments starting with # are ignored).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=443,
        metavar="PORT",
        help="TLS port to connect to (default: 443).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Per-connection timeout in seconds (default: 10).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information to stderr.",
    )
    args = parser.parse_args()

    if not args.domains and not args.domains_file:
        parser.error("Provide at least one of --domains or --domains-file.")

    return args


def load_domains(args: argparse.Namespace) -> List[str]:
    """Collect, deduplicate, and return the list of FQDNs to test."""
    domains: List[str] = list(args.domains)

    if args.domains_file:
        try:
            with open(args.domains_file, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        domains.append(line)
        except OSError as exc:
            sys.exit(f"Cannot read domains file '{args.domains_file}': {exc}")

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for d in domains:
        if d.lower() not in seen:
            seen.add(d.lower())
            unique.append(d)

    if not unique:
        sys.exit("No domains found to test.")

    return unique


# ---------------------------------------------------------------------------
# TLS / OpenSSL helpers
# ---------------------------------------------------------------------------


def get_openssl_version() -> str:
    """Return the local openssl version string, or a fallback message."""
    try:
        result = subprocess.run(
            ["openssl", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or result.stderr.strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "openssl not found"


def check_tls13(domain: str, port: int, timeout: float) -> Tuple[bool, str, str]:
    """
    Attempt a TLS 1.3-only connection using Python's ssl module.

    Returns:
        (success, cipher_suite_name, error_message)
    """
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()

        with socket.create_connection((domain, port), timeout=timeout) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=domain) as tls_sock:
                cipher_info = tls_sock.cipher()
                cipher_name = cipher_info[0] if cipher_info else ""
                return True, cipher_name, ""
    except ssl.SSLError as exc:
        return False, "", f"SSL error: {exc}"
    except socket.timeout:
        return False, "", "Connection timed out"
    except socket.gaierror as exc:
        return False, "", f"DNS resolution failed: {exc}"
    except ConnectionRefusedError:
        return False, "", "Connection refused"
    except OSError as exc:
        return False, "", str(exc)


def test_pqc_group(
    domain: str, port: int, timeout: float, group_name: str
) -> GroupTestResult:
    """
    Use openssl s_client to probe whether the server supports the given PQC group.

    Strategy: offer the PQC group first in the -groups list (with X25519 as fallback)
    and inspect what the server selects via the 'Server Temp Key' line in the output.
    """
    result = GroupTestResult(group_name=group_name, status=STATUS_ERROR)

    groups_value = f"{group_name}:X25519"
    cmd = [
        "openssl", "s_client",
        "-connect", f"{domain}:{port}",
        "-tls1_3",
        "-groups", groups_value,
        "-brief",
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout + 5,
            text=True,
        )
        output = proc.stdout or ""
    except FileNotFoundError:
        result.status = STATUS_UNTESTABLE
        result.notes = "openssl not found on this system; PQC group tests cannot be run."
        return result
    except subprocess.TimeoutExpired:
        result.status = STATUS_ERROR
        result.notes = "openssl s_client timed out."
        return result
    except OSError as exc:
        result.status = STATUS_ERROR
        result.notes = f"Failed to run openssl: {exc}"
        return result

    # --- Parse output ---

    # Detect an unknown / unsupported group name in the local openssl build
    lower_output = output.lower()
    if (
        "unknown group" in lower_output
        or "invalid group" in lower_output
        or "unknown option" in lower_output
        or "bad -groups option" in lower_output
        or "ssl_conf_cmd" in lower_output
        or ("error" in lower_output and group_name.lower() in lower_output)
    ):
        result.status = STATUS_UNTESTABLE
        result.notes = (
            f"The local OpenSSL build does not recognise the group '{group_name}'. "
            "A newer OpenSSL version or an OQS-provider build is required to test this group."
        )
        # Capture the relevant error line as evidence
        for line in output.splitlines():
            if "group" in line.lower() or "option" in line.lower():
                result.evidence = line.strip()
                break
        return result

    # Look for 'Server Temp Key' to discover what was actually negotiated
    server_temp_key_line = ""
    for line in output.splitlines():
        if line.strip().lower().startswith("server temp key"):
            server_temp_key_line = line.strip()
            break

    if server_temp_key_line:
        result.evidence = server_temp_key_line
        # Check whether the PQC group name appears in the selected key line
        # (case-insensitive, without the "Draft00" suffix for looser matching)
        base_name = group_name.replace("Draft00", "").lower()
        if base_name in server_temp_key_line.lower() or group_name.lower() in server_temp_key_line.lower():
            result.status = STATUS_SUPPORTED
            result.negotiated_group = server_temp_key_line.split(":", 1)[-1].strip()
            result.notes = "Server selected the PQC group when it was offered."
        else:
            # Server replied with a different group (fell back to X25519)
            result.status = STATUS_UNSUPPORTED
            result.negotiated_group = server_temp_key_line.split(":", 1)[-1].strip()
            result.notes = (
                f"Server fell back to a non-PQC group ({result.negotiated_group}) "
                "when offered this PQC group; PQC not supported."
            )
        return result

    # No 'Server Temp Key' line — connection likely failed outright
    # Determine whether it's a cipher mismatch or a general connectivity failure
    if (
        "no shared cipher" in lower_output
        or "handshake failure" in lower_output
        or "alert handshake failure" in lower_output
        or "ssl alert number 40" in lower_output
    ):
        result.status = STATUS_UNSUPPORTED
        result.notes = "TLS handshake failed; server and client share no common cipher or group."
        # Grab the first error-looking line as evidence
        for line in output.splitlines():
            if line.strip():
                result.evidence = line.strip()
                break
        return result

    if "connect:errno" in lower_output or "connection refused" in lower_output or "timed out" in lower_output:
        result.status = STATUS_ERROR
        result.notes = "Could not establish a TCP connection to the server."
        for line in output.splitlines():
            if line.strip():
                result.evidence = line.strip()
                break
        return result

    # Catch-all: something failed but we can't classify it precisely
    result.status = STATUS_ERROR
    result.notes = "Unexpected openssl output; unable to determine PQC support status."
    result.evidence = output[:300].strip()
    return result


# ---------------------------------------------------------------------------
# Domain assessment
# ---------------------------------------------------------------------------


def compute_overall(tls13_ok: bool, group_tests: List[GroupTestResult]) -> str:
    if not tls13_ok:
        return OVERALL_ERROR

    statuses = [t.status for t in group_tests]

    if STATUS_SUPPORTED in statuses:
        return OVERALL_FULL_PQC

    if all(s == STATUS_UNTESTABLE for s in statuses):
        # We can't determine PQC support because the local tooling is insufficient
        return OVERALL_PARTIAL

    if STATUS_UNSUPPORTED in statuses and STATUS_UNTESTABLE not in statuses:
        return OVERALL_NO_PQC

    # Mix of unsupported and untestable (or errors)
    return OVERALL_PARTIAL


def assess_domain(
    domain: str, port: int, timeout: float, verbose: bool
) -> DomainResult:
    result = DomainResult(domain=domain, port=port)

    def log(msg: str) -> None:
        if verbose:
            print(f"  {msg}", file=sys.stderr)

    # Step 1: basic TLS 1.3 check
    log("Checking TLS 1.3 support...")
    tls13_ok, cipher, tls_err = check_tls13(domain, port, timeout)
    result.tls13_supported = tls13_ok
    result.tls13_cipher = cipher
    result.tls_error = tls_err

    if not tls13_ok:
        result.overall = OVERALL_ERROR
        log(f"TLS 1.3 check failed: {tls_err}")
        # Still populate group_tests as skipped so the report table is consistent
        for display_name, _, _ in PQC_GROUPS:
            result.group_tests.append(
                GroupTestResult(
                    group_name=display_name,
                    status=STATUS_SKIPPED,
                    notes="Not tested — TLS 1.3 connection failed.",
                )
            )
        return result

    log(f"TLS 1.3: OK (cipher: {cipher})")

    # Step 2: PQC group tests
    for display_name, group_str, _ in PQC_GROUPS:
        log(f"Testing PQC group: {display_name}...")
        group_result = test_pqc_group(domain, port, timeout, group_str)
        group_result.group_name = display_name  # use display name in report
        result.group_tests.append(group_result)
        log(f"  -> {group_result.status}")

    result.overall = compute_overall(tls13_ok, result.group_tests)
    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _status_cell(status: str) -> str:
    return ICONS.get(status, status)


def _overall_cell(overall: str) -> str:
    icon = OVERALL_ICONS.get(overall, "")
    return f"{icon} {overall}" if icon else overall


def generate_report(
    results: List[DomainResult],
    openssl_version: str,
    generated_at: datetime.datetime,
    args: argparse.Namespace,
) -> str:
    lines: List[str] = []

    # -----------------------------------------------------------------------
    # Header / Overview
    # -----------------------------------------------------------------------
    lines.append("# Post-Quantum Cryptography (PQC) TLS Support Report")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(
        "This report assesses TLS server support for post-quantum cryptography (PQC) "
        "key exchange algorithms. As classical asymmetric cryptography (RSA, ECDH) is "
        "threatened by future large-scale quantum computers, NIST has standardised "
        "ML-KEM (FIPS 203, formerly Kyber) as a quantum-resistant key encapsulation "
        "mechanism. Leading TLS implementations are deploying ML-KEM in *hybrid* key "
        "exchange schemes that pair it with a classical algorithm (X25519 or P-256), "
        "ensuring security against both classical and quantum adversaries during the "
        "transition period."
    )
    lines.append("")
    lines.append(
        "Each domain listed below was probed for TLS 1.3 support (a prerequisite for "
        "all PQC key exchange) and then tested for each of the PQC key exchange groups "
        "described in the **What Was Tested** section."
    )
    lines.append("")
    lines.append(f"**Generated:** {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Domains tested:** {len(results)}")
    lines.append(f"**TLS port:** {args.port}")
    lines.append(f"**Connection timeout:** {args.timeout}s")
    lines.append(f"**Test tool:** {openssl_version}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    lines.append("## Summary")
    lines.append("")

    # Build header row dynamically from PQC_GROUPS
    col_names = [g[0] for g in PQC_GROUPS]
    header = "| Domain | TLS 1.3 | " + " | ".join(col_names) + " | Overall |"
    separator = "| --- | --- | " + " | ".join(["---"] * len(col_names)) + " | --- |"
    lines.append(header)
    lines.append(separator)

    for r in results:
        tls13_cell = "✅" if r.tls13_supported else "🔴"
        group_cells = " | ".join(_status_cell(t.status) for t in r.group_tests)
        overall_cell = _overall_cell(r.overall)
        lines.append(f"| {r.domain} | {tls13_cell} | {group_cells} | {overall_cell} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # -----------------------------------------------------------------------
    # What Was Tested
    # -----------------------------------------------------------------------
    lines.append("## What Was Tested")
    lines.append("")
    lines.append(
        "The following checks were performed against each domain, in order:"
    )
    lines.append("")
    lines.append("### TLS 1.3 Support")
    lines.append("")
    lines.append(
        "A TLS 1.3-only handshake is attempted using Python's `ssl` module. "
        "TLS 1.3 is a prerequisite for all PQC key exchange groups. If this check "
        "fails, PQC group tests are skipped."
    )
    lines.append("")
    lines.append("### PQC Key Exchange Groups")
    lines.append("")
    lines.append(
        "For each PQC group below, `openssl s_client` is invoked with `-tls1_3` "
        "and `-groups <PQC_GROUP>:X25519`. The PQC group is advertised first so that "
        "a supporting server will select it. The `Server Temp Key` field in the "
        "handshake output reveals which group was actually negotiated:"
    )
    lines.append("")
    lines.append(
        "- If the PQC group name appears in `Server Temp Key`, the server **supports** it."
    )
    lines.append(
        "- If the server falls back to X25519, the server **does not support** the PQC group."
    )
    lines.append(
        "- If the local OpenSSL build does not recognise the group name, the test is "
        "marked **untestable** — this reflects a limitation of the test environment, "
        "not necessarily the server."
    )
    lines.append("")

    for display_name, group_str, description in PQC_GROUPS:
        lines.append(f"#### {display_name}")
        lines.append("")
        lines.append(f"**OpenSSL group string:** `{group_str}`")
        lines.append("")
        lines.append(description)
        lines.append("")

    lines.append("### Status Legend")
    lines.append("")
    lines.append("| Icon | Status | Meaning |")
    lines.append("| --- | --- | --- |")
    lines.append("| ✅ | Supported | Server negotiated this PQC key exchange group. |")
    lines.append("| ❌ | Unsupported | Server rejected the group or fell back to a classical group. |")
    lines.append("| ⚠️ | Untestable | Local OpenSSL does not support this group string; result is inconclusive. |")
    lines.append("| 🔴 | Error | A connection or tooling error prevented the test from completing. |")
    lines.append("| — | Skipped | Test was not run because a prerequisite check failed. |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # -----------------------------------------------------------------------
    # Detailed results per domain
    # -----------------------------------------------------------------------
    lines.append("## Detailed Results")
    lines.append("")

    for r in results:
        lines.append(f"### {r.domain}")
        lines.append("")

        # TLS connection summary
        lines.append("**TLS Connection**")
        lines.append("")
        if r.tls13_supported:
            lines.append(f"- **TLS 1.3:** ✅ Supported")
            if r.tls13_cipher:
                lines.append(f"- **Negotiated cipher suite:** `{r.tls13_cipher}`")
        else:
            lines.append(f"- **TLS 1.3:** 🔴 Failed")
            if r.tls_error:
                lines.append(f"- **Error:** {r.tls_error}")
            lines.append("")
            lines.append(
                "> PQC key exchange tests were skipped because a TLS 1.3 "
                "connection could not be established."
            )
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        lines.append("")
        lines.append("**PQC Key Exchange Tests**")
        lines.append("")

        for gt in r.group_tests:
            icon = ICONS.get(gt.status, gt.status)
            lines.append(f"#### {gt.group_name}")
            lines.append("")
            lines.append(f"- **Status:** {icon} {gt.status.capitalize()}")
            if gt.negotiated_group:
                lines.append(f"- **Negotiated group:** `{gt.negotiated_group}`")
            if gt.evidence:
                lines.append(f"- **Evidence:** `{gt.evidence}`")
            if gt.notes:
                lines.append(f"- **Notes:** {gt.notes}")
            lines.append("")

        lines.append(f"**Overall assessment:** {_overall_cell(r.overall)}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    domains = load_domains(args)

    generated_at = datetime.datetime.now(datetime.UTC)
    openssl_version = get_openssl_version()

    if args.verbose:
        print(f"OpenSSL: {openssl_version}", file=sys.stderr)
        print(f"Testing {len(domains)} domain(s) on port {args.port}...", file=sys.stderr)

    results: List[DomainResult] = []
    for domain in domains:
        if args.verbose:
            print(f"\n[{domains.index(domain) + 1}/{len(domains)}] {domain}", file=sys.stderr)
        result = assess_domain(domain, args.port, args.timeout, args.verbose)
        results.append(result)

    if args.verbose:
        print("\nGenerating report...", file=sys.stderr)

    report = generate_report(results, openssl_version, generated_at, args)

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
    except OSError as exc:
        sys.exit(f"Cannot write report to '{args.output}': {exc}")

    if args.verbose:
        print(f"Report written to: {args.output}", file=sys.stderr)
    else:
        print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()

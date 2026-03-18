#Requires -Modules ActiveDirectory
<#
.SYNOPSIS
    Enumerates Active Directory accounts and assesses their exposure to
    Microsoft's RC4 Kerberos deprecation (CVE-2026-20833 / mid-2026 enforcement).

.DESCRIPTION
    Queries user, computer, and managed service accounts in Active Directory and
    evaluates the msDS-SupportedEncryptionTypes attribute against the bitmask
    flags defined in MS-KILE. Accounts are classified by impact level and the
    results are written to a Markdown file suitable for review, remediation
    planning, or management reporting.

    Impact classification logic
    ───────────────────────────
    CRITICAL  – Only RC4 (or only DES/RC4) explicitly set; will break when
                enforcement takes effect (April / July 2026 cumulative updates).
    HIGH      – RC4 explicitly included alongside AES; account is currently
                negotiating down to RC4. Remediation strongly recommended.
                Also: DES explicitly present alongside AES, or AES-only but
                password predates AES key provisioning (pre-2009).
    HIGH      – Also: msDS-SupportedEncryptionTypes is NULL / 0, account has at
                least one SPN, AND password predates AES key provisioning
                (pre-2009). Service tickets will fail at enforcement AND the
                account likely has no AES key material at all.
    MEDIUM    – msDS-SupportedEncryptionTypes is NULL / 0 AND either:
                  (a) account has at least one SPN (service account), or
                  (b) password predates AES key provisioning (pre-2009).
                For (a): KDC defaults to RC4 for service tickets; after
                mid-2026 enforcement these accounts will fail unless AES keys
                exist. For (b): even without an SPN the account still needs a
                TGT (AS-REQ); if it has no AES keys the KDC cannot issue an
                AES-encrypted AS-REP and Kerberos logon breaks at enforcement.
    LOW       – msDS-SupportedEncryptionTypes is NULL / 0 AND no SPN AND
                password is recent (post-2008). The KDC uses the domain
                default; risk depends on domain-level settings but AES keys
                should be present.
    SAFE      – AES128 and/or AES256 explicitly set; no RC4/DES flag. No action
                required.

.PARAMETER OutputPath
    Full path for the Markdown output file.
    Defaults to .\RC4-Kerberos-Exposure-<timestamp>.md in the current directory.

.PARAMETER SearchBase
    Optional LDAP distinguished name to scope the search.
    Defaults to the domain root.

.PARAMETER IncludeSafeAccounts
    Switch. When specified, accounts with SAFE status are included in the
    output table. By default only impacted accounts are written.

.PARAMETER IncludeComputers
    Switch. When specified, computer accounts are included in the assessment.

.PARAMETER IncludeManagedServiceAccounts
    Switch. When specified, gMSA and sMSA accounts are included in the assessment.

.PARAMETER ExportCsv
    Switch. When specified, also exports the results to a CSV file alongside
    the Markdown report (same base path, .csv extension).

.PARAMETER PassThru
    Switch. When specified, the result objects are emitted to the pipeline
    after the report is written.

.EXAMPLE
    .\Get-RC4KerberosExposure.ps1

.EXAMPLE
    .\Get-RC4KerberosExposure.ps1 -OutputPath C:\Reports\RC4Audit.md `
        -IncludeSafeAccounts -IncludeComputers -IncludeManagedServiceAccounts `
        -ExportCsv -PassThru

.NOTES
    Author  : Generated for Saxo Bank / Digital Resilience & Trust
    Requires: ActiveDirectory PowerShell module (RSAT or domain-joined DC)
    CVE     : CVE-2026-20833
    Refs    : https://aka.ms/rc4kerberos
              https://learn.microsoft.com/en-us/windows-server/security/kerberos/detect-remediate-rc4-kerberos

    Version History
    ───────────────
    1.0.0   2026-03-18  Initial release. Enumerates user, computer, and managed
                        service accounts; classifies RC4/DES exposure; writes a
                        Markdown report with optional CSV export.
#>

[Diagnostics.CodeAnalysis.SuppressMessageAttribute(
    'PSAvoidUsingWriteHost', '',
    Justification = 'Intentional console feedback — this is an interactive end-user script, not a library or module.')]
[CmdletBinding()]
param(
    [string]$OutputPath = ".\RC4-Kerberos-Exposure-$(Get-Date -Format 'yyyyMMdd-HHmmss').md",
    [string]$SearchBase,
    [switch]$IncludeSafeAccounts,
    [switch]$IncludeComputers,
    [switch]$IncludeManagedServiceAccounts,
    [switch]$ExportCsv,
    [switch]$PassThru
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#──────────────────────────────────────────────────────────────────────────────
# Bitmask constants  (MS-KILE §2.2.7 / MS-ADA2 §2.324)
#──────────────────────────────────────────────────────────────────────────────
$ETYPE_DES_CBC_CRC          = 0x01   # DES-CBC-CRC
$ETYPE_DES_CBC_MD5          = 0x02   # DES-CBC-MD5
$ETYPE_RC4_HMAC             = 0x04   # RC4-HMAC-MD5  ← the problem bit
$ETYPE_AES128               = 0x08   # AES128-CTS-HMAC-SHA1-96
$ETYPE_AES256               = 0x10   # AES256-CTS-HMAC-SHA1-96
$ETYPE_AES256_SHA384        = 0x20   # AES256-CTS-HMAC-SHA384-96 (WS2025+)
$ETYPE_AES_MASK             = ($ETYPE_AES128 -bor $ETYPE_AES256 -bor $ETYPE_AES256_SHA384)
$ETYPE_DES_MASK             = ($ETYPE_DES_CBC_CRC -bor $ETYPE_DES_CBC_MD5)

#──────────────────────────────────────────────────────────────────────────────
# Helper: decode bitmask → human-readable string
#──────────────────────────────────────────────────────────────────────────────
function Get-ETypeLabel {
    param([int]$Value)
    if ($Value -eq 0) { return "Not set (NULL / 0)" }
    $parts = @()
    if ($Value -band $ETYPE_DES_CBC_CRC)   { $parts += "DES-CBC-CRC" }
    if ($Value -band $ETYPE_DES_CBC_MD5)   { $parts += "DES-CBC-MD5" }
    if ($Value -band $ETYPE_RC4_HMAC)      { $parts += "RC4-HMAC" }
    if ($Value -band $ETYPE_AES128)        { $parts += "AES128-SHA1" }
    if ($Value -band $ETYPE_AES256)        { $parts += "AES256-SHA1" }
    if ($Value -band $ETYPE_AES256_SHA384) { $parts += "AES256-SHA384" }
    # Any remaining unknown bits
    $known = $ETYPE_DES_MASK -bor $ETYPE_RC4_HMAC -bor $ETYPE_AES_MASK
    $unknown = $Value -band (-bnot $known)
    if ($unknown) { $parts += "0x$('{0:X}' -f $unknown) (unknown flags)" }
    return $parts -join ", "
}

#──────────────────────────────────────────────────────────────────────────────
# Helper: classify impact
#──────────────────────────────────────────────────────────────────────────────
function Get-ImpactLevel {
    param(
        [int]    $EType,
        [bool]   $HasSPN,
        [bool]   $IsEnabled,
        [bool]   $PasswordOld    # pwdLastSet before 2009 → may lack AES keys
    )

    if (-not $IsEnabled) { return "DISABLED" }

    if ($EType -eq 0) {
        # NULL / not set — risk is compounded when the password is old (pre-2009)
        # because the account likely has no AES keys, affecting both service-ticket
        # issuance (SPN path) and TGT/AS-REP issuance (no-SPN path).
        if ($HasSPN -and $PasswordOld) { return "HIGH"   }
        if ($HasSPN)                   { return "MEDIUM"  }
        if ($PasswordOld)              { return "MEDIUM"  }
        else                           { return "LOW"     }
    }

    $hasRC4 = [bool]($EType -band $ETYPE_RC4_HMAC)
    $hasDES = [bool]($EType -band $ETYPE_DES_MASK)
    $hasAES = [bool]($EType -band $ETYPE_AES_MASK)

    if ($hasRC4 -and -not $hasAES) {
        return "CRITICAL"
    }
    if ($hasDES -and -not $hasRC4 -and -not $hasAES) {
        return "CRITICAL"   # DES-only is even older / broken
    }
    if ($hasRC4 -and $hasAES) {
        return "HIGH"
    }
    if (-not $hasRC4 -and $hasAES) {
        # DES explicitly present alongside AES, or old password → no AES keys provisioned
        if ($hasDES -or $PasswordOld) { return "HIGH" }
        return "SAFE"
    }

    return "LOW"
}

#──────────────────────────────────────────────────────────────────────────────
# Helper: remediation advice
#──────────────────────────────────────────────────────────────────────────────
function Get-Remediation {
    param([string]$Impact, [bool]$HasSPN)
    switch ($Impact) {
        "CRITICAL"  {
            if ($HasSPN) {
                return "Set msDS-SupportedEncryptionTypes = 0x18 (AES128+AES256); reset password to provision AES keys; update dependent services."
            } else {
                return "Reset account password to generate AES keys. Verify no SPN is present or will be added."
            }
        }
        "HIGH"      {
            if ($HasSPN) {
                return "Remove RC4/DES bits from msDS-SupportedEncryptionTypes. Set to 0x18 or 0x10. Reset password to regenerate keys. Update dependent services."
            } else {
                return "Remove RC4/DES flags; set msDS-SupportedEncryptionTypes = 0x18. Reset password."
            }
        }
        "MEDIUM"    {
            return "Set msDS-SupportedEncryptionTypes = 0x18 explicitly. Reset password to provision AES keys before April 2026 enforcement."
        }
        "LOW"       {
            return "Monitor. Consider explicitly setting msDS-SupportedEncryptionTypes = 0x18 for clarity. Ensure domain DefaultDomainSupportedEncTypes is AES-only."
        }
        "SAFE"      { return "No action required." }
        "DISABLED"  { return "Account is disabled; assess before re-enabling." }
        default     { return "Review manually." }
    }
}

#──────────────────────────────────────────────────────────────────────────────
# Helper: escape pipe characters for Markdown tables
#──────────────────────────────────────────────────────────────────────────────
function ConvertTo-MdSafe {
    param([string]$s)
    return $s -replace '\|', '\|'
}

#──────────────────────────────────────────────────────────────────────────────
# Helper: consistent sort weight for impact levels
#──────────────────────────────────────────────────────────────────────────────
function Get-ImpactSortWeight {
    param([string]$Impact)
    switch ($Impact) {
        'CRITICAL' { 0 } 'HIGH' { 1 } 'MEDIUM' { 2 } 'LOW' { 3 }
        'SAFE'     { 4 } 'DISABLED' { 5 } default { 6 }
    }
}

#──────────────────────────────────────────────────────────────────────────────
# Collect domain metadata
#──────────────────────────────────────────────────────────────────────────────
Write-Host "[*] Collecting domain information..." -ForegroundColor Cyan
$domain     = Get-ADDomain
$domainFQDN = $domain.DNSRoot

# Read DefaultDomainSupportedEncTypes from a DC (best-effort)
$ddsetValue = $null
try {
    $dc = $domain.PDCEmulator
    $regVal = Invoke-Command -ComputerName $dc -ScriptBlock {
        $path = 'HKLM:\SYSTEM\CurrentControlSet\Services\Kdc'
        if (Test-Path $path) {
            (Get-ItemProperty -Path $path -ErrorAction SilentlyContinue).DefaultDomainSupportedEncTypes
        }
    } -ErrorAction SilentlyContinue
    if ($null -ne $regVal) { $ddsetValue = $regVal }
} catch {
    Write-Warning "Could not query DefaultDomainSupportedEncTypes from PDC emulator: $_"
}

#──────────────────────────────────────────────────────────────────────────────
# AD query parameters
#──────────────────────────────────────────────────────────────────────────────
$adProperties = @(
    'SamAccountName',
    'DisplayName',
    'DistinguishedName',
    'msDS-SupportedEncryptionTypes',
    'ServicePrincipalName',
    'Enabled',
    'PasswordLastSet',
    'ObjectClass',
    'Description'
)

$searchParams = @{
    Filter     = '*'
    Properties = $adProperties
}
if ($PSBoundParameters.ContainsKey('SearchBase')) { $searchParams['SearchBase'] = $SearchBase }

#──────────────────────────────────────────────────────────────────────────────
# Retrieve accounts
#──────────────────────────────────────────────────────────────────────────────
Write-Host "[*] Querying user accounts..." -ForegroundColor Cyan
$userAccounts = Get-ADUser @searchParams

$computerAccounts = @()
if ($IncludeComputers) {
    Write-Host "[*] Querying computer accounts..." -ForegroundColor Cyan
    $computerAccounts = Get-ADComputer @searchParams
}

$msaAccounts = @()
if ($IncludeManagedServiceAccounts) {
    Write-Host "[*] Querying managed service accounts (gMSA/sMSA)..." -ForegroundColor Cyan
    $msaAccounts = Get-ADServiceAccount @searchParams
}

$allAccounts = @($userAccounts) + @($computerAccounts) + @($msaAccounts)
Write-Host "[*] Total accounts retrieved: $($allAccounts.Count)" -ForegroundColor Cyan

#──────────────────────────────────────────────────────────────────────────────
# Process each account
#──────────────────────────────────────────────────────────────────────────────
$results = [System.Collections.Generic.List[PSCustomObject]]::new()
$aesKeysCutoff = [datetime]'2009-01-01'
$total = $allAccounts.Count
$i = 0

foreach ($acct in $allAccounts) {
    $i++
    Write-Progress -Activity "Assessing accounts" `
        -Status "$($acct.SamAccountName) ($i of $total)" `
        -PercentComplete (($i / $total) * 100)

    $rawEType  = $acct.'msDS-SupportedEncryptionTypes'
    $eType     = if ($null -eq $rawEType) { 0 } else { [int]$rawEType }
    $hasSPN    = ($acct.ServicePrincipalName -and $acct.ServicePrincipalName.Count -gt 0)
    $isEnabled = if ($null -ne $acct.Enabled) { [bool]$acct.Enabled } else { $false }

    # Accounts whose password was set before AES support likely lack AES keys
    $pwdOld = ($acct.PasswordLastSet -and $acct.PasswordLastSet -lt $aesKeysCutoff)

    $impact      = Get-ImpactLevel -EType $eType -HasSPN $hasSPN -IsEnabled $isEnabled -PasswordOld $pwdOld
    $eTypeLabel  = Get-ETypeLabel -Value $eType
    $remediation = Get-Remediation -Impact $impact -HasSPN $hasSPN
    $spnList     = if ($hasSPN) { ($acct.ServicePrincipalName -join "; ") } else { "" }
    $pwdStr      = if ($acct.PasswordLastSet) { $acct.PasswordLastSet.ToString("yyyy-MM-dd") } else { "Never" }

    $row = [PSCustomObject]@{
        SamAccountName    = $acct.SamAccountName
        DisplayName       = if ($acct.DisplayName) { $acct.DisplayName } else { $acct.SamAccountName }
        ObjectType        = $acct.ObjectClass
        Enabled           = $isEnabled
        ETypeRaw          = $eType
        ETypeHex          = if ($eType -eq 0) { "NULL" } else { "0x$('{0:X}' -f $eType)" }
        ETypeLabel        = $eTypeLabel
        HasSPN            = $hasSPN
        SPNs              = $spnList
        PasswordLastSet   = $pwdStr
        OldPassword       = $pwdOld
        Impact            = $impact
        Remediation       = $remediation
        DistinguishedName = $acct.DistinguishedName
    }
    $results.Add($row)
}

Write-Progress -Activity "Assessing accounts" -Completed

#──────────────────────────────────────────────────────────────────────────────
# Summary statistics
#──────────────────────────────────────────────────────────────────────────────
$stats = $results | Group-Object Impact -NoElement
$countByImpact = @{}
$stats | ForEach-Object { $countByImpact[$_.Name] = $_.Count }

$totalImpacted = [int]$countByImpact['CRITICAL'] + [int]$countByImpact['HIGH'] + [int]$countByImpact['MEDIUM']

#──────────────────────────────────────────────────────────────────────────────
# Filter and sort for output
#──────────────────────────────────────────────────────────────────────────────
$sortExpr = @{ E = { Get-ImpactSortWeight $_.Impact } }

if ($IncludeSafeAccounts) {
    $outputRows = $results | Sort-Object $sortExpr, SamAccountName
} else {
    $outputRows = $results |
        Where-Object { $_.Impact -ne 'SAFE' } |
        Sort-Object $sortExpr, SamAccountName
}

#──────────────────────────────────────────────────────────────────────────────
# Build Markdown document
#──────────────────────────────────────────────────────────────────────────────
$ddsetDisplay = if ($null -ne $ddsetValue) {
    "0x$('{0:X}' -f [int]$ddsetValue)  ($(Get-ETypeLabel -Value ([int]$ddsetValue)))"
} else {
    "Not found / not readable (assumed domain default)"
}

$scopeLine = if ($PSBoundParameters.ContainsKey('SearchBase')) { "`n**Search scope:** $SearchBase" } else { "" }

$sb = [System.Text.StringBuilder]::new()

$null = $sb.AppendLine(@"
# RC4 Kerberos Deprecation — Active Directory Exposure Report

**Domain:**       $domainFQDN
**Generated:**    $([datetime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC$scopeLine
**Total accounts assessed:** $($results.Count)
**Accounts requiring action (CRITICAL / HIGH / MEDIUM):** $totalImpacted
**DC DefaultDomainSupportedEncTypes:** $ddsetDisplay

---

## Background — Why This Matters

### The RC4 Deprecation Timeline

RC4 (Rivest Cipher 4) is a stream cipher that has been considered cryptographically
weak for over a decade. In the context of Windows Kerberos authentication, RC4-encrypted
service tickets are the primary enabler of **Kerberoasting** — an offline attack technique
where an adversary with any domain credentials can request a service ticket for an
SPN-bearing account and attempt to crack the RC4-HMAC key offline, recovering the
plaintext password without generating any further domain-controller events.

Microsoft has been progressively hardening Kerberos encryption since Windows Server 2008
introduced AES-SHA1 support, but RC4 persisted as a fallback for compatibility with
legacy systems and accounts whose passwords predated AES key provisioning.

**The enforcement timeline is as follows:**

| Phase | Cumulative Update | Behaviour |
|-------|-------------------|-----------|
| Audit (Phase 1) | January 2026 CU | DCs begin logging Events 201–209; ``DefaultDomainSupportedEncTypes`` defaults shift. RC4 still allowed. |
| Enforcement start | **April 2026 CU** | ``DefaultDomainSupportedEncTypes`` changes to ``0x18`` (AES128+AES256 only) on all accounts **without** an explicit ``msDS-SupportedEncryptionTypes`` setting. RC4 service tickets can no longer be issued by default. |
| Enforcement final | **July 2026 CU** | RC4 is completely removed from the KDC path except for accounts where ``msDS-SupportedEncryptionTypes`` explicitly includes the RC4 bit (``0x04``). Rollback registry key ``Rc4DefaultDisablementPhase`` no longer honoured. |

Reference: [Beyond RC4 for Windows authentication — Microsoft Windows Server Blog](https://www.microsoft.com/en-us/windows-server/blog/2025/12/03/beyond-rc4-for-windows-authentication/)
CVE: **CVE-2026-20833** — [KB article](https://support.microsoft.com/topic/cve-2026-20833)

---

## The ``msDS-SupportedEncryptionTypes`` Attribute

This Active Directory attribute is a **bitmask** (unsigned 32-bit integer) that tells the
KDC which Kerberos encryption types a given account supports.  When the KDC issues a
service ticket it selects the **highest** encryption type that both the requesting client
and the target account (SPN host) advertise.

### Bit Flags

| Bit | Hex value | Decimal | Algorithm | Security status |
|-----|-----------|---------|-----------|-----------------|
| 0   | ``0x01``    | 1       | DES-CBC-CRC | ❌ Broken — removed from WS2025/Win11 24H2 |
| 1   | ``0x02``    | 2       | DES-CBC-MD5 | ❌ Broken — removed from WS2025/Win11 24H2 |
| 2   | ``0x04``    | 4       | RC4-HMAC-MD5 | ⚠️ Weak — Kerberoasting target; being deprecated |
| 3   | ``0x08``    | 8       | AES128-CTS-HMAC-SHA1-96 | ✅ Acceptable |
| 4   | ``0x10``    | 16      | AES256-CTS-HMAC-SHA1-96 | ✅ Recommended |
| 5   | ``0x20``    | 32      | AES256-CTS-HMAC-SHA384-96 | ✅ Recommended (WS2025+) |

### Common Combined Values

| Hex     | Decimal | Algorithms present | Notes |
|---------|---------|--------------------|-------|
| ``NULL`` / ``0x00`` | 0 | Not set | KDC uses ``DefaultDomainSupportedEncTypes``; historically RC4. **Service accounts at risk.** |
| ``0x04``  | 4  | RC4 only | **Breaks at April 2026 enforcement** |
| ``0x07``  | 7  | DES + RC4 | **Breaks at April 2026 enforcement** |
| ``0x08``  | 8  | AES128 only | Safe, consider adding AES256 |
| ``0x10``  | 16 | AES256 only | Safe |
| ``0x18``  | 24 | AES128 + AES256 | ✅ **Recommended target** |
| ``0x1C``  | 28 | RC4 + AES128 + AES256 | RC4 included — should remove ``0x04`` bit |
| ``0x1F``  | 31 | DES + RC4 + AES128 + AES256 | Legacy default — must remediate |
| ``0x27``  | 39 | DES + RC4 + AES (session keys) | Old ``DefaultDomainSupportedEncTypes`` default |

### NULL / 0 — The Hidden Risk for Service Accounts

When ``msDS-SupportedEncryptionTypes`` is NULL or 0, the KDC falls back to
``DefaultDomainSupportedEncTypes`` (a per-DC registry key). Before the April 2026
cumulative update, this registry key defaulted to ``0x27`` (includes RC4). After the
update the default becomes ``0x18`` (AES only). Any service account (i.e., an account
with a **Service Principal Name / SPN**) that has no explicit attribute set and has
never had its password reset since before 2009 will likely **lack AES keys** and will
break at enforcement unless the password is reset first.

User accounts **without** SPNs are generally lower risk, but they are not immune.
Even without an SPN, an account must still obtain a TGT via AS-REQ. The KDC
encrypts the AS-REP with the account's own long-term key material. If that material
is RC4-only (password predates 2009), the KDC cannot issue an AES AS-REP and
Kerberos authentication will fail at enforcement regardless of whether an SPN is
present. These accounts are therefore classified MEDIUM when the password is old.

### AES Key Provisioning

AES keys are generated at password-reset time. An account whose password was last set
**before Windows Server 2008 joined the domain** (roughly pre-2009) will only have
RC4/DES keys in the ``unicodePwd`` / Kerberos key material. A password reset is sufficient
to generate AES keys — no ``msDS-SupportedEncryptionTypes`` change is needed for plain
user accounts, but it is required for SPN-bearing service accounts.

---

## Impact Classification

| Impact | Meaning | Action required before April 2026 |
|--------|---------|-----------------------------------|
| 🔴 **CRITICAL** | Account has RC4 or DES only (``0x04``, ``0x07``, or similar without AES). **Will break at enforcement.** | Immediate — reset password + set attribute |
| 🟠 **HIGH** | RC4 explicitly included alongside AES (e.g. ``0x1C``); or DES present with AES; or AES-only but password predates AES key provisioning; or NULL/0 + SPN + password pre-2009 (no AES keys, service tickets and TGT issuance both at risk). | High priority — remove RC4/DES bits, reset password |
| 🟡 **MEDIUM** | NULL/0 + has SPN (service tickets at risk after enforcement); or NULL/0 + no SPN but password pre-2009 (TGT/AS-REP issuance breaks if account has no AES keys). | Required before April 2026 enforcement |
| 🔵 **LOW** | NULL/0 + no SPN + recent password. Lower risk; depends on domain defaults but AES keys should be present. | Recommended — set explicit ``0x18`` for hygiene |
| ✅ **SAFE** | AES-only, no RC4/DES. | No action required |
| ⚫ **DISABLED** | Account is disabled. | Assess before re-enabling |

---

## Summary

"@)

# Stats table
$null = $sb.AppendLine("| Impact | Count |")
$null = $sb.AppendLine("|--------|-------|")
foreach ($s in ($stats | Sort-Object @{ E = { Get-ImpactSortWeight $_.Name } })) {
    $icon = switch ($s.Name) {
        'CRITICAL' {'🔴'} 'HIGH' {'🟠'} 'MEDIUM' {'🟡'} 'LOW' {'🔵'}
        'SAFE'     {'✅'} 'DISABLED' {'⚫'} default {''}
    }
    $null = $sb.AppendLine("| $icon **$($s.Name)** | $($s.Count) |")
}

$null = $sb.AppendLine("")
$null = $sb.AppendLine("---")
$null = $sb.AppendLine("")
$null = $sb.AppendLine("## Account Detail")
$null = $sb.AppendLine("")

if (-not $IncludeSafeAccounts) {
    $null = $sb.AppendLine("> **Note:** SAFE accounts are excluded from this table. Re-run with ``-IncludeSafeAccounts`` to include them.")
    $null = $sb.AppendLine("")
}

if ($outputRows.Count -eq 0) {
    $null = $sb.AppendLine("*No accounts match the current filter criteria.*")
} else {
    $null = $sb.AppendLine("| Impact | Type | SAMAccountName | Display Name | Enabled | Enc. Types (Hex) | Algorithms Present | Has SPN | Pwd Last Set | Recommended Action |")
    $null = $sb.AppendLine("|--------|------|----------------|--------------|---------|------------------|--------------------|---------|--------------|-------------------|")

    foreach ($r in $outputRows) {
        $impactCell = switch ($r.Impact) {
            'CRITICAL' {'🔴 CRITICAL'} 'HIGH'     {'🟠 HIGH'}     'MEDIUM'   {'🟡 MEDIUM'}
            'LOW'      {'🔵 LOW'}      'SAFE'     {'✅ SAFE'}     'DISABLED' {'⚫ DISABLED'}
            default    {$r.Impact}
        }
        $enabledStr = if ($r.Enabled) { "Yes" } else { "No" }
        $spnStr     = if ($r.HasSPN)  { "Yes" } else { "No" }
        $typeStr    = switch ($r.ObjectType) {
            'user'                               { '👤 User' }
            'computer'                           { '💻 Computer' }
            'msDS-GroupManagedServiceAccount'    { '🔑 gMSA' }
            'msDS-ManagedServiceAccount'         { '🔑 sMSA' }
            default                              { $r.ObjectType }
        }

        $null = $sb.AppendLine("| $(ConvertTo-MdSafe $impactCell) | $typeStr | ``$(ConvertTo-MdSafe $r.SamAccountName)`` | $(ConvertTo-MdSafe $r.DisplayName) | $enabledStr | ``$($r.ETypeHex)`` | $(ConvertTo-MdSafe $r.ETypeLabel) | $spnStr | $($r.PasswordLastSet) | $(ConvertTo-MdSafe $r.Remediation) |")
    }
}

$null = $sb.AppendLine("")
$null = $sb.AppendLine("---")
$null = $sb.AppendLine("")
$null = $sb.AppendLine("## Remediation Guidance")
$null = $sb.AppendLine(@"

### CRITICAL / HIGH — Accounts with explicit RC4 or DES

1. **Set AES encryption types** on the account:
   ``````powershell
   Set-ADUser -Identity <samAccountName> -KerberosEncryptionType AES128,AES256
   # Or equivalently:
   Set-ADObject -Identity <DN> -Replace @{'msDS-SupportedEncryptionTypes' = 0x18}
   ``````
2. **Reset the account password** to provision AES key material in AD:
   ``````powershell
   Set-ADAccountPassword -Identity <samAccountName> -Reset -NewPassword (Read-Host -AsSecureString)
   ``````
3. **Update dependent services** — any service, application, or script using this
   account's Kerberos ticket must be tested after the change.

### MEDIUM — NULL/0 service accounts (SPN-bearing, no explicit attribute)

1. **Set explicit AES** (do not leave as NULL if you have SPNs):
   ``````powershell
   Set-ADUser -Identity <samAccountName> -KerberosEncryptionType AES128,AES256
   ``````
2. **Reset password** if ``PasswordLastSet`` is before 2009 to ensure AES keys exist.

### Monitoring via Event Log

On Windows Server 2019+ (and 2016 with January 2025 CU) Domain Controllers:

``````powershell
# Find RC4 service ticket requests (0x17 = RC4-HMAC)
Get-WinEvent -LogName Security -FilterXPath ``
  "Event[System[EventID=4769] and Event[EventData[Data[@Name='TicketEncryptionType']='0x17']]]" |
  Select-Object TimeCreated, Message | Format-List
``````

Look for **Event IDs 201–209** (KDCSVC log) introduced with CVE-2026-20833 patching:

| Event | Phase | Meaning |
|-------|-------|---------|
| 201   | Audit  | RC4 requested; client RC4-only; no msDS-SET on service |
| 202   | Audit  | Service account lacks AES keys; no msDS-SET |
| 203   | Enforce | RC4 blocked — client RC4-only, service has no msDS-SET |
| 204   | Enforce | RC4 blocked — service account has no AES keys |
| 205   | Any    | Domain ``DefaultDomainSupportedEncTypes`` includes weak encryption |
| 208   | Enforce | RC4 blocked — AES required but client RC4-only |
| 209   | Enforce | RC4 blocked — AES required but account lacks AES keys |

### Microsoft Resources

- [Beyond RC4 for Windows Authentication (Server Blog)](https://www.microsoft.com/en-us/windows-server/blog/2025/12/03/beyond-rc4-for-windows-authentication/)
- [Detect and Remediate RC4 Usage in Kerberos (Microsoft Learn)](https://learn.microsoft.com/en-us/windows-server/security/kerberos/detect-remediate-rc4-kerberos)
- [Microsoft/Kerberos-Crypto tools on GitHub](https://github.com/microsoft/Kerberos-Crypto)
- CVE-2026-20833 KB article

---

*This report was generated automatically. Validate findings in your environment before taking remediation action.*
"@)

#──────────────────────────────────────────────────────────────────────────────
# Write output
#──────────────────────────────────────────────────────────────────────────────
$markdownContent = $sb.ToString()
$markdownContent | Out-File -FilePath $OutputPath -Encoding UTF8 -Force
Write-Host "[+] Report written to: $OutputPath" -ForegroundColor Green

if ($ExportCsv) {
    $csvPath = [System.IO.Path]::ChangeExtension($OutputPath, '.csv')
    $results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8 -Force
    Write-Host "[+] CSV exported to:   $csvPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "[+] Total accounts assessed : $($results.Count)"
Write-Host "[+] CRITICAL : $([int]$countByImpact['CRITICAL'])"
Write-Host "[+] HIGH     : $([int]$countByImpact['HIGH'])"
Write-Host "[+] MEDIUM   : $([int]$countByImpact['MEDIUM'])"
Write-Host "[+] LOW      : $([int]$countByImpact['LOW'])"
Write-Host "[+] SAFE     : $([int]$countByImpact['SAFE'])"
Write-Host "[+] DISABLED : $([int]$countByImpact['DISABLED'])"

if ($PassThru) {
    Write-Output $results
}

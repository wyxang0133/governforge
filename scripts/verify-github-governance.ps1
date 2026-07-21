param(
  [string]$Owner = "wyxang0133",
  [string]$Repository = "governforge",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

function Get-GitHubToken {
  if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
  throw "Set GITHUB_TOKEN before running this release gate (the token is never printed)."
}

$token = Get-GitHubToken
$headers = @{
  Authorization = "Bearer $token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}
$root = "https://api.github.com/repos/$Owner/$Repository"
$repo = Invoke-RestMethod -Headers $headers -Uri $root
$protection = Invoke-RestMethod -Headers $headers -Uri "$root/branches/$Branch/protection"

$required = @($protection.required_status_checks.contexts)
$expected = @("backend", "frontend", "postgres-integration", "browser-e2e", "images", "manifests")
$missing = @($expected | Where-Object { $_ -notin $required })
$checks = @(
  @{ Name = "repository is public"; Pass = ($repo.visibility -eq "public") }
  @{ Name = "branch protection enabled"; Pass = ($null -ne $protection.required_status_checks) }
  @{ Name = "one approving review required"; Pass = ($protection.required_pull_request_reviews.required_approving_review_count -ge 1) }
  @{ Name = "CODEOWNERS review required"; Pass = [bool]$protection.required_pull_request_reviews.require_code_owner_reviews }
  @{ Name = "administrator enforcement"; Pass = [bool]$protection.enforce_admins.enabled }
  @{ Name = "force push disabled"; Pass = (-not [bool]$protection.allow_force_pushes.enabled) }
  @{ Name = "branch deletion disabled"; Pass = (-not [bool]$protection.allow_deletions.enabled) }
  @{ Name = "all required CI checks configured"; Pass = ($missing.Count -eq 0) }
)

$checks | ForEach-Object {
  $mark = if ($_.Pass) { "PASS" } else { "FAIL" }
  Write-Output ("[{0}] {1}" -f $mark, $_.Name)
}
if ($missing.Count -gt 0) { Write-Output ("Missing required checks: {0}" -f ($missing -join ", ")) }
if (@($checks | Where-Object { -not $_.Pass }).Count -gt 0) { exit 1 }
Write-Output ("Governance baseline verified: {0}/{1}" -f $checks.Count, $checks.Count)

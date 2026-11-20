<#
 Runs tests/dax/test_cases.json against a PUBLISHED semantic model through the Power BI REST API (executeQueries) and writes
 tests/results/dax_results.json / .md. RLS cases use "impersonatedUserName" (needs Build permission on the dataset).
 Usage:  pwsh tests/dax/run_dax_tests.ps1 -WorkspaceId <guid> -DatasetId <guid>
 Requires: Install-Module MicrosoftPowerBIMgmt.Profile -Scope CurrentUser
#>
param(
  [Parameter(Mandatory)][string]$WorkspaceId,
  [Parameter(Mandatory)][string]$DatasetId,
  [string]$CasesPath = "$PSScriptRoot/test_cases.json",
  [string]$OutDir = "$PSScriptRoot/../results"
)
$ErrorActionPreference = 'Stop'
Connect-PowerBIServiceAccount | Out-Null
$cases = Get-Content $CasesPath -Raw | ConvertFrom-Json
$results = @()
foreach ($c in $cases) {
  $body = @{ queries = @(@{ query = $c.dax }); serializerSettings = @{ includeNulls = $true } }
  if ($c.impersonate) { $body.impersonatedUserName = $c.impersonate }
  $sw = [Diagnostics.Stopwatch]::StartNew(); $actual = $null; $err = $null
  try {
    $resp = Invoke-PowerBIRestMethod -Method Post -Url "groups/$WorkspaceId/datasets/$DatasetId/executeQueries" -Body ($body | ConvertTo-Json -Depth 8) | ConvertFrom-Json
    $row = $resp.results[0].tables[0].rows[0]
    $actual = [double]($row.PSObject.Properties | Select-Object -First 1).Value
  } catch { $err = $_.Exception.Message }
  $sw.Stop()
  $pass = ($null -ne $actual) -and ([math]::Abs($actual - [double]$c.expected) -le [double]$c.tolerance)
  $results += [pscustomobject]@{ name = $c.name; expected = $c.expected; actual = $actual; tolerance = $c.tolerance; status = $(if ($pass) { 'PASS' } else { 'FAIL' }); ms = $sw.ElapsedMilliseconds; user = $c.impersonate; error = $err }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$results | ConvertTo-Json -Depth 4 | Set-Content "$OutDir/dax_results.json"
$md = @("# DAX test results ($(Get-Date -Format s))", "", "| Test | Expected | Actual | Status | ms |", "|---|---:|---:|---|---:|")
$results | ForEach-Object { $md += "| $($_.name) | $($_.expected) | $($_.actual) | $($_.status) | $($_.ms) |" }
$avg = [math]::Round(($results | Measure-Object ms -Average).Average, 0)
$md += "", "Passed $(($results | Where-Object status -eq 'PASS').Count) / $($results.Count). Average query time: $avg ms."
$md | Set-Content "$OutDir/dax_results.md"
$results | Format-Table name, expected, actual, status, ms -AutoSize
if ($results | Where-Object status -eq 'FAIL') { Write-Error "DAX tests failed"; exit 1 }

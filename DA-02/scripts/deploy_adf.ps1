<# Deploys /adf to an existing Azure Data Factory with the Az.DataFactory module, replacing {{PLACEHOLDERS}}.
   Prereqs: Connect-AzAccount; a Key Vault holding secrets sql-source-password and sql-dw-password; a self-hosted IR (name below)
   that can reach the source SQL Server. Secrets are NEVER stored in git.
   pwsh scripts/deploy_adf.ps1 -ResourceGroup rg-bi -FactoryName adf-aw-bi -KeyVaultName kv-aw-bi -SourceServer myhost -SourceDatabase AdventureWorks2022 `
        -SourceUser etl_reader -DwServer myserver.database.windows.net -DwDatabase AW_BI -DwUser etl_loader -StartTrigger #>
param([Parameter(Mandatory)]$ResourceGroup, [Parameter(Mandatory)]$FactoryName, [Parameter(Mandatory)]$KeyVaultName,
      [Parameter(Mandatory)]$SourceServer, [string]$SourceDatabase = "AdventureWorks2022", [Parameter(Mandatory)]$SourceUser,
      [Parameter(Mandatory)]$DwServer, [string]$DwDatabase = "AW_BI", [Parameter(Mandatory)]$DwUser, [string]$SelfHostedIrName = "ir-selfhosted", [switch]$StartTrigger)
$ErrorActionPreference = 'Stop'
$map = @{ KEYVAULT_NAME = $KeyVaultName; SOURCE_SQL_SERVER = $SourceServer; SOURCE_DATABASE = $SourceDatabase; SOURCE_SQL_USER = $SourceUser
          DW_SQL_SERVER = $DwServer; DW_DATABASE = $DwDatabase; DW_SQL_USER = $DwUser; SELF_HOSTED_IR_NAME = $SelfHostedIrName }
$tmp = Join-Path ([IO.Path]::GetTempPath()) "adf_deploy"; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory $tmp | Out-Null
function Deploy([string]$folder, [scriptblock]$cmd) {
  Get-ChildItem "$PSScriptRoot\..\adf\$folder\*.json" | ForEach-Object {
    $t = Get-Content $_.FullName -Raw; $map.GetEnumerator() | ForEach-Object { $t = $t.Replace("{{$($_.Key)}}", $_.Value) }
    $f = Join-Path $tmp $_.Name; Set-Content $f $t; $name = $_.BaseName; Write-Host "deploy $folder/$name"; & $cmd $name $f } }
$rg = @{ ResourceGroupName = $ResourceGroup; DataFactoryName = $FactoryName }
Deploy "linkedService" { param($n, $f) Set-AzDataFactoryV2LinkedService @rg -Name $n -DefinitionFile $f -Force | Out-Null }
Deploy "dataset"       { param($n, $f) Set-AzDataFactoryV2Dataset @rg -Name $n -DefinitionFile $f -Force | Out-Null }
foreach ($p in "pl_extract_to_staging", "pl_transform_and_test", "pl_master_daily") { $f = Join-Path $tmp "$p.json"
  $t = Get-Content "$PSScriptRoot\..\adf\pipeline\$p.json" -Raw; Set-Content $f $t; Write-Host "deploy pipeline/$p"; Set-AzDataFactoryV2Pipeline @rg -Name $p -DefinitionFile $f -Force | Out-Null }
Deploy "trigger"       { param($n, $f) Set-AzDataFactoryV2Trigger @rg -Name $n -DefinitionFile $f -Force | Out-Null }
if ($StartTrigger) { Start-AzDataFactoryV2Trigger @rg -Name tr_daily_0200 -Force; Write-Host "trigger tr_daily_0200 started (02:00 IST)" }
Write-Host "Deployed. Next: Monitor > Pipeline runs > trigger pl_master_daily once manually (Add trigger > Trigger now)."

<# Publishes a .pbix to Power BI Service, sets the SQL parameters, a daily refresh schedule and triggers a refresh.
   (Row-level-security role MEMBERS cannot be set through the public REST API - add them in the Service: dataset > Security.)
   Save the project as .pbix first: Power BI Desktop > open powerbi/EnterpriseBI.pbip > File > Save a copy (.pbix).
   pwsh scripts/publish_powerbi.ps1 -PbixPath .\EnterpriseBI.pbix -WorkspaceName "Enterprise BI" -SqlServer myserver.database.windows.net -Database AW_BI
   Requires: Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser #>
param([Parameter(Mandatory)]$PbixPath, [Parameter(Mandatory)]$WorkspaceName, [Parameter(Mandatory)]$SqlServer, [string]$Database = "AW_BI",
      [string]$RefreshTimeIst = "03:00", [string]$NotifyEmail = "")
$ErrorActionPreference = 'Stop'
Connect-PowerBIServiceAccount | Out-Null
$ws = Get-PowerBIWorkspace -Name $WorkspaceName; if (-not $ws) { throw "Workspace '$WorkspaceName' not found (create it first, with a Pro/PPU/Fabric capacity)." }
$rep = New-PowerBIReport -Path $PbixPath -Workspace $ws -ConflictAction CreateOrOverwrite
$ds = Get-PowerBIDataset -WorkspaceId $ws.Id | Where-Object { $_.Id -eq $rep.DatasetId }
Write-Host "Published report $($rep.Id), dataset $($ds.Id)"
$base = "groups/$($ws.Id)/datasets/$($ds.Id)"
$params = @{ updateDetails = @(@{ name = "p_SqlServer"; newValue = $SqlServer }, @{ name = "p_Database"; newValue = $Database }) } | ConvertTo-Json -Depth 4
Invoke-PowerBIRestMethod -Method Post -Url "$base/Default.UpdateParameters" -Body $params | Out-Null
$sched = @{ value = @{ enabled = $true; days = @("Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"); times = @($RefreshTimeIst); localTimeZoneId = "India Standard Time"
          notifyOption = $(if ($NotifyEmail) { "MailOnFailure" } else { "NoNotification" }) } } | ConvertTo-Json -Depth 5
Invoke-PowerBIRestMethod -Method Patch -Url "$base/refreshSchedule" -Body $sched | Out-Null
Write-Host "Parameters set; daily refresh at $RefreshTimeIst IST."
Write-Host "MANUAL STEPS: (1) dataset settings > Data source credentials > sign in to the SQL source (gateway if on-prem), (2) dataset > Security: add users to 'Region Manager' / 'Global Executive', (3) refresh now."
Write-Host "Then run: pwsh tests/dax/run_dax_tests.ps1 -WorkspaceId $($ws.Id) -DatasetId $($ds.Id)"

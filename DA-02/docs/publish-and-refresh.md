# Publish to Power BI Service, set refresh, share

Needs a **Pro / Premium Per User / Fabric** licence (RLS roles can be designed free, but publishing and sharing cannot).

## 1. Publish
1. Power BI Desktop → open `powerbi/EnterpriseBI.pbip` → make sure the data refreshed → **Publish** → choose workspace *Enterprise BI* (create it first: Service → Workspaces → New workspace). Alternative: *File → Save a copy → .pbix*, then `pwsh scripts/publish_powerbi.ps1 -PbixPath … -WorkspaceName … -SqlServer … ` which also sets the parameters and the refresh schedule.
2. Keep the **workspace restricted** to the BI team (Admin/Member/Contributor see *all* rows - they bypass RLS).

## 2. Connect the Service to the data
| Where the warehouse lives | What to do |
|---|---|
| Azure SQL Database | Semantic model → *Settings → Data source credentials* → Edit → *Basic* (use the read-only `bi_reader` login) or OAuth2. No gateway needed. |
| SQL Server on your PC / VM | Install the **On-premises data gateway** (standard mode), sign in, *Manage connections* → add a SQL Server connection with the **same server and database name as the `p_SqlServer`/`p_Database` parameters**, then map it under *Settings → Gateway connection*. |
Parameters: *Settings → Parameters* (`p_SqlServer`, `p_Database`).

## 3. Scheduled refresh
*Settings → Refresh*: **On**, frequency daily, time **03:00**, time zone **(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi**, notify the owner on failure (add a distribution list). The ETL runs at **02:00**, so by 03:00 the warehouse is fresh. Pro allows 8 refreshes/day (Premium 48). Optional: let ADF trigger the refresh right after the DQ gate passes (pipeline parameters `pbiWorkspaceId`, `pbiDatasetId`) and keep the schedule as a safety net.
Verify: *Refresh history* shows *Completed* with a duration - **record it** in the test plan.

## 4. Row-level security membership
Semantic model → ⋯ → **Security** → role **Region Manager**: add the Entra security group(s) / users (UPNs must match `sec.user_territory_map.user_email`). Role **Global Executive**: add executives. Use **Test as role** to prove it ([security-rls.md](security-rls.md)). Anyone who is a workspace Member+ must *not* be relied on for RLS.

## 5. Share as an app
Workspace → **Create app** → Setup (name, description, support contact = link to the user guide) → Content (order pages) → Audience: add *Region managers* and *Executives* groups → Publish. Update the app after every report change. Region managers get *Viewer*-level access only.

## 6. Governance extras (5 minutes each)
Endorse the semantic model (*Promoted*, later *Certified*); apply a sensitivity label (HR data!); check *Lineage view*; enable *Usage metrics*; add the one-page [user guide](user-guide.md) as the app's "Help" link.

## 7. Release checklist
- [ ] Refresh succeeded twice in a row  - [ ] `run_dax_tests.ps1` passes (55/55)  - [ ] *Test as role* done for 2 regions + executive
- [ ] No workspace Member besides the BI team  - [ ] App audiences set  - [ ] Failure e-mail tested (temporarily break a credential)
- [ ] Timings recorded in the test plan  - [ ] Screen recording made ([demo-recording-script.md](demo-recording-script.md))

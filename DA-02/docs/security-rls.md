# Row-level security (RLS)

**Goal:** every region manager sees only their territories - across sales, finance, supply chain and HR - while executives see everything.

## How it works

1. `sec.user_territory_map (user_email, territory_id)` is the single place where access is administered. Multi-territory users (e.g. a Europe director = France + Germany + UK) simply have several rows. Seeded with placeholder `@contoso.com` users: **replace them with real UPNs**.
2. `rpt.vw_sec_user_territory` turns territory_id into the surrogate key and is imported as the hidden table **Region Access**.
3. Role **Region Manager** has two table filters:
   * `Territory`: keep a territory only if `Region Access` has a row for `USERPRINCIPALNAME()` with that territory key.
   * `Region Access`: keep only the signed-in user's own rows (nobody can read the map).
4. Because **every fact carries `territory_key`** and each dimension→fact relationship is single-direction, the filter on `Territory` propagates to Sales, Quota, Purchases (vendor region), Headcount and Payroll with no bi-directional relationships.
5. Role **Global Executive** has no filters.
6. **Deny by default:** a user in `Region Manager` but missing from the map sees *no* territories. The unassigned member (`territory_key = -1`) is visible only to Global Executive.

DAX (also in `powerbi/dax/rls.dax`): 
```dax
-- Territory
COUNTROWS ( FILTER ( 'Region Access', 'Region Access'[User Email] = USERPRINCIPALNAME ()
                     && 'Region Access'[Territory Key] = Territory[Territory Key] ) ) > 0
-- Region Access
'Region Access'[User Email] = USERPRINCIPALNAME ()
```

## Not region-secured (by design - documented, decide for your company)

* **Inventory** is a company-wide snapshot (AdventureWorks has no region on it). Region managers see company inventory. Hide the inventory cards for that role with a bookmark/page visibility if that is not acceptable.
* **Product, department, ship method** dimensions are not sensitive; they only ever show data of the visible territories because facts are filtered.
* AdventureWorks puts 277 of 290 employees in the **Northwest** (home addresses) and all vendors in 5 US territories - so most managers legitimately see little HR/supply-chain data. This is a property of the sample data, not a bug.

## Testing

| Where | How |
|---|---|
| Desktop | *Modeling → View as*: tick **Region Manager** + *Other user* `northwest.manager@contoso.com`. Check *Territories Visible* = 1 and Net Sales = Northwest only. Then tick *Global Executive*. |
| Service | Workspace → dataset → … → **Security** → role → ⋯ → *Test as role*. |
| Automated | `tests/dax/run_dax_tests.ps1` runs 6 RLS cases through `executeQueries` with `impersonatedUserName` (Northwest sees 1 territory & Northwest sales; Canada; Europe director sees 3 & FR+DE+UK; unmapped user sees 0). |

## Gotchas that bite in production

* **Workspace Admin/Member/Contributor bypass RLS.** Share through an **app** or give people *Viewer* only.
* Users with **Build** permission can create their own reports on the model - RLS still applies, but they can see the *measure/column names*.
* RLS role membership is assigned **in the Service** (dataset → Security) - it is not part of the PBIX and cannot be set by the public REST API. Prefer **Entra security groups** per role.
* Changing the map needs no redeploy: the next dataset refresh picks it up.
* RLS protects the model, not the SQL database: connect Power BI with the `bi_reader` login (SELECT on `rpt` only) and keep `sec`/`stg` denied.
* *Export data* / *Analyze in Excel* respect RLS; screenshots do not - classify the report accordingly (sensitivity labels).

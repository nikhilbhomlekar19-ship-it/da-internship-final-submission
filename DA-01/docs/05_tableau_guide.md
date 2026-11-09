# Tableau build guide

Goal: present the findings and the budget recommendation in Tableau.  Plan about **2 hours** for the five dashboards below.
A Tableau workbook cannot be generated outside Tableau, so this guide gives exact data sources, fields, chart specs, layouts and a numeric checklist.
The charts in `reports/figures/` show the *content* each dashboard should reach (they are Python mock-ups, not Tableau output).

## 1. Connect to the data

**Option A - BigQuery (Tableau Desktop / Cloud / Server)**
Connect -> *Google BigQuery* -> sign in -> project `YOUR_PROJECT` -> datasets `c360_marts` (and `c360_ml` for the budget plan).
Use **extracts** (Data -> Extract) - the marts are small and dashboards become instant.
For scheduled refresh on Tableau Cloud use a service account with *BigQuery Data Viewer* + *Job User*.

**Option B - CSV extracts (Tableau Public / no BigQuery licence)**
`exports/tableau/*.csv` ships with the repo (regenerate with `make export`).  Connect -> *Text file* for each CSV.
Tableau Public cannot connect to BigQuery, so this is the route for a public portfolio dashboard.

| Data source | Tables / files | Used by |
|---|---|---|
| **KPIs** | `mart_daily_kpis`, `mart_sessions_by_channel_daily` | Dashboard 1 |
| **Attribution** | `mart_attribution_by_channel`, `mart_attribution_comparison` | Dashboard 2 |
| **Campaign ROI** | `mart_campaign_roi`, `mart_channel_roi`, `mart_campaign_daily` | Dashboards 2-3 |
| **Customers** | `customer_profile` (PII-safe) | Dashboard 4 |
| **Budget** | `budget_recommendations`, `response_curves` | Dashboard 5 |
| (colours) | `channel_catalog` -> `color_hex` | all |

Keep each table as its own data source (no joins needed) - this avoids fan-out.
**Important**: `mart_campaign_roi`, `mart_channel_roi` and `mart_campaign_daily` contain one row per *model*; always apply the `Model Match` filter (below) or spend is counted 4x.

## 2. Parameters and calculated fields
Create the 3 parameters and the calculated fields from [`tableau/calculated_fields.md`](../tableau/calculated_fields.md): `Attribution Model`, `Gross Margin`, `Model Match`, `ROAS`, `Break-even ROAS`, `ROI %`, `CPA`, `CAC (new customer)`, `LTV:CAC`, `Platform over-claim`.
Set `Model Match = TRUE` as a **data source filter** on Campaign ROI.  Show the parameter control on every dashboard that uses it.

Colours: channels use the `color_hex` of `channel_catalog`; models: First touch `#1F77B4`, Last touch `#D62728`, Linear `#2CA02C`, Time decay `#FF9F1C`; actions: Scale up green, Cut red, Maintain grey, Test incrementality amber.

## 3. Dashboards

### Dashboard 1 - Executive overview  (data source: KPIs)
```
+--------------------------------------------------------------------------------+
| Net revenue | Orders | Ad spend | Blended ROAS | Blended CAC | Conversion rate   |  <- 6 KPI tiles
+--------------------------------------------------------------------------------+
| Daily net revenue (bars) + ad spend (line)          | Blended ROAS, 7-day mean  |
+--------------------------------------------------------------------------------+
| Sessions by channel (stacked area, web vs app filter) | Funnel: sessions -> cart  |
|                                                       | -> checkout -> purchase    |
+--------------------------------------------------------------------------------+
```
* KPI tiles: `SUM(net_revenue)`, `SUM(orders)`, `SUM(ad_spend)`, `SUM(net_revenue)/SUM(ad_spend)`, `SUM(ad_spend)/SUM(new_customers)`, `SUM(orders)/SUM(sessions)`.
* Daily chart: Columns `kpi_date` (continuous day), Rows `SUM(net_revenue)` as bars; dual axis `SUM(ad_spend)` as line. Annotate Black Friday week.
* ROAS trend: `SUM(net_revenue)/SUM(ad_spend)`, 7-day moving average (table calc: *Moving average, previous 6 + current*).
* Funnel: from `mart_sessions_by_channel_daily`, measures `sessions`, `add_to_cart_sessions`, `checkout_sessions`, `purchasing_sessions` (Measure Names/Values, horizontal bars, filter by `channel_group`).

### Dashboard 2 - "Same revenue, four stories"  (data source: Attribution)
```
+---------------------------------------+----------------------------------------+
| Channel revenue share by model        | Slope chart: share under First touch   |
| (grouped bars, colour = model)        | vs Last touch per channel              |
+---------------------------------------+----------------------------------------+
| Heat map: channel x model (share %)   | Table: channel, share_spread_pp,       |
|                                       | rank_swing  (sorted by spread)         |
+---------------------------------------+----------------------------------------+
```
* Grouped bars: `mart_attribution_by_channel`, Rows `channel_group` (sort by time-decay revenue), Columns `SUM(revenue_share)`, Color `Model Label`, show all 4 models (no parameter).
* Slope chart: `mart_attribution_comparison`; Measure Names = `share_first_touch`, `share_last_touch` on Columns, Detail `channel_group`, line mark; colour by `first_minus_last_share` (diverging).
* Heat map: Rows `channel_group`, Columns `Model Label`, Color `AVG(revenue_share)`, labels as %.
* **Headline to put in the title** (from `reports/findings.md`): *"Paid Search gets 28.7 % of revenue under first touch and 39.9 % under last touch"*.

### Dashboard 3 - Campaign ROI and unit economics  (data source: Campaign ROI, `Model Match` filter)
```
+------------------------------------------------------------------------------+
| Model: [ time decay v ]   Gross margin: [ 0.45 ]   Channel: [ all v ]        |
+---------------------------------------+--------------------------------------+
| ROAS by campaign (bars, sorted)       | Spend vs attributed revenue          |
| reference line = break-even ROAS      | (scatter; size = orders, colour =    |
| marker = platform-claimed ROAS        |  channel; 45-degree = ROAS 1)        |
+---------------------------------------+--------------------------------------+
| CPA / CAC / LTV:CAC table (conditional colour on LTV:CAC < 3)                |
+------------------------------------------------------------------------------+
```
* ROAS bars: Rows `campaign_key` (or `campaign_name`), Columns `ROAS`; Reference line at `Break-even ROAS`; second axis with `AVERAGE(platform_roas)` as circle marks (shows the over-claim).
* Scatter: Columns `SUM(spend)`, Rows `SUM(attributed_revenue)`, Size `SUM(attributed_orders)`, Color `channel_group`.
* Table: `SUM(spend)`, `CPA`, `CAC (new customer)`, `12-month CLV of acquired customers`, `LTV:CAC`, `Platform over-claim`.
* Switching the parameter between *First* and *Last touch* should visibly reshuffle the bar order - that is the point of the dashboard.

### Dashboard 4 - Customer 360 and segments  (data source: Customers)
```
+----------------------------+--------------------------+----------------------+
| RFM segments (treemap):    | CLV tier x lifecycle     | Acquisition channel  |
| size = customers,          | (stacked bars)           | of new customers     |
| colour = revenue           |                          | (bar)                |
+----------------------------+--------------------------+----------------------+
| Win-back list: Platinum/Gold customers At Risk or Churned (table, 25 rows)    |
| columns: person_id, rfm_segment, last_order_at, historical revenue, forecast  |
+-------------------------------------------------------------------------------+
```
* Treemap: Detail `rfm_segment`, Size `COUNTD(person_id)`, Color `SUM(historical_clv_revenue)`.
* Stacked bars: Columns `clv_tier` (order Platinum > Gold > Silver > Bronze), Rows `COUNTD(person_id)`, Color `lifecycle_stage`.
* Acquisition: filter `is_first_order`-based field `acquisition_channel`, exclude `Pre-tracking (existing customer)`.
* Win-back table: filter `Win-back priority flag = 'Win back'`, sort by `predicted_clv_12m_revenue`.
* Privacy: the extract has no names / e-mails - keep it that way; show `person_id` only.

### Dashboard 5 - Where to move budget  (data source: Budget)  <- the "so what"
```
+------------------------------------------------------------------------------+
| Headline: "Move $1.8 k (6 %) ... models disagree on 7 of 11 campaigns"       |
+--------------------------------------+---------------------------------------+
| Diverging bars: change in spend      | Table: campaign, action, confidence,  |
| (colour = action)                    | current -> recommended, median ROAS,  |
|                                      | last/first-touch ratio, note          |
+--------------------------------------+---------------------------------------+
| Response curves (line: spend vs revenue, one panel per selected campaign;    |
| point = today)                                                               |
+------------------------------------------------------------------------------+
| What we recommend: 1) scale ...  2) test ...  3) do not cut X on last-click  |
+------------------------------------------------------------------------------+
```
* Diverging bars: Rows `campaign_key`, Columns `change_pct` (or `Spend change ($)`), Color `action` (assign the four colours manually).
* Curves (optional): from `response_curves`, plot `spend_x = current_spend * (0.5..1.5)` using a small helper calc `current_revenue * (spend_x/current_spend)^beta`.
* Text box: paste the three recommendations from `reports/findings.md` (section 4) and the caveat *attribution is not incrementality*.

## 4. Interactions
* Dashboard action: clicking a channel on Dashboard 2 filters Dashboard 3 (Filter action, source = grouped bars, target = Dashboard 3).
* Highlight action on `campaign_key` between the ROAS bars and the scatter.
* Tooltips: show spend, orders, ROAS under **all four** models for every campaign mark.

## 5. Numeric validation checklist
Your tiles must match the pipeline (`reports/findings.md`, demo run):

| Tile | Expected |
|---|---|
| Net revenue (window) | $98,724 |
| Completed orders | 2,050 |
| Ad spend | $28,787 |
| Blended ROAS (MER) | 3.43x |
| New customers / blended CAC | 1,248 / $23 |
| Paid Search share (first / last / linear / time decay) | 28.7 % / 39.9 % / 33.5 % / 34.8 % |
| Time-decay ROAS, `google|cpc|generic_apparel` | see `exports/tableau/mart_campaign_roi.csv` (model = time_decay) |

If a number differs: check the `Model Match` filter (4x spend), date filters, and that you loaded the same run's extracts.

## 6. Storytelling tips
1. Lead each dashboard title with the insight, not the chart type ("Last-click gives Paid Search 11 points more credit than first-click").
2. One colour meaning per dashboard; never use the model colours for channels.
3. Show uncertainty: flag *Test incrementality* campaigns in amber; never present a budget move without its confidence.
4. Put the break-even ROAS line on every ROAS chart.
5. End on the recommendation and the experiment plan, not on the data.

## 7. Publishing
* Tableau Public: workbook with CSV extracts (no live BigQuery). Check the extracts contain no personal data (ours do not).
* Tableau Cloud / Server: BigQuery connection with a service account, extract refresh daily after the dbt run.
* Add the dbt `exposures` (`models/exposures.yml`) URLs once published so lineage shows which tables feed which dashboard.

SELECT m.date_key AS quota_month_key,
       COALESCE(dsp.salesperson_key, -1) AS salesperson_key,
       COALESCE(dt.territory_key, -1)    AS territory_key,
       CAST(q.SalesQuota / 3.0 AS DECIMAL(19,6)) AS quota_amount
FROM stg.SalesPersonQuotaHistory AS q
JOIN dw.dim_date AS m
  ON m.calendar_year = YEAR(q.QuotaDate)
 AND m.quarter_number = CASE WHEN MONTH(q.QuotaDate) <= 3 THEN 1 WHEN MONTH(q.QuotaDate) <= 6 THEN 2 WHEN MONTH(q.QuotaDate) <= 9 THEN 3 ELSE 4 END
 AND m.day_of_month = 1
LEFT JOIN stg.SalesPerson AS sp ON sp.BusinessEntityID = q.BusinessEntityID
LEFT JOIN dw.dim_salesperson AS dsp ON dsp.business_entity_id = q.BusinessEntityID
LEFT JOIN dw.dim_territory AS dt ON dt.territory_id = sp.TerritoryID

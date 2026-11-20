SELECT sp.BusinessEntityID AS business_entity_id,
       LTRIM(RTRIM(CONCAT(p.FirstName, N' ', p.LastName))) AS salesperson_name,
       COALESCE(e.JobTitle, N'Sales Representative')       AS job_title,
       COALESCE(t.Name, N'Unassigned')                     AS territory_name,
       CASE WHEN EXISTS (SELECT 1 FROM stg.SalesPersonQuotaHistory AS q WHERE q.BusinessEntityID = sp.BusinessEntityID)
            THEN N'Quota-carrying' ELSE N'No quota' END    AS quota_status
FROM stg.SalesPerson AS sp
JOIN stg.Person AS p ON p.BusinessEntityID = sp.BusinessEntityID
LEFT JOIN stg.Employee AS e ON e.BusinessEntityID = sp.BusinessEntityID
LEFT JOIN stg.SalesTerritory AS t ON t.TerritoryID = sp.TerritoryID

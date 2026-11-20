SELECT e.BusinessEntityID AS business_entity_id,
       LTRIM(RTRIM(CONCAT(p.FirstName, N' ', p.LastName))) AS employee_name,
       e.JobTitle AS job_title,
       e.HireDate AS hire_date,
       CASE WHEN e.SalariedFlag = 1 THEN N'Salaried' ELSE N'Hourly' END AS salaried_status,
       CASE WHEN e.CurrentFlag = 1 THEN N'Current' ELSE N'Former' END   AS current_status,
       COALESCE(t.territory_key, -1) AS territory_key
FROM stg.Employee AS e
JOIN stg.Person AS p ON p.BusinessEntityID = e.BusinessEntityID
LEFT JOIN (SELECT bea.BusinessEntityID AS BusinessEntityID, sp.TerritoryID AS TerritoryID,
                  ROW_NUMBER() OVER (PARTITION BY bea.BusinessEntityID ORDER BY bea.AddressTypeID, bea.AddressID) AS rn
           FROM stg.BusinessEntityAddress AS bea
           JOIN stg.Address AS a ON a.AddressID = bea.AddressID
           JOIN stg.StateProvince AS sp ON sp.StateProvinceID = a.StateProvinceID) AS addr
       ON addr.BusinessEntityID = e.BusinessEntityID AND addr.rn = 1
LEFT JOIN dw.dim_territory AS t ON t.territory_id = addr.TerritoryID

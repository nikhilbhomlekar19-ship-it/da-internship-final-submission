SELECT v.BusinessEntityID AS vendor_id,
       v.Name AS vendor_name,
       v.AccountNumber AS account_number,
       v.CreditRating AS credit_rating,
       CASE v.CreditRating WHEN 1 THEN N'Superior' WHEN 2 THEN N'Excellent' WHEN 3 THEN N'Above average' WHEN 4 THEN N'Average' WHEN 5 THEN N'Below average' ELSE N'N/A' END AS credit_rating_label,
       CASE WHEN v.PreferredVendorStatus = 1 THEN N'Preferred' ELSE N'Standard' END AS preferred_status,
       CASE WHEN v.ActiveFlag = 1 THEN N'Active' ELSE N'Inactive' END AS active_status,
       COALESCE(t.territory_key, -1) AS territory_key
FROM stg.Vendor AS v
LEFT JOIN (SELECT bea.BusinessEntityID AS BusinessEntityID, sp.TerritoryID AS TerritoryID,
                  ROW_NUMBER() OVER (PARTITION BY bea.BusinessEntityID ORDER BY bea.AddressTypeID, bea.AddressID) AS rn
           FROM stg.BusinessEntityAddress AS bea
           JOIN stg.Address AS a ON a.AddressID = bea.AddressID
           JOIN stg.StateProvince AS sp ON sp.StateProvinceID = a.StateProvinceID) AS addr
       ON addr.BusinessEntityID = v.BusinessEntityID AND addr.rn = 1
LEFT JOIN dw.dim_territory AS t ON t.territory_id = addr.TerritoryID

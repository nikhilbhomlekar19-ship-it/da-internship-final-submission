SELECT c.CustomerID AS customer_id,
       CASE WHEN c.StoreID IS NOT NULL THEN N'Store' ELSE N'Individual' END AS customer_type,
       CASE WHEN c.StoreID IS NOT NULL THEN s.Name
            WHEN p.BusinessEntityID IS NOT NULL THEN LTRIM(RTRIM(CONCAT(p.FirstName, N' ', p.LastName)))
            ELSE CONCAT(N'Customer ', c.CustomerID) END AS customer_name
FROM stg.Customer AS c
LEFT JOIN stg.Store  AS s ON s.BusinessEntityID = c.StoreID
LEFT JOIN stg.Person AS p ON p.BusinessEntityID = c.PersonID

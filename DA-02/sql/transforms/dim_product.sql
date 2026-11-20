SELECT p.ProductID                                   AS product_id,
       p.ProductNumber                               AS product_number,
       p.Name                                        AS product_name,
       COALESCE(m.Name, N'N/A')                      AS product_model,
       COALESCE(sc.Name, N'Components & materials')  AS product_subcategory,
       COALESCE(pc.Name, N'Components & materials')  AS product_category,
       COALESCE(p.Color, N'N/A')                     AS color,
       COALESCE(p.Size, N'N/A')                      AS size,
       p.Weight                                      AS weight,
       CASE RTRIM(p.ProductLine) WHEN 'R' THEN N'Road' WHEN 'M' THEN N'Mountain' WHEN 'T' THEN N'Touring' WHEN 'S' THEN N'Standard' ELSE N'N/A' END AS product_line,
       CASE RTRIM(p.Class) WHEN 'H' THEN N'High' WHEN 'M' THEN N'Medium' WHEN 'L' THEN N'Low' ELSE N'N/A' END AS product_class,
       CASE RTRIM(p.Style) WHEN 'W' THEN N'Women' WHEN 'M' THEN N'Men' WHEN 'U' THEN N'Universal' ELSE N'N/A' END AS product_style,
       CASE WHEN p.MakeFlag = 1 THEN N'Make' ELSE N'Buy' END AS make_or_buy,
       CASE WHEN p.FinishedGoodsFlag = 1 THEN N'Finished good' ELSE N'Component / material' END AS product_type,
       p.StandardCost                                AS standard_cost,
       p.ListPrice                                   AS list_price,
       p.SafetyStockLevel                            AS safety_stock_level,
       p.ReorderPoint                                AS reorder_point,
       p.DaysToManufacture                           AS days_to_manufacture,
       CAST(p.SellStartDate AS DATE)                 AS sell_start_date,
       CAST(p.SellEndDate AS DATE)                   AS sell_end_date,
       CASE WHEN p.SellEndDate IS NOT NULL OR p.DiscontinuedDate IS NOT NULL THEN N'Discontinued' ELSE N'Active' END AS lifecycle_status
FROM stg.Product AS p
LEFT JOIN stg.ProductSubcategory AS sc ON sc.ProductSubcategoryID = p.ProductSubcategoryID
LEFT JOIN stg.ProductCategory    AS pc ON pc.ProductCategoryID = sc.ProductCategoryID
LEFT JOIN stg.ProductModel       AS m  ON m.ProductModelID = p.ProductModelID

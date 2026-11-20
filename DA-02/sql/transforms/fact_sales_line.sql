SELECT d.SalesOrderID       AS sales_order_id,
       d.SalesOrderDetailID AS sales_order_detail_id,
       h.SalesOrderNumber   AS sales_order_number,
       YEAR(h.OrderDate) * 10000 + MONTH(h.OrderDate) * 100 + DAY(h.OrderDate) AS order_date_key,
       CASE WHEN h.ShipDate IS NULL THEN NULL ELSE YEAR(h.ShipDate) * 10000 + MONTH(h.ShipDate) * 100 + DAY(h.ShipDate) END AS ship_date_key,
       YEAR(h.DueDate) * 10000 + MONTH(h.DueDate) * 100 + DAY(h.DueDate) AS due_date_key,
       COALESCE(dc.customer_key, -1)      AS customer_key,
       COALESCE(dp.product_key, -1)       AS product_key,
       COALESCE(dt.territory_key, -1)     AS territory_key,
       COALESCE(dsp.salesperson_key, -1)  AS salesperson_key,
       COALESCE(dso.special_offer_key, -1) AS special_offer_key,
       COALESCE(dsm.ship_method_key, -1)  AS ship_method_key,
       CASE WHEN h.OnlineOrderFlag = 1 THEN N'Online' ELSE N'Reseller' END AS order_channel,
       CASE h.Status WHEN 1 THEN N'In process' WHEN 2 THEN N'Approved' WHEN 3 THEN N'Backordered' WHEN 4 THEN N'Rejected' WHEN 5 THEN N'Shipped' WHEN 6 THEN N'Cancelled' ELSE N'Unknown' END AS order_status,
       d.OrderQty           AS order_quantity,
       d.UnitPrice          AS unit_price,
       d.UnitPriceDiscount  AS unit_price_discount_pct,
       CAST(d.OrderQty * d.UnitPrice AS DECIMAL(19,6))                                        AS gross_sales_amount,
       CAST(d.OrderQty * d.UnitPrice - d.LineTotal AS DECIMAL(19,6))                          AS discount_amount,
       CAST(d.LineTotal AS DECIMAL(19,6))                                                     AS net_sales_amount,
       CAST(d.OrderQty * COALESCE(c.StandardCost, p.StandardCost, 0) AS DECIMAL(19,6))        AS standard_cost_amount,
       CAST(d.LineTotal - d.OrderQty * COALESCE(c.StandardCost, p.StandardCost, 0) AS DECIMAL(19,6)) AS gross_margin_amount,
       CAST(CAST(h.Freight AS DECIMAL(19,6)) * CAST(d.LineTotal AS DECIMAL(19,6)) / CAST(NULLIF(h.SubTotal, 0) AS DECIMAL(19,6)) AS DECIMAL(19,6)) AS allocated_freight_amount,
       CAST(CAST(h.TaxAmt AS DECIMAL(19,6)) * CAST(d.LineTotal AS DECIMAL(19,6)) / CAST(NULLIF(h.SubTotal, 0) AS DECIMAL(19,6)) AS DECIMAL(19,6)) AS allocated_tax_amount
FROM stg.SalesOrderDetail AS d
JOIN stg.SalesOrderHeader AS h ON h.SalesOrderID = d.SalesOrderID
LEFT JOIN stg.Product AS p ON p.ProductID = d.ProductID
LEFT JOIN stg.ProductCostHistory AS c
       ON c.ProductID = d.ProductID AND h.OrderDate >= c.StartDate AND (c.EndDate IS NULL OR h.OrderDate <= c.EndDate)
LEFT JOIN dw.dim_customer      AS dc  ON dc.customer_id = h.CustomerID
LEFT JOIN dw.dim_product       AS dp  ON dp.product_id = d.ProductID
LEFT JOIN dw.dim_territory     AS dt  ON dt.territory_id = h.TerritoryID
LEFT JOIN dw.dim_salesperson   AS dsp ON dsp.business_entity_id = h.SalesPersonID
LEFT JOIN dw.dim_special_offer AS dso ON dso.special_offer_id = d.SpecialOfferID
LEFT JOIN dw.dim_ship_method   AS dsm ON dsm.ship_method_id = h.ShipMethodID

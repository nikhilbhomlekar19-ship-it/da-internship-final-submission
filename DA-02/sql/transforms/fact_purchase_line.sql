SELECT d.PurchaseOrderID       AS purchase_order_id,
       d.PurchaseOrderDetailID AS purchase_order_detail_id,
       YEAR(h.OrderDate) * 10000 + MONTH(h.OrderDate) * 100 + DAY(h.OrderDate) AS order_date_key,
       CASE WHEN h.ShipDate IS NULL THEN NULL ELSE YEAR(h.ShipDate) * 10000 + MONTH(h.ShipDate) * 100 + DAY(h.ShipDate) END AS ship_date_key,
       YEAR(d.DueDate) * 10000 + MONTH(d.DueDate) * 100 + DAY(d.DueDate) AS due_date_key,
       COALESCE(dv.vendor_key, -1)      AS vendor_key,
       COALESCE(dp.product_key, -1)     AS product_key,
       COALESCE(dsm.ship_method_key, -1) AS ship_method_key,
       COALESCE(dv.territory_key, -1)   AS territory_key,
       CASE h.Status WHEN 1 THEN N'Pending' WHEN 2 THEN N'Approved' WHEN 3 THEN N'Rejected' WHEN 4 THEN N'Complete' ELSE N'Unknown' END AS order_status,
       d.OrderQty     AS order_quantity,
       d.ReceivedQty  AS received_quantity,
       d.RejectedQty  AS rejected_quantity,
       d.StockedQty   AS stocked_quantity,
       d.UnitPrice    AS unit_price,
       CAST(d.LineTotal AS DECIMAL(19,6)) AS line_total_amount,
       CAST(CAST(h.Freight AS DECIMAL(19,6)) * CAST(d.LineTotal AS DECIMAL(19,6)) / CAST(NULLIF(h.SubTotal, 0) AS DECIMAL(19,6)) AS DECIMAL(19,6)) AS allocated_freight_amount,
       CAST(CAST(h.TaxAmt AS DECIMAL(19,6)) * CAST(d.LineTotal AS DECIMAL(19,6)) / CAST(NULLIF(h.SubTotal, 0) AS DECIMAL(19,6)) AS DECIMAL(19,6)) AS allocated_tax_amount,
       CASE WHEN h.ShipDate IS NULL THEN 0 ELSE 1 END AS shipped_flag,
       CASE WHEN h.ShipDate IS NOT NULL AND h.ShipDate <= d.DueDate THEN 1 ELSE 0 END AS on_time_flag,
       CASE WHEN h.ShipDate IS NOT NULL AND h.ShipDate > d.DueDate THEN DATEDIFF(DAY, d.DueDate, h.ShipDate) ELSE 0 END AS days_late
FROM stg.PurchaseOrderDetail AS d
JOIN stg.PurchaseOrderHeader AS h ON h.PurchaseOrderID = d.PurchaseOrderID
LEFT JOIN dw.dim_vendor      AS dv  ON dv.vendor_id = h.VendorID
LEFT JOIN dw.dim_product     AS dp  ON dp.product_id = d.ProductID
LEFT JOIN dw.dim_ship_method AS dsm ON dsm.ship_method_id = h.ShipMethodID

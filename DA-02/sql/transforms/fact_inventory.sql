SELECT dp.product_key AS product_key, dl.location_key AS location_key,
       i.Quantity AS quantity,
       CAST(i.Quantity * dp.standard_cost AS DECIMAL(19,4)) AS inventory_value_amount
FROM stg.ProductInventory AS i
JOIN dw.dim_product  AS dp ON dp.product_id = i.ProductID
JOIN dw.dim_location AS dl ON dl.location_id = i.LocationID

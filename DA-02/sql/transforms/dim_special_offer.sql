SELECT o.SpecialOfferID AS special_offer_id, o.Description AS offer_description, o.DiscountPct AS discount_pct,
       o.Type AS offer_type, o.Category AS offer_category,
       CAST(o.StartDate AS DATE) AS start_date, CAST(o.EndDate AS DATE) AS end_date,
       o.MinQty AS min_qty, o.MaxQty AS max_qty
FROM stg.SpecialOffer AS o

SELECT t.TerritoryID                          AS territory_id,
       t.Name                                 AS territory_name,
       t.CountryRegionCode                    AS country_region_code,
       COALESCE(c.Name, t.CountryRegionCode)  AS country_region_name,
       t.TerritoryGroup                       AS territory_group
FROM stg.SalesTerritory AS t
LEFT JOIN stg.CountryRegion AS c ON c.CountryRegionCode = t.CountryRegionCode

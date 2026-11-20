-- 04_security.sql : region-access map used by Power BI row-level security + read-only reporting role
IF OBJECT_ID(N'sec.user_territory_map') IS NULL
CREATE TABLE sec.user_territory_map (
    user_email   nvarchar(256) NOT NULL,      -- must equal the user's Entra ID UPN (what USERPRINCIPALNAME() returns)
    territory_id int NOT NULL,                -- AdventureWorks SalesTerritory.TerritoryID (stable natural key)
    is_active    bit NOT NULL CONSTRAINT df_user_territory_active DEFAULT (1),
    CONSTRAINT pk_user_territory_map PRIMARY KEY (user_email, territory_id));
GO
-- Placeholder region managers. REPLACE these with real UPNs from your tenant before testing RLS in the Service.
IF NOT EXISTS (SELECT 1 FROM sec.user_territory_map)
INSERT INTO sec.user_territory_map (user_email, territory_id) VALUES
 (N'northwest.manager@contoso.com', 1), (N'northeast.manager@contoso.com', 2), (N'central.manager@contoso.com', 3),
 (N'southwest.manager@contoso.com', 4), (N'southeast.manager@contoso.com', 5), (N'canada.manager@contoso.com', 6),
 (N'france.manager@contoso.com', 7),    (N'germany.manager@contoso.com', 8),   (N'australia.manager@contoso.com', 9),
 (N'uk.manager@contoso.com', 10),
 (N'europe.director@contoso.com', 7), (N'europe.director@contoso.com', 8), (N'europe.director@contoso.com', 10);  -- multi-territory example
GO
IF DATABASE_PRINCIPAL_ID(N'bi_reader') IS NULL CREATE ROLE bi_reader;
GO
GRANT SELECT ON SCHEMA::rpt TO bi_reader;      -- Power BI connects with a login that is ONLY in this role
DENY  SELECT ON SCHEMA::sec TO bi_reader;
DENY  SELECT ON SCHEMA::stg TO bi_reader;
GO
-- Example (edit names/passwords, store the secret in Key Vault / the Power BI credential store, never in git):
-- CREATE LOGIN powerbi_svc WITH PASSWORD = '<strong password>';   -- SQL Server (master)
-- CREATE USER  powerbi_svc FOR LOGIN powerbi_svc;                  -- inside AW_BI
-- ALTER ROLE bi_reader ADD MEMBER powerbi_svc;

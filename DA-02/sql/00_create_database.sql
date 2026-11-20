-- 00_create_database.sql  (SQL Server only; on Azure SQL Database create the DB in the portal and skip this file)
-- Run:  sqlcmd -S localhost -E -i sql/00_create_database.sql
IF DB_ID(N'AW_BI') IS NULL
    CREATE DATABASE AW_BI;
GO
ALTER DATABASE AW_BI SET RECOVERY SIMPLE;   -- dev/demo setting; use FULL + log backups in production
GO

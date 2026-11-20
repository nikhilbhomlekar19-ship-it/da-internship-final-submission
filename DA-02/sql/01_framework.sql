-- 01_framework.sql : schemas + ETL control framework (run inside database AW_BI: sqlcmd -d AW_BI)
IF SCHEMA_ID(N'stg') IS NULL EXEC (N'CREATE SCHEMA stg');
IF SCHEMA_ID(N'dw')  IS NULL EXEC (N'CREATE SCHEMA dw');
IF SCHEMA_ID(N'etl') IS NULL EXEC (N'CREATE SCHEMA etl');
IF SCHEMA_ID(N'rpt') IS NULL EXEC (N'CREATE SCHEMA rpt');
IF SCHEMA_ID(N'sec') IS NULL EXEC (N'CREATE SCHEMA sec');
GO
IF OBJECT_ID(N'etl.config') IS NULL
CREATE TABLE etl.config (
    config_key   nvarchar(100) NOT NULL CONSTRAINT pk_etl_config PRIMARY KEY,
    config_value nvarchar(400) NOT NULL,
    description  nvarchar(400) NULL);
GO
IF NOT EXISTS (SELECT 1 FROM etl.config WHERE config_key = N'fiscal_year_start_month')
    INSERT INTO etl.config (config_key, config_value, description)
    VALUES (N'fiscal_year_start_month', N'7', N'Month the fiscal year starts (7 = July). FY is named by the calendar year it ends in.');
GO
IF OBJECT_ID(N'etl.run_log') IS NULL
CREATE TABLE etl.run_log (
    run_id        bigint IDENTITY(1,1) NOT NULL CONSTRAINT pk_etl_run_log PRIMARY KEY,
    pipeline_name nvarchar(100) NOT NULL,
    started_at    datetime2(0)  NOT NULL CONSTRAINT df_run_log_started DEFAULT (SYSUTCDATETIME()),
    finished_at   datetime2(0)  NULL,
    status        nvarchar(20)  NOT NULL CONSTRAINT df_run_log_status DEFAULT (N'RUNNING'),  -- RUNNING / SUCCEEDED / FAILED
    triggered_by  nvarchar(200) NULL,
    error_message nvarchar(4000) NULL);
GO
IF OBJECT_ID(N'etl.step_log') IS NULL
CREATE TABLE etl.step_log (
    step_id       bigint IDENTITY(1,1) NOT NULL CONSTRAINT pk_etl_step_log PRIMARY KEY,
    run_id        bigint NOT NULL CONSTRAINT fk_step_log_run REFERENCES etl.run_log (run_id),
    step_name     nvarchar(200) NOT NULL,
    started_at    datetime2(3)  NOT NULL,
    finished_at   datetime2(3)  NULL,
    rows_affected bigint NULL,
    status        nvarchar(20)  NOT NULL,
    error_message nvarchar(4000) NULL);
GO
IF OBJECT_ID(N'etl.source_table_config') IS NULL
CREATE TABLE etl.source_table_config (       -- drives the metadata-driven ADF extract pipeline
    config_id        int IDENTITY(1,1) NOT NULL CONSTRAINT pk_source_table_config PRIMARY KEY,
    source_schema    nvarchar(128) NOT NULL,
    source_table     nvarchar(128) NOT NULL,
    target_schema    nvarchar(128) NOT NULL CONSTRAINT df_stc_target_schema DEFAULT (N'stg'),
    target_table     nvarchar(128) NOT NULL,
    load_type        nvarchar(12)  NOT NULL,   -- FULL | INCREMENTAL
    watermark_column nvarchar(128) NULL,
    key_columns      nvarchar(400) NULL,       -- comma separated, used as upsert keys for INCREMENTAL
    select_list      nvarchar(max) NOT NULL,   -- bracket-quoted column list, rename aliases included
    load_order       int NOT NULL,
    is_active        bit NOT NULL CONSTRAINT df_stc_active DEFAULT (1));
GO
IF OBJECT_ID(N'etl.watermark') IS NULL
CREATE TABLE etl.watermark (
    table_name     nvarchar(128) NOT NULL CONSTRAINT pk_etl_watermark PRIMARY KEY,
    last_watermark datetime2(3)  NOT NULL,
    updated_at     datetime2(0)  NOT NULL CONSTRAINT df_watermark_updated DEFAULT (SYSUTCDATETIME()));
GO
IF OBJECT_ID(N'etl.dq_check') IS NULL
CREATE TABLE etl.dq_check (
    check_id   int IDENTITY(1,1) NOT NULL CONSTRAINT pk_dq_check PRIMARY KEY,
    check_name nvarchar(200) NOT NULL,
    layer      nvarchar(20)  NOT NULL,         -- staging | dw
    severity   nvarchar(10)  NOT NULL,         -- ERROR (fails the run) | WARN
    check_sql  nvarchar(max) NOT NULL,         -- must return ONE row / ONE bigint = number of violations
    is_active  bit NOT NULL CONSTRAINT df_dq_check_active DEFAULT (1));
GO
IF OBJECT_ID(N'etl.dq_result') IS NULL
CREATE TABLE etl.dq_result (
    result_id  bigint IDENTITY(1,1) NOT NULL CONSTRAINT pk_dq_result PRIMARY KEY,
    batch_id   uniqueidentifier NOT NULL,
    run_id     bigint NULL,
    check_id   int NOT NULL,
    check_name nvarchar(200) NOT NULL,
    severity   nvarchar(10) NOT NULL,
    violations bigint NOT NULL,                -- -1 = the check itself failed to execute
    status     nvarchar(10) NOT NULL,          -- PASS | FAIL
    checked_at datetime2(0) NOT NULL CONSTRAINT df_dq_result_at DEFAULT (SYSUTCDATETIME()));
GO
CREATE OR ALTER PROCEDURE etl.usp_log_step
    @run_id bigint, @step_name nvarchar(200), @started_at datetime2(3),
    @rows_affected bigint = NULL, @status nvarchar(20) = N'SUCCEEDED', @error_message nvarchar(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @run_id IS NULL RETURN;
    INSERT INTO etl.step_log (run_id, step_name, started_at, finished_at, rows_affected, status, error_message)
    VALUES (@run_id, @step_name, @started_at, SYSUTCDATETIME(), @rows_affected, @status, @error_message);
END;
GO
CREATE OR ALTER PROCEDURE etl.usp_update_watermark @table_name nvarchar(128), @new_watermark datetime2(3)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE etl.watermark SET last_watermark = @new_watermark, updated_at = SYSUTCDATETIME() WHERE table_name = @table_name;
    IF @@ROWCOUNT = 0
        INSERT INTO etl.watermark (table_name, last_watermark) VALUES (@table_name, @new_watermark);
END;
GO

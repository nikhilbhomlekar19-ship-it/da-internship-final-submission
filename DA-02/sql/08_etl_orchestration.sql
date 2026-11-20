-- 08_etl_orchestration.sql : dependency-ordered loaders + the single entry point used by SQL Agent and ADF
CREATE OR ALTER PROCEDURE etl.usp_load_dimensions @run_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;
    EXEC etl.usp_load_dim_date        @run_id;
    EXEC etl.usp_load_dim_territory   @run_id;      -- before employee / vendor (they look up territory_key)
    EXEC etl.usp_load_dim_product     @run_id;
    EXEC etl.usp_load_dim_customer    @run_id;
    EXEC etl.usp_load_dim_salesperson @run_id;
    EXEC etl.usp_load_dim_employee    @run_id;
    EXEC etl.usp_load_dim_department  @run_id;
    EXEC etl.usp_load_dim_vendor      @run_id;
    EXEC etl.usp_load_dim_special_offer @run_id;
    EXEC etl.usp_load_dim_ship_method @run_id;
    EXEC etl.usp_load_dim_location    @run_id;
END;
GO
CREATE OR ALTER PROCEDURE etl.usp_load_facts @run_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;
    EXEC etl.usp_load_fact_sales_line        @run_id;
    EXEC etl.usp_load_fact_sales_quota       @run_id;
    EXEC etl.usp_load_fact_purchase_line     @run_id;
    EXEC etl.usp_load_fact_inventory         @run_id;
    EXEC etl.usp_load_fact_headcount_monthly @run_id;
    EXEC etl.usp_load_fact_payroll_monthly   @run_id;   -- after headcount (aggregates it)
END;
GO
-- @extract_mode: 'LOCAL' = copy source->staging with cross-database synonyms (SQL Agent / no Azure)
--                'ADF'   = staging was already loaded by Azure Data Factory; only transform + test
CREATE OR ALTER PROCEDURE etl.usp_run_all @extract_mode varchar(10) = 'LOCAL', @triggered_by nvarchar(200) = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @run_id bigint;
    INSERT INTO etl.run_log (pipeline_name, triggered_by)
    VALUES (N'etl.usp_run_all (' + @extract_mode + N')', COALESCE(@triggered_by, SUSER_SNAME()));
    SET @run_id = SCOPE_IDENTITY();
    BEGIN TRY
        IF @extract_mode = 'LOCAL' EXEC etl.usp_extract_local @run_id;
        EXEC etl.usp_load_dimensions @run_id;
        EXEC etl.usp_load_facts      @run_id;
        EXEC etl.usp_run_dq_checks   @run_id = @run_id, @fail_on_error = 1;
        UPDATE etl.run_log SET status = N'SUCCEEDED', finished_at = SYSUTCDATETIME() WHERE run_id = @run_id;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        UPDATE etl.run_log SET status = N'FAILED', finished_at = SYSUTCDATETIME(), error_message = LEFT(ERROR_MESSAGE(), 4000) WHERE run_id = @run_id;
        THROW;
    END CATCH
END;
GO

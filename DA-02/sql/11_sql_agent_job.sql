-- 11_sql_agent_job.sql : "no Azure" scheduling. SQL Server Agent job that runs the full ETL nightly at 02:00.
-- Not available on Azure SQL Database (use the ADF trigger in /adf instead). Run on the SQL Server instance (msdb).
USE msdb;
GO
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'AW_BI - nightly ETL')
    EXEC msdb.dbo.sp_delete_job @job_name = N'AW_BI - nightly ETL';
GO
EXEC msdb.dbo.sp_add_job @job_name = N'AW_BI - nightly ETL', @enabled = 1,
     @description = N'Extract AdventureWorks -> stg, load dw star schema, run data-quality gate.';
EXEC msdb.dbo.sp_add_jobstep @job_name = N'AW_BI - nightly ETL', @step_name = N'Run etl.usp_run_all',
     @subsystem = N'TSQL', @database_name = N'AW_BI', @retry_attempts = 1, @retry_interval = 5,
     @command = N'EXEC etl.usp_run_all @extract_mode = ''LOCAL'', @triggered_by = N''SQL Agent'';';
EXEC msdb.dbo.sp_add_jobschedule @job_name = N'AW_BI - nightly ETL', @name = N'Nightly 02:00',
     @freq_type = 4, @freq_interval = 1, @active_start_time = 020000;     -- daily at 02:00 server time
EXEC msdb.dbo.sp_add_jobserver @job_name = N'AW_BI - nightly ETL';
GO
-- Optional failure e-mail (needs Database Mail + an operator):
-- EXEC msdb.dbo.sp_update_job @job_name = N'AW_BI - nightly ETL', @notify_level_email = 2, @notify_email_operator_name = N'BI Team';

-- 01_integrity.sql : runs the data-quality gate (grain, orphan keys, reconciliations to staging) and prints every check.
-- Fails (THROW 51000) if any ERROR-severity check fails.   sqlcmd -S <server> -d AW_BI -b -i tests/sql/01_integrity.sql
SET NOCOUNT ON;
EXEC etl.usp_run_dq_checks @run_id = NULL, @fail_on_error = 1;
PRINT 'Data-quality gate passed';

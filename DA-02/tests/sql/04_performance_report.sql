-- 04_performance_report.sql : timings of the last SUCCEEDED ETL run (paste these numbers into docs/test-plan-and-results.md).
SET NOCOUNT ON;
DECLARE @run bigint = (SELECT MAX(run_id) FROM etl.run_log WHERE status = N'SUCCEEDED');
SELECT run_id, pipeline_name, status, started_at, finished_at, DATEDIFF(SECOND, started_at, finished_at) AS total_seconds, triggered_by
FROM etl.run_log WHERE run_id = @run;
SELECT step_name, rows_affected, DATEDIFF(MILLISECOND, started_at, finished_at) AS duration_ms
FROM etl.step_log WHERE run_id = @run ORDER BY step_id;
SELECT N'TOTAL rows loaded into dw.*' AS metric, SUM(rows_affected) AS value FROM etl.step_log WHERE run_id = @run AND step_name LIKE N'load %';
SELECT t.name AS table_name, SUM(p.rows) AS row_count
FROM sys.tables AS t JOIN sys.schemas AS s ON s.schema_id = t.schema_id JOIN sys.partitions AS p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE s.name = N'dw' GROUP BY t.name ORDER BY t.name;

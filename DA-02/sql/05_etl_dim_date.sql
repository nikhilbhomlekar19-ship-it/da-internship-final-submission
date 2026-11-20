-- 05_etl_dim_date.sql : generates/extends the calendar between the earliest and latest date found in staging.
CREATE OR ALTER PROCEDURE etl.usp_load_dim_date @run_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @t0 datetime2(3) = SYSUTCDATETIME(), @rows int = 0;
    DECLARE @fsm int = COALESCE(TRY_CAST((SELECT config_value FROM etl.config WHERE config_key = N'fiscal_year_start_month') AS int), 7);
    DECLARE @lo date, @hi date;

    SELECT @lo = MIN(x.d), @hi = MAX(x.d)
    FROM (            SELECT CAST(OrderDate AS date) AS d FROM stg.SalesOrderHeader
          UNION ALL   SELECT CAST(DueDate AS date)   FROM stg.SalesOrderHeader
          UNION ALL   SELECT CAST(ShipDate AS date)  FROM stg.SalesOrderHeader
          UNION ALL   SELECT CAST(OrderDate AS date) FROM stg.PurchaseOrderHeader
          UNION ALL   SELECT CAST(ShipDate AS date)  FROM stg.PurchaseOrderHeader
          UNION ALL   SELECT CAST(DueDate AS date)   FROM stg.PurchaseOrderDetail
          UNION ALL   SELECT CAST(QuotaDate AS date) FROM stg.SalesPersonQuotaHistory
          UNION ALL   SELECT HireDate                FROM stg.Employee) AS x;

    IF @lo IS NULL THROW 51001, N'dim_date: staging is empty - run the extract first.', 1;
    SET @lo = DATEFROMPARTS(YEAR(@lo), 1, 1);   -- whole years at the start ...
    SET @hi = EOMONTH(@hi);                     -- ... whole months at the end (time-intelligence stays correct)

    ;WITH n AS (SELECT 0 AS i UNION ALL SELECT i + 1 FROM n WHERE i < DATEDIFF(DAY, @lo, @hi)),
    dts AS (SELECT DATEADD(DAY, i, @lo) AS d FROM n),
    x AS (SELECT d,
                 (DATEDIFF(DAY, '19000101', d) % 7) + 1 AS dow,           -- 1900-01-01 was a Monday -> Monday = 1, language independent
                 YEAR(d) AS y, MONTH(d) AS m,
                 ((MONTH(d) - @fsm + 12) % 12) + 1 AS fm
          FROM dts)
    INSERT INTO dw.dim_date (date_key, full_date, day_of_month, day_name, day_of_week, week_of_year, month_number, month_name, month_short,
        year_month_label, year_month_number, month_index, quarter_number, quarter_name, year_quarter_label, year_quarter_number,
        calendar_year, fiscal_year, fiscal_year_label, fiscal_quarter_number, fiscal_quarter_label, fiscal_quarter_sort, fiscal_month_number,
        day_type, is_month_end, month_start_date, month_end_date)
    SELECT y * 10000 + m * 100 + DAY(d), d, DAY(d),
           CHOOSE(dow, N'Monday', N'Tuesday', N'Wednesday', N'Thursday', N'Friday', N'Saturday', N'Sunday'), dow, DATEPART(ISO_WEEK, d), m,
           CHOOSE(m, N'January', N'February', N'March', N'April', N'May', N'June', N'July', N'August', N'September', N'October', N'November', N'December'),
           CHOOSE(m, N'Jan', N'Feb', N'Mar', N'Apr', N'May', N'Jun', N'Jul', N'Aug', N'Sep', N'Oct', N'Nov', N'Dec'),
           CHOOSE(m, N'Jan', N'Feb', N'Mar', N'Apr', N'May', N'Jun', N'Jul', N'Aug', N'Sep', N'Oct', N'Nov', N'Dec') + N' ' + CAST(y AS nvarchar(4)),
           y * 100 + m, y * 12 + m - 1, (m - 1) / 3 + 1, N'Q' + CAST((m - 1) / 3 + 1 AS nvarchar(1)),
           CAST(y AS nvarchar(4)) + N' Q' + CAST((m - 1) / 3 + 1 AS nvarchar(1)), y * 10 + (m - 1) / 3 + 1,
           y, 0, N'', 0, N'', 0, fm,                                    -- fiscal columns are (re)computed by the UPDATE below
           CASE WHEN dow >= 6 THEN N'Weekend' ELSE N'Weekday' END, CASE WHEN d = EOMONTH(d) THEN 1 ELSE 0 END,
           DATEFROMPARTS(y, m, 1), EOMONTH(d)
    FROM x
    WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date AS e WHERE e.date_key = x.y * 10000 + x.m * 100 + DAY(x.d))
    OPTION (MAXRECURSION 0);
    SET @rows = @@ROWCOUNT;

    -- (re)apply the fiscal calendar so a changed fiscal_year_start_month takes effect on existing rows too
    UPDATE d SET
        fiscal_year           = d.calendar_year + CASE WHEN d.month_number >= @fsm AND @fsm > 1 THEN 1 ELSE 0 END,
        fiscal_month_number   = ((d.month_number - @fsm + 12) % 12) + 1
    FROM dw.dim_date AS d;
    UPDATE d SET
        fiscal_year_label     = N'FY' + CAST(d.fiscal_year AS nvarchar(4)),
        fiscal_quarter_number = (d.fiscal_month_number - 1) / 3 + 1
    FROM dw.dim_date AS d;
    UPDATE d SET
        fiscal_quarter_label  = d.fiscal_year_label + N' Q' + CAST(d.fiscal_quarter_number AS nvarchar(1)),
        fiscal_quarter_sort   = d.fiscal_year * 10 + d.fiscal_quarter_number
    FROM dw.dim_date AS d;

    EXEC etl.usp_log_step @run_id, N'load dim_date', @t0, @rows;
END;
GO

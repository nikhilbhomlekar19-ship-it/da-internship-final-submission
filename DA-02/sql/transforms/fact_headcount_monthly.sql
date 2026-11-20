SELECT m.date_key AS month_end_date_key,
       e.employee_key AS employee_key,
       COALESCE(dd.department_key, -1) AS department_key,
       e.territory_key AS territory_key,
       1 AS headcount_flag,
       CASE WHEN e.hire_date >= m.month_start_date THEN 1 ELSE 0 END AS new_hire_flag,
       DATEDIFF(MONTH, e.hire_date, m.full_date) AS tenure_months
FROM dw.dim_date AS m
JOIN dw.dim_employee AS e ON e.hire_date <= m.full_date AND e.current_status = N'Current' AND e.employee_key <> -1
LEFT JOIN stg.EmployeeDepartmentHistory AS h
       ON h.BusinessEntityID = e.business_entity_id AND h.StartDate <= m.full_date AND (h.EndDate IS NULL OR h.EndDate >= m.full_date)
LEFT JOIN dw.dim_department AS dd ON dd.department_id = h.DepartmentID
WHERE m.is_month_end = 1

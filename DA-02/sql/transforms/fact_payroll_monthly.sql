SELECT hc.month_end_date_key AS month_end_date_key,
       hc.department_key AS department_key,
       hc.territory_key AS territory_key,
       COUNT(*) AS employee_count,
       CAST(SUM(COALESCE(r.Rate, 0) * 173.3333) AS DECIMAL(19,4)) AS estimated_payroll_cost
FROM dw.fact_headcount_monthly AS hc
JOIN dw.dim_date AS m ON m.date_key = hc.month_end_date_key
JOIN dw.dim_employee AS e ON e.employee_key = hc.employee_key
LEFT JOIN stg.EmployeePayHistory AS r
       ON r.BusinessEntityID = e.business_entity_id
      AND r.RateChangeDate = (SELECT MAX(r2.RateChangeDate) FROM stg.EmployeePayHistory AS r2
                              WHERE r2.BusinessEntityID = e.business_entity_id AND r2.RateChangeDate <= m.full_date)
GROUP BY hc.month_end_date_key, hc.department_key, hc.territory_key

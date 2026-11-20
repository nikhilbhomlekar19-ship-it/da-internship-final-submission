"""Reference implementation of dw.dim_date (mirrors etl.usp_load_dim_date in T-SQL).
Fiscal year starts in month FSM (default 7 = July) and is named by the calendar year it ends in."""
import datetime as dt

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def date_rows(start, end, fsm=7):
    d, rows = start, []
    while d <= end:
        m, y = d.month, d.year
        fy = y + (1 if (m >= fsm and fsm > 1) else 0)
        fm = ((m - fsm + 12) % 12) + 1
        fq = (fm - 1) // 3 + 1
        q = (m - 1) // 3 + 1
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        mend = nxt - dt.timedelta(days=1)
        rows.append(dict(
            date_key=y * 10000 + m * 100 + d.day, full_date=d, day_of_month=d.day, day_name=DAYS[d.weekday()],
            day_of_week=d.weekday() + 1, week_of_year=d.isocalendar()[1], month_number=m, month_name=MONTHS[m - 1],
            month_short=MONTHS[m - 1][:3], year_month_label=f"{MONTHS[m-1][:3]} {y}", year_month_number=y * 100 + m,
            month_index=y * 12 + m - 1, quarter_number=q, quarter_name=f"Q{q}", year_quarter_label=f"{y} Q{q}",
            year_quarter_number=y * 10 + q, calendar_year=y, fiscal_year=fy, fiscal_year_label=f"FY{fy}",
            fiscal_quarter_number=fq, fiscal_quarter_label=f"FY{fy} Q{fq}", fiscal_quarter_sort=fy * 10 + fq,
            fiscal_month_number=fm, day_type="Weekend" if d.weekday() >= 5 else "Weekday",
            is_month_end=1 if d == mend else 0, month_start_date=d.replace(day=1), month_end_date=mend))
        d += dt.timedelta(days=1)
    return rows

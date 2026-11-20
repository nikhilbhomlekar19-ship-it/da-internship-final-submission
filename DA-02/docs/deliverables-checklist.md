# Deliverables checklist (from the brief) - status and where to find it

| Deliverable | Status | Where / what you still do |
|---|---|---|
| Working demo (deployed or screen-recorded) | **You must do** | Publish ([publish-and-refresh.md](publish-and-refresh.md)), record with [demo-recording-script.md](demo-recording-script.md) |
| GitHub repo, clean commits, README, setup instructions | Ready | `README.md`, `docs/implementation-guide.md`; public GitHub repository, projects in `DA-01/` and `DA-02/`; CI in `.github/workflows/da-02.yml` at the repository root |
| Architecture diagram | Ready | `docs/assets/architecture.svg/.png` (+ Mermaid in `docs/architecture.md`) |
| Data / API documentation | Ready | `docs/data-model.md`, `docs/data-dictionary.md`, `docs/dax-reference.md`, `docs/report-spec.md` (no custom API; REST calls: ADF→Power BI refresh, DAX `executeQueries`) |
| Test results + performance/accuracy numbers | **Partly** | Accuracy baselines and sandbox results are real ([test-plan-and-results.md](test-plan-and-results.md)); **you run the SQL Server and DAX suites and record ETL/refresh/page timings** |
| 10-minute final presentation | Script ready | [presentation-10min.md](presentation-10min.md) - build the slides, fill the ⟦…⟧ numbers |
| Individual reflection per intern | **You must write** | [reflections-template.md](reflections-template.md) |
| One-page user guide (step 7) | Ready | `docs/user-guide.md` / `docs/user-guide.pdf` |

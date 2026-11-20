"""Generates the Azure Data Factory artifacts (same layout as ADF's Git integration: linkedService/, dataset/, pipeline/, trigger/).
Placeholders {{LIKE_THIS}} are replaced by scripts/deploy_adf.ps1."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E = lambda s: {"value": s, "type": "Expression"}
LS = lambda n: {"referenceName": n, "type": "LinkedServiceReference"}
def put(folder, name, props):
    p = os.path.join(ROOT, "adf", folder); os.makedirs(p, exist_ok=True)
    json.dump({"name": name, "properties": props}, open(os.path.join(p, name + ".json"), "w"), indent=2); open(os.path.join(p, name + ".json"), "a").write("\n")

def ds_ref(name, **params):
    return {"referenceName": name, "type": "DatasetReference", "parameters": {k: (E(v) if isinstance(v, str) and v.startswith("@") else v) for k, v in params.items()}}

def kv_secret(name): return {"type": "AzureKeyVaultSecret", "store": LS("ls_keyvault"), "secretName": name}

def run():
    put("linkedService", "ls_keyvault", {"type": "AzureKeyVault", "typeProperties": {"baseUrl": "https://{{KEYVAULT_NAME}}.vault.azure.net/"}})
    put("linkedService", "ls_sql_source", {"type": "SqlServer", "connectVia": {"referenceName": "{{SELF_HOSTED_IR_NAME}}", "type": "IntegrationRuntimeReference"},
        "typeProperties": {"connectionString": "Integrated Security=False;Data Source={{SOURCE_SQL_SERVER}};Initial Catalog={{SOURCE_DATABASE}};User ID={{SOURCE_SQL_USER}};Encrypt=True;TrustServerCertificate=True",
                           "password": kv_secret("sql-source-password")}, "description": "AdventureWorks2022 on SQL Server (reached through a self-hosted integration runtime)."})
    put("linkedService", "ls_sql_dw", {"type": "AzureSqlDatabase", "typeProperties": {
        "connectionString": "Integrated Security=False;Encrypt=True;Connection Timeout=30;Data Source={{DW_SQL_SERVER}};Initial Catalog={{DW_DATABASE}};User ID={{DW_SQL_USER}}",
        "password": kv_secret("sql-dw-password")}, "description": "AW_BI warehouse database (Azure SQL Database). For SQL Server swap the type to SqlServer + connectVia."})
    put("dataset", "ds_src_table", {"linkedServiceName": LS("ls_sql_source"), "type": "SqlServerTable",
        "parameters": {"schema_name": {"type": "string", "defaultValue": "Sales"}, "table_name": {"type": "string", "defaultValue": "SalesOrderHeader"}},
        "typeProperties": {"schema": E("@dataset().schema_name"), "table": E("@dataset().table_name")}})
    put("dataset", "ds_dw_table", {"linkedServiceName": LS("ls_sql_dw"), "type": "AzureSqlTable",
        "parameters": {"schema_name": {"type": "string", "defaultValue": "etl"}, "table_name": {"type": "string", "defaultValue": "source_table_config"}},
        "typeProperties": {"schema": E("@dataset().schema_name"), "table": E("@dataset().table_name")}})

    sel = "@concat('SELECT ', item().select_list, ' FROM [', item().source_schema, '].[', item().source_table, ']')"
    delta = ("@concat('SELECT ', item().select_list, ' FROM [', item().source_schema, '].[', item().source_table, '] WHERE [', item().watermark_column, '] > ''', "
             "activity('Get old watermark').output.firstRow.last_watermark, ''' AND [', item().watermark_column, '] <= ''', activity('Get new watermark').output.firstRow.new_watermark, '''')")
    sink_ds = [ds_ref("ds_dw_table", schema_name="@item().target_schema", table_name="@item().target_table")]
    src_ds = [ds_ref("ds_src_table", schema_name="@item().source_schema", table_name="@item().source_table")]
    retry = {"timeout": "0.02:00:00", "retry": 2, "retryIntervalInSeconds": 30, "secureOutput": False, "secureInput": False}
    copy_full = {"name": "Copy full", "type": "Copy", "policy": retry, "inputs": src_ds, "outputs": sink_ds, "typeProperties": {
        "source": {"type": "SqlServerSource", "sqlReaderQuery": E(sel), "queryTimeout": "02:00:00"},
        "sink": {"type": "AzureSqlSink", "preCopyScript": E("@concat('TRUNCATE TABLE [', item().target_schema, '].[', item().target_table, ']')"), "writeBehavior": "insert", "disableMetricsCollection": False},
        "enableStaging": False}}
    lk_old = {"name": "Get old watermark", "type": "Lookup", "policy": retry, "typeProperties": {
        "source": {"type": "AzureSqlSource", "sqlReaderQuery": E("@concat('SELECT CONVERT(varchar(30), last_watermark, 126) AS last_watermark FROM etl.watermark WHERE table_name = ''', item().target_table, '''')"), "queryTimeout": "02:00:00"},
        "dataset": ds_ref("ds_dw_table"), "firstRowOnly": True}}
    lk_new = {"name": "Get new watermark", "type": "Lookup", "policy": retry, "typeProperties": {
        "source": {"type": "SqlServerSource", "sqlReaderQuery": E("@concat('SELECT CONVERT(varchar(30), MAX([', item().watermark_column, ']), 126) AS new_watermark FROM [', item().source_schema, '].[', item().source_table, ']')"), "queryTimeout": "02:00:00"},
        "dataset": src_ds[0], "firstRowOnly": True}}
    copy_delta = {"name": "Copy delta (upsert)", "type": "Copy", "policy": retry, "inputs": src_ds, "outputs": sink_ds,
        "dependsOn": [{"activity": "Get old watermark", "dependencyConditions": ["Succeeded"]}, {"activity": "Get new watermark", "dependencyConditions": ["Succeeded"]}],
        "typeProperties": {"source": {"type": "SqlServerSource", "sqlReaderQuery": E(delta), "queryTimeout": "02:00:00"},
            "sink": {"type": "AzureSqlSink", "writeBehavior": "upsert", "upsertSettings": {"useTempDB": True, "keys": E("@split(item().key_columns, ',')")}, "disableMetricsCollection": False},
            "enableStaging": False}}
    sp_wm = {"name": "Update watermark", "type": "SqlServerStoredProcedure", "linkedServiceName": LS("ls_sql_dw"),
        "dependsOn": [{"activity": "Copy delta (upsert)", "dependencyConditions": ["Succeeded"]}],
        "typeProperties": {"storedProcedureName": "[etl].[usp_update_watermark]", "storedProcedureParameters": {
            "table_name": {"value": E("@item().target_table"), "type": "String"}, "new_watermark": {"value": E("@activity('Get new watermark').output.firstRow.new_watermark"), "type": "DateTime"}}}}
    put("pipeline", "pl_extract_to_staging", {"description": "Metadata-driven extract: reads etl.source_table_config, copies each source table to stg (FULL = truncate+load, INCREMENTAL = watermark + upsert).",
        "activities": [
          {"name": "Lookup table config", "type": "Lookup", "policy": retry, "typeProperties": {"source": {"type": "AzureSqlSource",
              "sqlReaderQuery": "SELECT source_schema, source_table, target_schema, target_table, load_type, watermark_column, key_columns, select_list FROM etl.source_table_config WHERE is_active = 1 ORDER BY load_order", "queryTimeout": "02:00:00"},
              "dataset": ds_ref("ds_dw_table"), "firstRowOnly": False}},
          {"name": "For each table", "type": "ForEach", "dependsOn": [{"activity": "Lookup table config", "dependencyConditions": ["Succeeded"]}],
           "typeProperties": {"items": E("@activity('Lookup table config').output.value"), "isSequential": False, "batchCount": 4, "activities": [
              {"name": "Full or incremental", "type": "IfCondition", "typeProperties": {"expression": E("@equals(item().load_type, 'FULL')"),
                  "ifTrueActivities": [copy_full], "ifFalseActivities": [lk_old, lk_new, copy_delta, sp_wm]}}]}}],
        "annotations": ["aw-bi"]})
    put("pipeline", "pl_transform_and_test", {"description": "Runs the warehouse load (dims, facts) and the data-quality gate. Fails the pipeline if an ERROR check fails.",
        "activities": [{"name": "Run etl.usp_run_all", "type": "SqlServerStoredProcedure", "linkedServiceName": LS("ls_sql_dw"), "policy": {"timeout": "0.02:00:00", "retry": 1, "retryIntervalInSeconds": 60},
            "typeProperties": {"storedProcedureName": "[etl].[usp_run_all]", "storedProcedureParameters": {
                "extract_mode": {"value": "ADF", "type": "String"},
                "triggered_by": {"value": E("@concat('ADF ', pipeline().Pipeline, ' run ', pipeline().RunId)"), "type": "String"}}}}], "annotations": ["aw-bi"]})
    pbi = {"name": "Refresh Power BI dataset", "type": "IfCondition", "dependsOn": [{"activity": "Transform and test", "dependencyConditions": ["Succeeded"]}],
        "typeProperties": {"expression": E("@and(not(empty(pipeline().parameters.pbiWorkspaceId)), not(empty(pipeline().parameters.pbiDatasetId)))"),
          "ifTrueActivities": [{"name": "POST refresh", "type": "WebActivity", "typeProperties": {
              "url": E("@concat('https://api.powerbi.com/v1.0/myorg/groups/', pipeline().parameters.pbiWorkspaceId, '/datasets/', pipeline().parameters.pbiDatasetId, '/refreshes')"),
              "method": "POST", "headers": {"Content-Type": "application/json"}, "body": {"notifyOption": "MailOnFailure"},
              "authentication": {"type": "MSI", "resource": "https://analysis.windows.net/powerbi/api"}}}]}}
    alert = {"name": "Alert on failure", "type": "IfCondition",
        "dependsOn": [{"activity": "Extract to staging", "dependencyConditions": ["Failed"]}, {"activity": "Transform and test", "dependencyConditions": ["Failed"]}],
        "typeProperties": {"expression": E("@not(empty(pipeline().parameters.alertWebhookUrl))"),
          "ifTrueActivities": [{"name": "POST webhook", "type": "WebActivity", "typeProperties": {"url": E("@pipeline().parameters.alertWebhookUrl"), "method": "POST",
              "headers": {"Content-Type": "application/json"}, "body": E("@json(concat('{\"text\":\"AW_BI nightly pipeline FAILED. Run id: ', pipeline().RunId, '\"}'))")}}]}}
    put("pipeline", "pl_master_daily", {"description": "Nightly orchestration: extract -> transform + DQ gate -> Power BI refresh. Webhook alert on failure.",
        "parameters": {"pbiWorkspaceId": {"type": "string", "defaultValue": ""}, "pbiDatasetId": {"type": "string", "defaultValue": ""}, "alertWebhookUrl": {"type": "string", "defaultValue": ""}},
        "activities": [
          {"name": "Extract to staging", "type": "ExecutePipeline", "typeProperties": {"pipeline": {"referenceName": "pl_extract_to_staging", "type": "PipelineReference"}, "waitOnCompletion": True}},
          {"name": "Transform and test", "type": "ExecutePipeline", "dependsOn": [{"activity": "Extract to staging", "dependencyConditions": ["Succeeded"]}],
           "typeProperties": {"pipeline": {"referenceName": "pl_transform_and_test", "type": "PipelineReference"}, "waitOnCompletion": True}}, pbi, alert], "annotations": ["aw-bi"]})
    put("trigger", "tr_daily_0200", {"type": "ScheduleTrigger", "pipelines": [{"pipelineReference": {"referenceName": "pl_master_daily", "type": "PipelineReference"},
        "parameters": {"pbiWorkspaceId": "", "pbiDatasetId": "", "alertWebhookUrl": ""}}],
        "typeProperties": {"recurrence": {"frequency": "Day", "interval": 1, "startTime": "2026-01-01T02:00:00", "timeZone": "India Standard Time", "schedule": {"hours": [2], "minutes": [0]}}}})
if __name__ == "__main__": run()

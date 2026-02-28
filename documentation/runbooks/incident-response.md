# Runbook: Incident Response Playbook

## Purpose

This playbook defines the incident response process for the Azure Data Platform.
It covers detection, triage, escalation, resolution, and post-incident review.

---

## Severity Definitions

| Severity | Definition | Response Time | Update Frequency |
|----------|-----------|--------------|-----------------|
| **SEV1** | Complete production outage or confirmed data loss. All users unable to access the platform. | Immediate (< 15 min) | Every 30 minutes |
| **SEV2** | Major feature degraded or unavailable. Significant user impact with no workaround. | < 30 minutes | Every 1 hour |
| **SEV3** | Partial degradation. Workaround available. Limited user impact. | < 2 hours | Every 4 hours |

---

## Incident Response Process

### Phase 1: Detection and Initial Response

#### 1.1 Detection Sources

| Source | Type | Alert Channel |
|--------|------|--------------|
| Azure Monitor | Automated | Email, Teams webhook |
| Fabric Pipeline Failures | Automated | Email notification |
| Application Insights | Automated | Email, Action Group |
| User Report | Manual | Teams message, email |
| CI/CD Failure | Automated | GitHub notification |
| Azure Service Health | Automated | Email, Action Group |

#### 1.2 Initial Triage (First 15 Minutes)

When an incident is detected:

1. **Acknowledge the alert** -- Confirm you are investigating.

2. **Assess severity** using the definitions above. Ask:
   - Is production completely down? (SEV1)
   - Is a critical feature broken with no workaround? (SEV2)
   - Is there degradation but the platform is usable? (SEV3)

3. **Create an incident issue** in GitHub using the Incident Report template.

4. **Notify the team** via Teams/Slack:
   ```
   INCIDENT: [SEV1/2/3] - Brief description
   Status: Investigating
   Impact: [describe user impact]
   Tracking: [link to GitHub issue]
   Investigating: [your name]
   ```

5. **Check for Azure-side issues first:**
   ```bash
   # Check Azure Service Health
   az rest --method get \
     --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.ResourceHealth/events?api-version=2022-10-01" \
     --query "value[?status=='Active']"
   ```

#### 1.3 Assemble the Response Team

| Role | Responsibility |
|------|---------------|
| **Incident Commander (IC)** | Coordinates response, communicates status, makes decisions |
| **Investigator** | Diagnoses root cause, implements fix |
| **Communicator** | Updates stakeholders and the incident issue timeline |

For a small team, one person may fill multiple roles. The person who detects the
incident is the default IC until handoff.

---

### Phase 2: Investigation

#### 2.1 Common Investigation Steps

**Check Azure Resource Health:**
```bash
# Check resource health for the subscription
az resource list --query "[].{name:name, type:type}" -o table

# Check specific resource health
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/$RESOURCE_TYPE/$RESOURCE_NAME/providers/Microsoft.ResourceHealth/availabilityStatuses/current?api-version=2023-07-01-preview"
```

**Check Application Insights for errors:**
```bash
# Query Application Insights for recent exceptions
az monitor app-insights query \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RG" \
  --analytics-query "exceptions | where timestamp > ago(1h) | summarize count() by problemId | top 10 by count_"
```

**Check Log Analytics:**
```bash
# Query Log Analytics for error patterns
az monitor log-analytics query \
  --workspace "$LAW_ID" \
  --analytics-query "AzureDiagnostics | where TimeGenerated > ago(1h) | where Level == 'Error' | summarize count() by Resource, OperationName | top 20 by count_" \
  -o table
```

#### 2.2 Service-Specific Investigation

##### Microsoft Fabric Issues

```bash
# Check Fabric capacity status
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Fabric/capacities/$CAPACITY_NAME?api-version=2023-11-01"
```

- Check Fabric admin portal for capacity health
- Review pipeline run history in Fabric workspace
- Check for Fabric service incidents at https://status.fabric.microsoft.com

**Common Fabric issues:**
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Pipeline failures | Capacity paused/exhausted | Resume capacity, check CU usage |
| Notebook timeout | Memory/compute exhaustion | Scale capacity, optimize code |
| Data refresh failure | Source connectivity | Check Private Endpoint, credentials |

##### PostgreSQL Issues

```bash
# Check server status
az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$SERVER_NAME" \
  --query '{state:state, sku:sku.name, storage:storage.storageSizeGb}' \
  -o table

# Check connection count
az postgres flexible-server parameter show \
  --resource-group "$RG" \
  --name "$SERVER_NAME" \
  --parameter-name max_connections

# Check recent metrics
az monitor metrics list \
  --resource "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.DBforPostgreSQL/flexibleServers/$SERVER_NAME" \
  --metric "cpu_percent,memory_percent,active_connections,storage_percent" \
  --interval PT5M \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  -o table
```

**Common PostgreSQL issues:**
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Connection refused | Server stopped, max connections | Restart server, check connection pool |
| Slow queries | Missing indexes, high CPU | Check query plans, pg_stat_activity |
| Storage full | Data growth, WAL bloat | Expand storage, vacuum, archive old data |
| pgvector slow | HNSW index not built | Build/rebuild HNSW index |

##### Application (Streamlit/React) Issues

```bash
# Check App Service status
az webapp show \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --query '{state:state, availability:availabilityState}' \
  -o table

# Check recent logs
az webapp log tail \
  --resource-group "$RG" \
  --name "$APP_NAME"

# Check health endpoint
curl -sf "https://$APP_NAME.azurewebsites.net/healthz" -w "\nHTTP Status: %{http_code}\n"

# Restart the app (if needed)
az webapp restart \
  --resource-group "$RG" \
  --name "$APP_NAME"
```

**Common App Service issues:**
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| 502/503 errors | Container crash, startup failure | Check logs, restart, rollback |
| Slow response | Resource exhaustion, cold start | Scale up/out, check dependencies |
| Auth failures | Token expiry, Entra ID config | Check managed identity, token cache |

##### AI Foundry Issues

```bash
# Check model deployment status
az cognitiveservices account deployment list \
  --resource-group "$RG" \
  --name "$AI_ACCOUNT_NAME" \
  --query "[].{name:name, status:properties.provisioningState}" \
  -o table
```

**Common AI Foundry issues:**
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| 429 Too Many Requests | Rate limit exceeded | Implement backoff, check quota |
| Model unavailable | Deployment scaled to zero | Redeploy model |
| Embedding failures | Input too long, encoding issues | Validate input, check token limits |

---

### Phase 3: Mitigation and Resolution

#### 3.1 Mitigation Options (Fast Fixes)

| Action | When to Use | Command |
|--------|------------|---------|
| **Restart App Service** | App unresponsive, memory leak | `az webapp restart --name $APP --resource-group $RG` |
| **Scale up Fabric** | Capacity exhaustion | Scale via Fabric admin portal |
| **Resume Fabric capacity** | Capacity paused | `az fabric capacity resume --name $CAPACITY --resource-group $RG` |
| **Restart PostgreSQL** | Server unresponsive | `az postgres flexible-server restart --name $SERVER --resource-group $RG` |
| **Rollback deployment** | Bad deployment caused issue | Swap staging slot back, or redeploy previous image |
| **Failover to read replica** | Primary DB issues | Promote read replica (if configured) |

#### 3.2 Rollback Procedures

**Application rollback (slot swap):**
```bash
# Swap staging slot back to production (reverting the last deployment)
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --slot staging \
  --target-slot production
```

**Application rollback (previous image):**
```bash
# Find the previous image tag
PREV_TAG="<previous-git-sha>"

# Redeploy previous image
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --container-image-name "ghcr.io/vamshi455/azureai/streamlit-admin:$PREV_TAG"

az webapp restart --resource-group "$RG" --name "$APP_NAME"
```

**Infrastructure rollback:**
```bash
# Deploy the previous known-good Bicep commit
git checkout "<known-good-commit>" -- infra/
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters "infra/parameters/$ENV.bicepparam" \
  --name "rollback-$ENV-$(date +%Y%m%d%H%M)"
```

#### 3.3 Resolution Confirmation

Before declaring the incident resolved:

- [ ] The root cause has been identified and fixed (or a workaround is in place)
- [ ] Affected services are responding normally
- [ ] Health check endpoints return 200
- [ ] Data pipelines are processing (if applicable)
- [ ] No new errors in Application Insights / Log Analytics
- [ ] Users confirm functionality is restored

---

### Phase 4: Communication

#### 4.1 Status Update Template

```
INCIDENT UPDATE: [SEV1/2/3] - Brief description
Status: [Investigating | Identified | Mitigating | Resolved]
Impact: [describe current user impact]
Root Cause: [if known]
Next Update: [time of next update]
Tracking: [link to GitHub issue]
```

#### 4.2 Resolution Notification

```
INCIDENT RESOLVED: [SEV1/2/3] - Brief description
Duration: [start time] to [end time] ([duration])
Root Cause: [brief root cause]
Resolution: [what was done to fix it]
Follow-up: [link to post-incident review]
```

---

### Phase 5: Post-Incident Review

Conduct a post-incident review within **48 hours** of resolution for SEV1/SEV2 incidents.

#### 5.1 Post-Incident Review Template

Document the following in the GitHub incident issue:

```markdown
## Post-Incident Review

### Timeline
- [Time]: Incident detected via [method]
- [Time]: Investigation started by [person]
- [Time]: Root cause identified
- [Time]: Mitigation applied
- [Time]: Service restored
- [Time]: Incident declared resolved

### Root Cause Analysis
[Detailed explanation of what caused the incident]

### What Went Well
- [Things that worked during the response]

### What Could Be Improved
- [Areas for improvement]

### Action Items
- [ ] [Action item with owner and due date]
- [ ] [Action item with owner and due date]
- [ ] [Update monitoring/alerting for this failure mode]
- [ ] [Update this runbook if procedures were missing]
```

#### 5.2 Action Item Categories

| Category | Examples |
|----------|---------|
| **Detection** | Add alerts, improve monitoring coverage |
| **Prevention** | Code review improvements, additional tests, guardrails |
| **Mitigation** | Faster rollback procedures, circuit breakers, retries |
| **Process** | Update runbooks, improve communication templates |

---

## Quick Reference: Emergency Commands

```bash
# ---- App Service ----
az webapp restart --name $APP --resource-group $RG
az webapp stop --name $APP --resource-group $RG
az webapp start --name $APP --resource-group $RG
az webapp log tail --name $APP --resource-group $RG

# ---- PostgreSQL ----
az postgres flexible-server restart --name $SERVER --resource-group $RG
az postgres flexible-server stop --name $SERVER --resource-group $RG
az postgres flexible-server start --name $SERVER --resource-group $RG

# ---- Fabric ----
az fabric capacity resume --name $CAPACITY --resource-group $RG
az fabric capacity suspend --name $CAPACITY --resource-group $RG

# ---- Networking ----
az network nsg rule list --nsg-name $NSG --resource-group $RG -o table
az network private-endpoint show --name $PE --resource-group $RG

# ---- Key Vault ----
az keyvault secret list --vault-name $KV -o table

# ---- Diagnostics ----
az monitor activity-log list --subscription $SUB \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --query "[?status.value=='Failed']" -o table
```

---

## Escalation Matrix

| Severity | Primary Contact | Escalation (if no response in 15 min) | External |
|----------|----------------|---------------------------------------|----------|
| SEV1 | Team Lead | Engineering Manager | Azure Support (Sev A) |
| SEV2 | On-call Engineer | Team Lead | Azure Support (Sev B) |
| SEV3 | Any Team Member | On-call Engineer | N/A |

### Azure Support

For Azure platform issues beyond our control:

```bash
# Create Azure support request
az support tickets create \
  --ticket-name "INC-$(date +%Y%m%d%H%M)" \
  --title "Brief incident description" \
  --description "Detailed description" \
  --severity "critical" \
  --problem-classification "/providers/Microsoft.Support/services/<service-id>/problemClassifications/<classification-id>"
```

Or via Azure Portal: https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade

---

## Maintenance Windows

| Day | Time (UTC) | Activity |
|-----|-----------|----------|
| Tuesday | 02:00-06:00 | Azure platform maintenance window |
| Thursday | 22:00-02:00 | Planned deployment window |

Non-emergency deployments should be scheduled during planned windows. Emergency fixes
can be deployed at any time following this incident response process.

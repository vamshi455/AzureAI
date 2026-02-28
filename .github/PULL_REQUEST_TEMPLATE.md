## Summary

<!-- Provide a concise description of the changes in this PR. What problem does it solve? -->

## Type of Change

- [ ] Infrastructure (Bicep/ARM templates)
- [ ] Data Platform (notebooks, pipelines, SQL)
- [ ] Application (Streamlit, React)
- [ ] CI/CD (GitHub Actions workflows)
- [ ] Documentation
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Refactoring (no functional changes)

## Affected Components

- [ ] Microsoft Fabric
- [ ] Microsoft Purview
- [ ] AI Foundry
- [ ] PostgreSQL / pgvector
- [ ] Streamlit Admin App
- [ ] React Web App
- [ ] Networking
- [ ] Security / IAM
- [ ] Other: <!-- specify -->

## Changes Made

<!-- List the specific changes made in this PR -->

-
-
-

## Environment Impact

| Environment | Impact |
|-------------|--------|
| Dev         | <!-- describe impact or "N/A" --> |
| QA          | <!-- describe impact or "N/A" --> |
| Prod        | <!-- describe impact or "N/A" --> |

## Testing

### Tests Performed

- [ ] Unit tests pass locally
- [ ] Integration tests pass (if applicable)
- [ ] Manually tested in Dev environment
- [ ] Bicep what-if reviewed (for infra changes)

### How to Test

<!-- Provide steps for reviewers to test or verify the changes -->

1.
2.
3.

## Infrastructure Changes (if applicable)

- [ ] Bicep templates lint successfully (`az bicep build`)
- [ ] Parameters updated for all environments (dev, qa, prod)
- [ ] What-if output reviewed -- no unexpected deletions or modifications
- [ ] Cost impact assessed
- [ ] Network/security group changes reviewed

## Data Platform Changes (if applicable)

- [ ] Notebook executes successfully end-to-end
- [ ] SQL scripts validated
- [ ] Data lineage in Purview updated (if schema changes)
- [ ] Backward compatibility verified for downstream consumers
- [ ] No PII or sensitive data in notebook outputs

## Application Changes (if applicable)

- [ ] Application builds successfully
- [ ] No new security vulnerabilities (check Trivy scan)
- [ ] Environment variables documented
- [ ] Health check endpoint works
- [ ] Responsive design verified (React)

## Security Checklist

- [ ] No secrets, keys, or connection strings in code
- [ ] No PII in logs or comments
- [ ] RBAC / permissions changes reviewed
- [ ] Network security changes reviewed
- [ ] Trivy security scan passes

## Documentation

- [ ] Code comments added for complex logic
- [ ] README or docs updated (if applicable)
- [ ] ADR created for significant architectural decisions
- [ ] Naming conventions followed (see `documentation/architecture/naming-conventions.md`)

## Rollback Plan

<!-- How would you roll back these changes if something goes wrong? -->

## Related Issues

<!-- Link related issues: Fixes #123, Relates to #456 -->

## Screenshots / Evidence

<!-- If applicable, add screenshots, what-if output, or test results -->

---

**Reviewer Notes:**
- For infrastructure changes, carefully review the what-if output in the CI pipeline
- For data platform changes, verify no breaking schema changes
- For application changes, verify the health check passes in the deploy pipeline

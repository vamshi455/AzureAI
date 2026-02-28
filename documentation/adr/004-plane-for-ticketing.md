# ADR-004: Plane for Project Ticketing and Issue Tracking

## Status

**Accepted** -- 2026-02-28

## Context

We need a project management and issue tracking tool for the data platform team (4-10
people). The tool must support:

1. **Issue tracking** -- Bug reports, feature requests, tasks, and incidents.
2. **Sprint/cycle planning** -- Organizing work into iterations.
3. **Kanban boards** -- Visual workflow management.
4. **GitHub integration** -- Linking issues to PRs and commits.
5. **Reasonable cost** -- Budget-appropriate for a small team.
6. **Self-hosting option** -- Preferred for data sovereignty and control, though not
   strictly required.

### Options Evaluated

| Tool | Open Source | Self-Hostable | Free Tier | GitHub Integration |
|------|-----------|--------------|-----------|-------------------|
| Plane | Yes | Yes | Yes (unlimited) | Yes |
| Jira | No | No (Cloud only for new) | 10 users free | Yes |
| Linear | No | No | 250 issues free | Yes |
| GitHub Issues/Projects | Partially | No | Yes | Native |
| Azure DevOps Boards | No | No | 5 users free | Limited |

## Decision

We will use **Plane** (self-hosted) as our project management and issue tracking tool.

### Rationale

**1. Open source with self-hosting**

Plane is open source (Apache 2.0 / AGPL) and can be self-hosted via Docker. This gives
us:
- Full control over our project data
- No vendor lock-in
- No per-user pricing constraints
- Ability to customize if needed

For a manufacturing company with potentially sensitive project information (production
issues, security incidents), self-hosting is a meaningful advantage.

**2. Free for unlimited users**

The self-hosted Community Edition is free with no user limits. For a growing team (4-10
people), this eliminates per-seat costs. Jira charges $7.75/user/month (Standard),
and Linear charges $8/user/month, which adds up as the team grows.

| Tool | Cost for 10 users/month |
|------|------------------------|
| Plane (self-hosted) | $0 |
| Jira Standard | $77.50 |
| Linear | $80 |
| GitHub Issues | $0 (but limited features) |

**3. Modern UX comparable to Linear**

Plane provides a clean, modern interface similar to Linear, with:
- Kanban boards and list views
- Cycles (sprints) with burn-down charts
- Modules for grouping related work
- Custom properties and filters
- Keyboard shortcuts for fast navigation

This is a significant UX improvement over Jira, which has a steeper learning curve and
more complex interface.

**4. GitHub integration**

Plane integrates with GitHub to:
- Link Plane issues to GitHub PRs and branches
- Auto-update issue status when PRs are merged
- Reference Plane issue IDs in commit messages

This keeps the development workflow connected between project management and code.

**5. Suitable for small team workflows**

Plane is designed for teams our size. It provides the essential project management
features without the complexity overhead of enterprise tools like Jira. The team can
be productive immediately without extensive tool configuration.

**6. Docker deployment on Azure**

Plane's Docker-based deployment can run on:
- Azure Container Instances (simplest, low cost)
- Azure App Service (containers)
- Azure Kubernetes Service (if we already have a cluster)

This aligns with our Azure-first infrastructure strategy.

## Consequences

### Positive

- **Zero licensing cost** for the self-hosted Community Edition.
- **Full data sovereignty** with self-hosting.
- **Modern, intuitive UX** reduces onboarding time.
- **GitHub integration** maintains developer workflow continuity.
- **No user limit** -- supports team growth without cost scaling.
- **Open source** -- no vendor lock-in, community-driven development.

### Negative

- **Self-hosting responsibility** -- We must manage the Plane deployment (updates,
  backups, availability). This is additional operational work.
- **Smaller ecosystem** -- Fewer third-party integrations compared to Jira. No native
  Slack bot (though webhooks are available).
- **Less mature** -- Plane is newer than Jira and Linear. Some features may be less
  polished or missing compared to established competitors.
- **Single-vendor risk** -- If the Plane project becomes unmaintained, we would need
  to migrate. Mitigated by the open source license allowing community forks.
- **Limited enterprise features** -- Advanced reporting, time tracking, and portfolio
  management are less developed than in Jira.

### Mitigations

- Automate Plane deployment and backups using our existing IaC and CI/CD patterns.
- Use Plane's webhook API for custom integrations (e.g., Slack notifications).
- Maintain export capability so data can be migrated if needed.
- Monitor the Plane project's health and community activity.
- If enterprise features become needed, evaluate migration to Jira or Linear at that
  point.

## Alternatives Rejected

### Jira

The industry standard, but rejected because:
- Per-user pricing ($7.75+/user/month) is unnecessary cost for a small team
- Complex interface with significant configuration overhead
- Atlassian Cloud-only for new customers (no self-hosting)
- Feature-heavy for our team size (we would use <20% of capabilities)

### Linear

Excellent UX and developer experience, but rejected because:
- No self-hosting option
- Per-user pricing ($8/user/month)
- 250-issue limit on the free tier
- Closed source

### GitHub Issues + GitHub Projects

Native GitHub integration is appealing, but rejected because:
- Limited project management features (no cycles/sprints, limited reporting)
- No standalone project views outside of GitHub
- Issue templates are rigid compared to Plane's custom properties
- Not suitable for non-developer stakeholders who need project visibility
  without GitHub access

We do use GitHub Issues for code-specific concerns (bug reports, PRs) while
Plane handles broader project management and sprint planning.

### Azure DevOps Boards

Rejected because:
- Only 5 free users (then $6/user/month)
- Limited GitHub integration (designed primarily for Azure Repos)
- Heavier weight than needed for our team size
- The rest of our toolchain is GitHub-based, not Azure DevOps-based

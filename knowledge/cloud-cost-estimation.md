---
created: '2026-04-22T23:01:17'
promoted_to: []
pursuit: null
source: project-ariadne
status: polished
tags:
- concept
title: Cloud Cost Estimation
topic: Workload Analysis
type: article
updated: '2026-04-22T23:01:17'
tier: doctrine
---

> **Entity type:** `concept`

Cloud consumption pricing for AWS GovCloud, Azure Government, and similar environments requires its own BOE discipline. Cost drivers: (1) COMPUTE — instance-hours by family/size with right-sizing plan, (2) STORAGE — tiered (hot/warm/cold) by retention, (3) NETWORK — egress (largest surprise category), inter-region, VPN/Direct Connect, (4) MANAGED SERVICES — databases, analytics, containers typically dominate variable cost, (5) LICENSING — BYOL vs pay-as-you-go for Windows/Oracle/SQL Server. Pricing strategy: (a) use current published cloud calculators as the floor; (b) apply reserved-instance / savings-plan commitment discounts only to the portion of load that is genuinely steady-state; (c) include egress at realistic transfer volumes — egress underestimates are a leading cost-realism finding; (d) carry a 10-20% cloud growth contingency for multi-year ordering periods. Anti-pattern: quoting list prices without egress or without a FinOps management approach — evaluators read this as naive.
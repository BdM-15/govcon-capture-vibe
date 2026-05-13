---
created: '2026-04-22T23:01:17'
promoted_to: []
pursuit: null
source: project-ariadne
status: polished
tags:
- concept
title: Service Desk Staffing Model
topic: Workload Analysis
type: article
updated: '2026-04-22T23:01:17'
tier: doctrine
---

> **Entity type:** `concept`

Service desk/help desk staffing based on ticket volume and service levels. Key drivers: (1) Monthly ticket volume (from RFP or historical data), (2) Average handle time (AHT) per ticket type (typically 10-30 minutes), (3) First call resolution (FCR) target (typically 70-85%), (4) Service level agreement (e.g., 80% answered within 60 seconds), (5) Coverage hours (8×5, 12×5, 24×7). Erlang C formula for queue-based staffing. Rule of thumb: 1 FTE per 400-600 tickets/month for Tier 1 support. Add Tier 2/3 escalation staff at 20-30% of Tier 1 volume. Adjust for complexity and SLA stringency.
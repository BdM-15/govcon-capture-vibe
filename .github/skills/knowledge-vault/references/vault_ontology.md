# Vault Ontology Quick Reference

## VALID_ENTITY_TYPES (32 govcon entity types)

Use these exact snake_case names in entity proposals. Any proposal using a type not in this list will be rejected by the extraction pipeline.

| Type | Typical vault note signal |
|------|--------------------------|
| `amendment` | "Amendment 0001", "modification", "contract mod" |
| `clause` | "FAR 52.xxx", "DFARS clause", "deviation" |
| `compliance_artifact` | "CDRL", "DID", "data delivery requirement" |
| `concept` | Abstract ideas, methodologies, approaches |
| `contract_line_item` | "CLIN 0001", "subCLIN", "SLIN" |
| `contract_vehicle` | "IDIQ", "BPA", "GWAC", "MATOC" |
| `customer_priority` | Hot buttons, evaluation hot spots, stated customer goals |
| `deliverable` | Concrete outputs the offeror must produce |
| `document` | Plans, policies, standards, regulations, manuals |
| `document_section` | Sections L, M, H, J; PWS §§; SOW sections |
| `equipment` | Hardware, physical assets, model numbers |
| `evaluation_factor` | Section M factors, subfactors, scoring criteria |
| `event` | Milestones, kickoffs, option exercise dates |
| `government_furnished_item` | GFE, GFI, GFD, government-owned assets |
| `labor_category` | "Senior Systems Engineer", "Program Manager", LCAT names |
| `location` | Installation, base, CONUS/OCONUS site |
| `organization` | Companies, agencies, program offices, commands |
| `pain_point` | Problems the solution must solve; risk areas |
| `past_performance_reference` | Prior contracts, OPRs, CPARs, PPIRS references |
| `performance_standard` | AQLs, AQLIs, SLAs, QASPs, thresholds |
| `period_of_performance` | Base year, option years, PoP dates |
| `pricing_element` | Labor hours, ODC budget, fee structure, wrap rates |
| `program` | Parent program, initiative, PMO |
| `proposal_instruction` | Section L instructions to offerors |
| `proposal_volume` | Volume I, Volume II, Cost Volume |
| `regulatory_reference` | NIST SP, DAFI, MIL-STD, OMB Circular |
| `requirement` | Mandatory "shall" statements, functional requirements |
| `strategic_theme` | Win themes, discriminators, FAB statements, ghost language |
| `technical_specification` | Technical standards, metrics, interface requirements |
| `technology` | Software platforms, systems, tools |
| `work_scope_item` | PWS task paragraphs, SOW work items |
| `workload_metric` | FTEs, ticket volumes, service requests, demand data |

## Entity Proposal Format

When surfacing entity proposals in a vault note, use this format:

```
ENTITY: <exact phrase from note> | TYPE: <entity_type> | CONFIDENCE: <0.0-1.0>
```

Example:
```
ENTITY: 25-page Technical Approach limit | TYPE: proposal_instruction | CONFIDENCE: 0.95
ENTITY: CPFF completion form | TYPE: pricing_element | CONFIDENCE: 0.85
ENTITY: CMMC Level 2 | TYPE: requirement | CONFIDENCE: 0.9
```

## Key Relationship Types for Vault Notes

When describing connections between notes and KG entities:

| Relationship | Meaning |
|-------------|---------|
| `ADDRESSES` | Note addresses a requirement or pain point |
| `RESPONDS_TO` | Note content responds to a proposal_instruction |
| `SUPPORTS` | Note supports an evaluation_factor or strategic_theme |
| `DERIVED_FROM` | Evergreen note derived from raw capture |
| `RELATED_TO` | General semantic relationship |
| `DEMONSTRATES` | Past performance reference demonstrates a capability |
| `SATISFIES` | Deliverable or work_scope_item satisfies a requirement |

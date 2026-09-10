"""
Curated seed for the Arab Risk Monitor knowledge graph.

This is the one hand-authored input to the graph. `etl/build_graph.py` takes
it, adds a node for every indicator in the registry and every source paper,
attaches supporting passages by searching the papers corpus, validates that
every edge connects two real nodes, and writes data/graph/knowledge_graph.json.

The structure follows the "Pathways for Peace" framework (World Bank / UN,
2018): societies move along a pathway between *sustainable peace* and
*violent conflict*; that pathway is shaped by ACTORS, INSTITUTIONS and
STRUCTURAL FACTORS. Grievances rooted in inequality and exclusion get
contested in four ARENAS (power and governance; land and natural resources;
service delivery; security and justice). RISK FACTORS push toward violence;
POLICY LEVERS — the prevention measures the report recommends — push back.
The Arab Risk Monitor INDICATORS are how each risk factor is measured for the
22 Arab States.

node types: concept | pathway_element | arena | risk_factor | policy_lever
            | actor | indicator (added by build) | paper (added by build)
edge rels:  part_of | contested_in | drives | intersects | undermines
            | mitigates | strengthens | measured_by | monitored_by
            | recommended_in (added by build) | evidence_in (added by build)
"""

from __future__ import annotations

# --------------------------------------------------------------------- nodes
NODES: list[dict] = [
    # -- core concepts -----------------------------------------------------
    {
        "id": "violent-conflict",
        "type": "concept",
        "label": "Violent conflict",
        "summary": "Organized collective violence — from communal violence to civil war. "
        "Pathways for Peace documents a 21st-century surge after decades of decline, "
        "driven increasingly by non-state actors and cross-border dynamics.",
        "query": "surge in violent conflict trends 21st century battle deaths non-state actors",
    },
    {
        "id": "sustainable-peace",
        "type": "concept",
        "label": "Sustainable peace",
        "summary": "Not merely the absence of violence but a society built on inclusive "
        "development, justice, equity and human rights, able to manage its conflicts "
        "constructively over time.",
        "query": "sustainable peace definition sustaining peace resolutions inclusive society",
    },
    {
        "id": "prevention",
        "type": "concept",
        "label": "Prevention of violent conflict",
        "summary": "Activities aimed at preventing the outbreak, escalation, continuation and "
        "recurrence of conflict by addressing root causes. Pathways for Peace finds prevention "
        "works and is cost-effective — net savings of roughly US$5–70 billion a year.",
        "query": "prevention works cost-effective sustained inclusive targeted principles",
    },
    # -- pathway elements ------------------------------------------------
    {
        "id": "actors",
        "type": "pathway_element",
        "label": "Actors",
        "summary": "Individuals and groups whose decisions ultimately define the pathway a "
        "society takes. Elites, leaders, movements, security forces, communities.",
        "query": "centrality of actors decisions elites leaders incentives pathway",
    },
    {
        "id": "institutions",
        "type": "pathway_element",
        "label": "Institutions",
        "summary": "The formal rules and informal norms that shape incentives for peace or "
        "violence — a society's 'immune system' against pressures toward violence.",
        "query": "institutions rules of the game immune system incentives contain violence",
    },
    {
        "id": "structural-factors",
        "type": "pathway_element",
        "label": "Structural factors",
        "summary": "Slow-changing foundations of a society: geography, demography, economic "
        "structure, distribution of resources, legacies of violence, systemic stresses like "
        "climate change.",
        "query": "structural factors geography demography economy resource distribution slow changing",
    },
    # -- arenas of contestation ----------------------------------------
    {
        "id": "arena-power-governance",
        "type": "arena",
        "label": "Arena: Power and governance",
        "summary": "Contestation over who holds power and how it is exercised — elections, "
        "constitutions, representation, 'winner-takes-all' politics.",
        "query": "arena of power and governance winner takes all elections representation power sharing",
    },
    {
        "id": "arena-land-resources",
        "type": "arena",
        "label": "Arena: Land and natural resources",
        "summary": "Contestation over land, water, minerals and their revenues — strongest at "
        "local level, aggravated by climate change, population growth and large-scale agriculture.",
        "query": "arena of land and natural resources water pastoralists farmers tenure revenues",
    },
    {
        "id": "arena-service-delivery",
        "type": "arena",
        "label": "Arena: Service delivery",
        "summary": "Contestation over access to and quality of basic services (education, health, "
        "water, infrastructure) and the perceived fairness of their distribution.",
        "query": "arena of service delivery access basic services fairness state legitimacy",
    },
    {
        "id": "arena-security-justice",
        "type": "arena",
        "label": "Arena: Security and justice",
        "summary": "Contestation over physical security and access to justice — abusive or "
        "exclusionary security forces, impunity, weak or plural justice systems.",
        "query": "arena of security and justice policing impunity human rights traditional formal justice",
    },
    # -- risk factors -------------------------------------------------
    {
        "id": "horizontal-inequality",
        "type": "risk_factor",
        "label": "Horizontal inequality",
        "summary": "Systematic inequality between identity or regional groups in political power, "
        "economic resources, services and security. The report's central structural driver of "
        "modern conflict.",
        "aliases": ["group inequality", "intergroup inequality"],
        "query": "horizontal inequality between groups political economic social conflict risk",
    },
    {
        "id": "group-grievances",
        "type": "risk_factor",
        "label": "Group grievances",
        "summary": "Shared perceptions of injustice, exclusion or relative deprivation that "
        "leaders mobilize around. Perceptions matter and are often missed by standard surveys.",
        "aliases": ["grievances", "sense of injustice", "relative deprivation"],
        "query": "collective grievances perceptions injustice relative deprivation mobilization",
    },
    {
        "id": "political-exclusion",
        "type": "risk_factor",
        "label": "Exclusion from power",
        "summary": "Groups shut out of political decision-making and representation, raising the "
        "payoff to contesting power violently.",
        "aliases": ["political marginalization"],
        "query": "exclusion from political power representation decision making marginalization",
    },
    {
        "id": "youth-economic-exclusion",
        "type": "risk_factor",
        "label": "Youth and economic exclusion",
        "summary": "Unemployment, blocked aspirations and lack of economic opportunity, "
        "especially for young people — a recruitment pool for armed and extremist groups.",
        "aliases": ["youth unemployment", "youth exclusion", "jobs"],
        "query": "youth aspirations exclusion unemployment economic opportunity recruitment",
    },
    {
        "id": "gender-inequality",
        "type": "risk_factor",
        "label": "Gender inequality",
        "summary": "Exclusion of women from political, economic and civic life; a societal "
        "cleavage the report links to conflict risk and to weaker peace agreements.",
        "query": "gender inequality women exclusion participation peace conflict risk",
    },
    {
        "id": "corruption",
        "type": "risk_factor",
        "label": "Corruption",
        "summary": "Capture of the state and its resources by narrow groups; erodes trust and "
        "legitimacy and channels grievances toward the state.",
        "query": "corruption state capture legitimacy trust institutions grievances",
    },
    {
        "id": "weak-state-legitimacy",
        "type": "risk_factor",
        "label": "Weak state legitimacy",
        "summary": "When people lose faith that institutions will protect them or treat them "
        "fairly, the incentives that hold violence in check weaken.",
        "aliases": ["political instability", "state fragility"],
        "query": "state legitimacy trust in institutions political stability fragility",
    },
    {
        "id": "natural-resource-dependence",
        "type": "risk_factor",
        "label": "Natural-resource dependence",
        "summary": "Heavy economic reliance on agriculture or extractives raises exposure to "
        "price shocks, climate stress and contestation over rents.",
        "query": "natural resource dependence extractives agriculture rents price shocks conflict",
    },
    {
        "id": "water-stress",
        "type": "risk_factor",
        "label": "Water stress",
        "summary": "Scarcity and competition over freshwater — across users (pastoralists vs. "
        "farmers) and across borders (riparian states).",
        "query": "water scarcity stress riparian transboundary competition farmers pastoralists",
    },
    {
        "id": "climate-hazards",
        "type": "risk_factor",
        "label": "Climate hazards",
        "summary": "Droughts, floods and slow-onset change that interact with exclusion and weak "
        "institutions to raise vulnerability to violence — e.g. the Lake Chad region.",
        "query": "climate change impacts drought Lake Chad shocks vulnerability to violence",
    },
    {
        "id": "economic-shocks",
        "type": "risk_factor",
        "label": "Economic shocks",
        "summary": "Sudden downturns, commodity-price collapses and fiscal crises that can "
        "accelerate the onset of conflict, especially where adjustment is delayed.",
        "query": "economic shocks commodity price fiscal crisis capital flight onset of violence",
    },
    {
        "id": "aid-dependence",
        "type": "risk_factor",
        "label": "Aid and financial dependence",
        "summary": "High reliance on ODA or volatile flows like remittances weakens state "
        "autonomy and exposes budgets to sudden stops.",
        "aliases": ["aid dependence", "remittance dependence"],
        "query": "aid dependence ODA volatility remittances fiscal space donor financing",
    },
    {
        "id": "service-delivery-gaps",
        "type": "risk_factor",
        "label": "Service-delivery gaps",
        "summary": "Unequal or failing basic services (health, education, water) that signal "
        "state absence or bias and deepen group grievances.",
        "query": "unequal basic services health education state absence grievances legitimacy",
    },
    {
        "id": "militarization",
        "type": "risk_factor",
        "label": "Large / abusive security forces",
        "summary": "Oversized security sectors, hard to demobilize, and security provision "
        "experienced as threat rather than protection.",
        "aliases": ["military size", "security force abuse"],
        "query": "large security forces military expenditure demobilization abuse public expenditure",
    },
    {
        "id": "forced-displacement",
        "type": "risk_factor",
        "label": "Forced displacement",
        "summary": "Refugees and IDPs at record numbers; both a consequence of conflict and a "
        "source of strain on host communities and services.",
        "query": "forced displacement refugees IDPs host communities strain Jordan Lebanon",
    },
    {
        "id": "regional-spillover",
        "type": "risk_factor",
        "label": "Neighbouring / regional conflict",
        "summary": "Conflict in bordering countries spreads arms, fighters, illicit trade and "
        "refugees across porous borders and peripheries.",
        "aliases": ["neighbouring conflict", "conflict contagion"],
        "query": "neighbouring conflict spillover borders arms trafficking regional contagion",
    },
    {
        "id": "transnational-organized-crime",
        "type": "risk_factor",
        "label": "Transnational organized crime",
        "summary": "Illicit markets in arms, drugs and people that finance armed groups and "
        "corrode institutions — a systemic, cross-border risk.",
        "query": "transnational organized crime illicit trafficking arms drugs finance armed groups",
    },
    {
        "id": "legacies-of-violence",
        "type": "risk_factor",
        "label": "Legacies of violence / conflict trap",
        "summary": "Past violence reconfigures incentives, institutions and social norms so that "
        "conflict sustains itself — recurrence risk is high for years after fighting stops.",
        "aliases": ["conflict trap", "conflict recurrence"],
        "query": "path dependency of violence conflict trap recurrence relapse war economy",
    },
    {
        "id": "identity-mobilization",
        "type": "risk_factor",
        "label": "Identity-based mobilization",
        "summary": "Elites constructing narratives around identity and difference to escalate "
        "and sustain conflict.",
        "query": "identity narratives mobilization to violence difference elites escalation",
    },
    # -- policy levers ------------------------------------------------
    {
        "id": "inclusive-power-sharing",
        "type": "policy_lever",
        "label": "Inclusive power-sharing",
        "summary": "Representative, institutionalized power-sharing (via constitutions, not ad "
        "hoc deals) that mitigates 'winner-takes-all' politics and reassures groups that lose "
        "elections.",
        "query": "inclusive power sharing arrangements constitutions winner takes all representation",
    },
    {
        "id": "decentralization",
        "type": "policy_lever",
        "label": "Decentralization and autonomy",
        "summary": "Devolving power or granting subnational autonomy to accommodate diversity "
        "and lower the stakes of national-level contestation.",
        "query": "decentralization devolution subnational autonomy accommodate diversity Indonesia",
    },
    {
        "id": "credible-elections",
        "type": "policy_lever",
        "label": "Credible electoral processes",
        "summary": "Independent electoral authorities, pre-election mediation and protection of "
        "the vote — especially for women and marginalized groups — to make elections a peaceful "
        "contest.",
        "query": "credible electoral authorities pre-election mediation protection of the vote",
    },
    {
        "id": "civil-society-space",
        "type": "policy_lever",
        "label": "Civil society space",
        "summary": "Preserving or opening space for a diverse civil society as a link to local "
        "constituencies and a moderating force.",
        "query": "civil society space engagement local constituencies moderating role",
    },
    {
        "id": "horizontal-inequality-monitoring",
        "type": "policy_lever",
        "label": "Monitoring horizontal inequalities",
        "summary": "Regular measurement of inequality between groups and regions across power, "
        "resources, services and security — built on SDG indicators (SDG 5, 10, 16).",
        "query": "monitor exclusion horizontal inequalities groups SDG indicators disaggregated",
    },
    {
        "id": "perception-monitoring",
        "type": "policy_lever",
        "label": "Perception and grievance monitoring",
        "summary": "High-frequency surveys, polling and focus groups to track how groups "
        "perceive risk, injustice and the state — with strong privacy safeguards.",
        "query": "monitor perceptions grievances high-frequency surveys polling safeguards",
    },
    {
        "id": "early-warning-systems",
        "type": "policy_lever",
        "label": "Early warning systems linked to action",
        "summary": "Shifting from early warning of violence to awareness of risk, with warning "
        "systems that monitor medium-term risk and are connected to resources and decisions.",
        "query": "early warning systems risk awareness linked to early action response regional",
    },
    {
        "id": "integrated-plans",
        "type": "policy_lever",
        "label": "Integrated peace and development plans",
        "summary": "Single planning frameworks aligned with the SDGs that bring poverty "
        "reduction, disaster risk, services and environment together to prioritize conflict risks.",
        "query": "integrated peace and development plans collective outcomes humanitarian development nexus",
    },
    {
        "id": "people-centered-services",
        "type": "policy_lever",
        "label": "People-centered service delivery",
        "summary": "Making people partners in the design and delivery of services — the *how* of "
        "engagement matters as much as the *what*, especially where state legitimacy is contested.",
        "query": "people-centered approach service delivery participation partners trust legitimacy",
    },
    {
        "id": "land-tenure-security",
        "type": "policy_lever",
        "label": "Land tenure security",
        "summary": "Recognizing and protecting a continuum of land rights, and local dispute "
        "resolution, to defuse tensions over land while longer-term reforms are trialed.",
        "query": "securing land rights tenure continuum local dispute resolution reforms",
    },
    {
        "id": "transboundary-water-cooperation",
        "type": "policy_lever",
        "label": "Transboundary water cooperation",
        "summary": "Negotiation and cooperation between riparian countries and subregions over "
        "shared water as a foundation for peaceful relations (e.g. EcoPeace Middle East).",
        "query": "cooperation over water riparian countries EcoPeace Middle East shared basins",
    },
    {
        "id": "fiscal-space",
        "type": "policy_lever",
        "label": "Fiscal space and domestic revenue",
        "summary": "Enough domestic revenue to pay civil servants — especially in security, "
        "justice and core services — so prevention is state-led and sustainable, not donor-driven.",
        "query": "fiscal dimensions of prevention domestic revenue civil servants core state functions",
    },
    {
        "id": "redistributive-social-protection",
        "type": "policy_lever",
        "label": "Redistributive social protection",
        "summary": "Fiscal, wage and social-protection policy aimed at reducing inequity between "
        "social groups — which also cushions shocks.",
        "query": "redistributive policies social protection reduce inequity between groups shocks",
    },
    {
        "id": "security-sector-reform",
        "type": "policy_lever",
        "label": "Security sector reform",
        "summary": "Making security a service to the population, with civilian oversight, "
        "inclusion and public-expenditure transparency; paired with social and economic support.",
        "query": "security sector reform civilian oversight inclusion service to population Burundi Timor",
    },
    {
        "id": "local-mediation",
        "type": "policy_lever",
        "label": "Local mediation & infrastructures for peace",
        "summary": "Peace committees, ombuds offices and national mediation capacity that "
        "resolve disputes locally before they escalate (Kenya, Ghana, Peru, Somaliland).",
        "query": "infrastructures for peace peace committees mediation capacity ombudsman local",
    },
    {
        "id": "ddr",
        "type": "policy_lever",
        "label": "Disarmament, demobilization & reintegration",
        "summary": "Demobilizing and reintegrating combatants after violence to break the "
        "conflict trap and prevent recurrence.",
        "query": "disarmament demobilization reintegration combatants recurrence post-conflict",
    },
    {
        "id": "target-periphery",
        "type": "policy_lever",
        "label": "Targeting border and periphery areas",
        "summary": "Directing services, investment and 'stability poles' to weakly governed "
        "border and low-density regions where risk concentrates.",
        "query": "target border and periphery areas stability poles weak state presence investment",
    },
    {
        "id": "women-youth-participation",
        "type": "policy_lever",
        "label": "Women's and youth participation",
        "summary": "Meaningful inclusion of women and young people in peace processes and "
        "decision-making — shown to make agreements more durable.",
        "query": "women's participation peace processes youth inclusion durable agreements leadership",
    },
    {
        "id": "adaptation-finance",
        "type": "policy_lever",
        "label": "Climate adaptation finance",
        "summary": "Development finance for climate adaptation in exposed, fragile settings — "
        "reducing the structural stress that interacts with exclusion.",
        "query": "climate adaptation finance fragile settings structural stress resilience",
    },
    # -- actors / stakeholders --------------------------------------
    {
        "id": "national-government",
        "type": "actor",
        "label": "National government",
        "summary": "The primary actor for prevention: the report stresses that effective "
        "prevention is nationally owned and led.",
        "query": "national actors ownership leadership prevention strategies from within societies",
    },
    {
        "id": "civil-society",
        "type": "actor",
        "label": "Civil society",
        "summary": "Community organizations, NGOs, media and movements — a link to local "
        "constituencies and a partner in monitoring and mediation.",
        "query": "civil society role prevention monitoring mediation local constituencies",
    },
    {
        "id": "private-sector",
        "type": "actor",
        "label": "Private sector",
        "summary": "Firms and investors that can moderate actors' behavior, sustain livelihoods "
        "and finance development in fragile settings.",
        "query": "private sector contributions peacebuilding investment jobs fragile settings",
    },
    {
        "id": "women",
        "type": "actor",
        "label": "Women",
        "summary": "Women's meaningful participation in peace and security is shown to improve "
        "the sustainability of agreements.",
        "query": "women's leadership peacebuilding participation peace and security agreements",
    },
    {
        "id": "youth",
        "type": "actor",
        "label": "Youth",
        "summary": "Young people and the movements and networks that represent them — central to "
        "sustaining peace.",
        "query": "youth participation organizations movements networks sustaining peace",
    },
    {
        "id": "regional-organizations",
        "type": "actor",
        "label": "Regional organizations",
        "summary": "Bodies such as the League of Arab States, the African Union and ECOWAS that "
        "run regional early warning and mediation and share prevention practice.",
        "query": "regional subregional organizations League of Arab States ECOWAS African Union prevention",
    },
    {
        "id": "un-wb-partnership",
        "type": "actor",
        "label": "UN – World Bank partnership",
        "summary": "The joint humanitarian–development–peace engagement behind Pathways for "
        "Peace, including work in Yemen and on the humanitarian–development nexus.",
        "query": "United Nations World Bank partnership Yemen humanitarian development peace nexus",
    },
    {
        "id": "development-actors",
        "type": "actor",
        "label": "Development actors",
        "summary": "Bilateral and multilateral development agencies and banks, urged to engage "
        "early on risk rather than withdraw as it rises.",
        "query": "development actors engage early on risk stay engaged financing prevention",
    },
]

# --------------------------------------------------------------------- edges
EDGES: list[dict] = [
    # pathway spine
    {"source": "actors", "target": "sustainable-peace", "rel": "drives", "note": "Actors' decisions ultimately define the pathway."},
    {"source": "institutions", "target": "sustainable-peace", "rel": "strengthens", "note": "Capable institutions contain violence and manage expectations."},
    {"source": "structural-factors", "target": "violent-conflict", "rel": "drives", "note": "Structural conditions set the environment in which actors choose."},
    {"source": "prevention", "target": "violent-conflict", "rel": "mitigates", "note": "Prevention addresses causes, escalation and recurrence."},
    {"source": "prevention", "target": "sustainable-peace", "rel": "strengthens"},
    {"source": "legacies-of-violence", "target": "institutions", "rel": "undermines", "note": "Protracted conflict reorients institutions around wartime dynamics."},

    # arenas sit within the governance/structural frame
    {"source": "arena-power-governance", "target": "institutions", "rel": "part_of"},
    {"source": "arena-land-resources", "target": "structural-factors", "rel": "part_of"},
    {"source": "arena-service-delivery", "target": "institutions", "rel": "part_of"},
    {"source": "arena-security-justice", "target": "institutions", "rel": "part_of"},

    # risk factors -> conflict
    {"source": "horizontal-inequality", "target": "violent-conflict", "rel": "drives", "note": "The report's central structural driver of modern conflict."},
    {"source": "group-grievances", "target": "violent-conflict", "rel": "drives"},
    {"source": "political-exclusion", "target": "violent-conflict", "rel": "drives"},
    {"source": "youth-economic-exclusion", "target": "violent-conflict", "rel": "drives"},
    {"source": "gender-inequality", "target": "violent-conflict", "rel": "drives"},
    {"source": "corruption", "target": "weak-state-legitimacy", "rel": "drives"},
    {"source": "weak-state-legitimacy", "target": "violent-conflict", "rel": "drives"},
    {"source": "natural-resource-dependence", "target": "economic-shocks", "rel": "drives"},
    {"source": "economic-shocks", "target": "violent-conflict", "rel": "drives"},
    {"source": "water-stress", "target": "violent-conflict", "rel": "drives"},
    {"source": "climate-hazards", "target": "water-stress", "rel": "drives"},
    {"source": "climate-hazards", "target": "violent-conflict", "rel": "drives"},
    {"source": "aid-dependence", "target": "weak-state-legitimacy", "rel": "drives"},
    {"source": "service-delivery-gaps", "target": "group-grievances", "rel": "drives"},
    {"source": "militarization", "target": "violent-conflict", "rel": "drives"},
    {"source": "forced-displacement", "target": "violent-conflict", "rel": "intersects"},
    {"source": "regional-spillover", "target": "violent-conflict", "rel": "drives"},
    {"source": "transnational-organized-crime", "target": "violent-conflict", "rel": "drives"},
    {"source": "transnational-organized-crime", "target": "institutions", "rel": "undermines"},
    {"source": "legacies-of-violence", "target": "violent-conflict", "rel": "drives"},
    {"source": "identity-mobilization", "target": "violent-conflict", "rel": "drives"},
    {"source": "identity-mobilization", "target": "group-grievances", "rel": "intersects"},

    # risk factors contested in arenas
    {"source": "political-exclusion", "target": "arena-power-governance", "rel": "contested_in"},
    {"source": "corruption", "target": "arena-power-governance", "rel": "contested_in"},
    {"source": "identity-mobilization", "target": "arena-power-governance", "rel": "contested_in"},
    {"source": "natural-resource-dependence", "target": "arena-land-resources", "rel": "contested_in"},
    {"source": "water-stress", "target": "arena-land-resources", "rel": "contested_in"},
    {"source": "climate-hazards", "target": "arena-land-resources", "rel": "contested_in"},
    {"source": "service-delivery-gaps", "target": "arena-service-delivery", "rel": "contested_in"},
    {"source": "youth-economic-exclusion", "target": "arena-service-delivery", "rel": "contested_in"},
    {"source": "militarization", "target": "arena-security-justice", "rel": "contested_in"},
    {"source": "forced-displacement", "target": "arena-service-delivery", "rel": "contested_in"},
    {"source": "horizontal-inequality", "target": "arena-power-governance", "rel": "contested_in"},
    {"source": "horizontal-inequality", "target": "arena-service-delivery", "rel": "contested_in"},
    {"source": "horizontal-inequality", "target": "arena-security-justice", "rel": "contested_in"},

    # grievance chain
    {"source": "horizontal-inequality", "target": "group-grievances", "rel": "drives"},
    {"source": "political-exclusion", "target": "group-grievances", "rel": "drives"},
    {"source": "gender-inequality", "target": "horizontal-inequality", "rel": "intersects"},
    {"source": "youth-economic-exclusion", "target": "horizontal-inequality", "rel": "intersects"},

    # policy levers -> mitigate risk factors
    {"source": "inclusive-power-sharing", "target": "political-exclusion", "rel": "mitigates"},
    {"source": "inclusive-power-sharing", "target": "arena-power-governance", "rel": "strengthens"},
    {"source": "decentralization", "target": "political-exclusion", "rel": "mitigates"},
    {"source": "decentralization", "target": "horizontal-inequality", "rel": "mitigates"},
    {"source": "credible-elections", "target": "arena-power-governance", "rel": "strengthens"},
    {"source": "credible-elections", "target": "identity-mobilization", "rel": "mitigates"},
    {"source": "civil-society-space", "target": "weak-state-legitimacy", "rel": "mitigates"},
    {"source": "civil-society-space", "target": "group-grievances", "rel": "mitigates"},
    {"source": "horizontal-inequality-monitoring", "target": "horizontal-inequality", "rel": "monitored_by"},
    {"source": "perception-monitoring", "target": "group-grievances", "rel": "monitored_by"},
    {"source": "early-warning-systems", "target": "regional-spillover", "rel": "mitigates"},
    {"source": "early-warning-systems", "target": "violent-conflict", "rel": "mitigates"},
    {"source": "integrated-plans", "target": "climate-hazards", "rel": "mitigates"},
    {"source": "integrated-plans", "target": "structural-factors", "rel": "strengthens"},
    {"source": "people-centered-services", "target": "service-delivery-gaps", "rel": "mitigates"},
    {"source": "people-centered-services", "target": "weak-state-legitimacy", "rel": "mitigates"},
    {"source": "land-tenure-security", "target": "arena-land-resources", "rel": "strengthens"},
    {"source": "land-tenure-security", "target": "natural-resource-dependence", "rel": "mitigates"},
    {"source": "transboundary-water-cooperation", "target": "water-stress", "rel": "mitigates"},
    {"source": "fiscal-space", "target": "aid-dependence", "rel": "mitigates"},
    {"source": "fiscal-space", "target": "prevention", "rel": "strengthens"},
    {"source": "redistributive-social-protection", "target": "horizontal-inequality", "rel": "mitigates"},
    {"source": "redistributive-social-protection", "target": "economic-shocks", "rel": "mitigates"},
    {"source": "security-sector-reform", "target": "militarization", "rel": "mitigates"},
    {"source": "security-sector-reform", "target": "arena-security-justice", "rel": "strengthens"},
    {"source": "local-mediation", "target": "group-grievances", "rel": "mitigates"},
    {"source": "local-mediation", "target": "institutions", "rel": "strengthens"},
    {"source": "ddr", "target": "legacies-of-violence", "rel": "mitigates"},
    {"source": "target-periphery", "target": "regional-spillover", "rel": "mitigates"},
    {"source": "target-periphery", "target": "service-delivery-gaps", "rel": "mitigates"},
    {"source": "women-youth-participation", "target": "gender-inequality", "rel": "mitigates"},
    {"source": "women-youth-participation", "target": "youth-economic-exclusion", "rel": "mitigates"},
    {"source": "adaptation-finance", "target": "climate-hazards", "rel": "mitigates"},

    # actors -> levers they carry
    {"source": "national-government", "target": "prevention", "rel": "drives", "note": "Prevention is nationally owned and led."},
    {"source": "national-government", "target": "fiscal-space", "rel": "strengthens"},
    {"source": "civil-society", "target": "perception-monitoring", "rel": "strengthens"},
    {"source": "civil-society", "target": "local-mediation", "rel": "strengthens"},
    {"source": "private-sector", "target": "youth-economic-exclusion", "rel": "mitigates"},
    {"source": "women", "target": "women-youth-participation", "rel": "strengthens"},
    {"source": "youth", "target": "women-youth-participation", "rel": "strengthens"},
    {"source": "regional-organizations", "target": "early-warning-systems", "rel": "strengthens"},
    {"source": "un-wb-partnership", "target": "integrated-plans", "rel": "strengthens"},
    {"source": "development-actors", "target": "adaptation-finance", "rel": "strengthens"},
    {"source": "development-actors", "target": "integrated-plans", "rel": "strengthens"},
]

# ---------------------------------------------------- indicator attachments
# Maps each Arab Risk Monitor indicator (id from etl/indicators.py) to the
# graph node it measures, and the relation to use. build_graph.py adds an
# `indicator` node per registry entry and an edge  node --measured_by--> indicator.
INDICATOR_LINKS: dict[str, str] = {
    "GOV_WGI_PV.EST": "weak-state-legitimacy",
    "MS.MIL.TOTL.TF.ZS": "militarization",
    "MS.MIL.XPND.GD.ZS": "militarization",
    "conflict_ucdp_battle_deaths": "violent-conflict",
    "conflict_ucdp_battle_deaths_total": "violent-conflict",
    "conflict_neighbor": "regional-spillover",
    "forced_displacement": "forced-displacement",
    "displacement_refugees_origin": "forced-displacement",
    "displacement_idps": "forced-displacement",
    "GOV_WGI_VA.EST": "political-exclusion",
    "NV.AGR.TOTL.ZS": "natural-resource-dependence",
    "ER.H2O.FWST.ZS": "water-stress",
    "climate_disaster_impact": "climate-hazards",
    "climate_adaptation_finance": "adaptation-finance",
    "BX.TRF.PWKR.DT.GD.ZS": "aid-dependence",
    "DT.ODA.ODAT.GN.ZS": "aid-dependence",
    "NY.GDP.PCAP.CD": "youth-economic-exclusion",
    "NY.GDP.MKTP.KD.ZG": "economic-shocks",
    "GC.TAX.TOTL.GD.ZS": "fiscal-space",
    "SL.UEM.TOTL.ZS": "youth-economic-exclusion",
    "SH.DYN.MORT": "service-delivery-gaps",
    "GOV_WGI_CC.EST": "corruption",
    "GOV_WGI_RL.EST": "arena-security-justice",
    "SP.POP.TOTL": "structural-factors",
}

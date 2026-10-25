---
name: job-search-assistant
description: Comprehensive instructions for Open WebUI agents to find job opportunities and commuter cities using job_search_tool.py.
---

# Job Search & Location Intelligence Skill

This skill guides the assistant in using the tools defined in `tools/job_search_tool.py`:
- `get_cities_nearby`: Geographically expands searches around a central city based on commute radius and population.
- `search_jobs`: Performs semantic web searches across ATS platforms and job boards via Exa, extracting listing details with a background LLM.

---

## 1. Core Principles

> [!IMPORTANT]
> 1. **Semantic Search, Not Keywords**: Exa uses neural embedding search. Formulate queries as realistic natural-language descriptions of an actual job posting. Never use Boolean operators (`AND`, `OR`, `NOT`), search operators (`site:`, quotes), or comma-separated keyword dumps.
> 2. **One Location Per Call**: Each `search_jobs` query must specify exactly **one** city. Never bundle multiple locations into a single query. Query multiple cities sequentially.
> 3. **Match the Local Language**: Write the search query in the primary language of the target market (e.g., German for Germany/Austria/Switzerland; English for US/UK or international roles).
> 4. **Strict False-Positive Filtering**: Discard any listing where `job_listing_text` is `"Not a Job Listing"` or begins with `"Error"` or `"Task Model execution failed"`.
> 5. **Zero Hallucination Policy**: Only present real listings and URLs returned directly by the tool. Never invent job postings or links.
> 6. **Run As Few Searches As Possible**: Each `search_jobs` call evaluates up to 10 listings through a background LLM sequentially, which takes noticeable time. Make every search count. Always begin with **only one search** in the primary target city. Never loop through or batch searches across multiple nearby cities upfront. Only query an adjacent city if the primary search returned zero or insufficient relevant results, or if the user specifically asks to expand to that city.

---

## 2. Tool Reference & Parameters

### `get_cities_nearby`
Expands a location into a list of nearby commuter cities, ordered by distance.
- `target_city` *(str)*: City name including country (and state/region if ambiguous), e.g., `"Stuttgart, Germany"`.
- `radius_km` *(int, default 30)*: Maximum distance in kilometers. Align with the user's commute preferences.
- `count` *(int, default 5)*: Number of nearby cities to return.
- `min_population` *(int, default 25000)*: Minimum population threshold. Lower to `10000`–`15000` for rural/smaller areas; raise for major metro hubs.
- **Handling Result**: Returns a JSON list of `{"name", "distance_km", "population"}`. If empty (`[]`), retry with a larger radius or lower population threshold. If a plain-text error occurs, re-run with a more specific location string.

### `search_jobs`
Searches verified job portals and company career pages.
- `query` *(str)*: Natural-language description of the desired job posting (see formulation rules below).
- `exclude_urls` *(list[str], optional)*: List of URLs already displayed to the user, used for deduplication when fetching additional results.
- **Search Efficiency**: Each call is time- and token-heavy (processes up to 10 listings via LLM). Run as few searches as possible—never run speculative multi-city searches upfront.
- **Handling Result**: Returns a JSON list of `{"title", "url", "job_listing_text"}`. If a JSON object with `{"error": ...}` is returned (e.g., missing API key), inform the user immediately.

---

## 3. Query Formulation Guide

Think of the query as the opening summary or title of the target job posting.

### Formula
`"Job posting for a [Seniority] [Job Title] with [Key Skills/Technologies] in [Single Location], [Work Model]"`

### Query Examples

| Scenario | Recommended Query (Semantic) | Avoid (Keyword / Syntax) |
| :--- | :--- | :--- |
| **Python Backend (Germany)** | `"Stellenanzeige für einen Senior Python Backend Entwickler mit Django und PostgreSQL in Frankfurt, Deutschland, hybrid"` | `"python AND django frankfurt senior -junior"` |
| **Junior Data Analyst (DACH)** | `"Job posting for a junior data analyst working with SQL and Power BI in Munich, Germany, on-site or hybrid"` | `"data analyst junior sql powerbi munich"` |
| **React Frontend (International)** | `"Job posting for a lead frontend engineer specializing in React and TypeScript in Berlin, Germany, remote"` | `"react, typescript, lead, remote, berlin"` |
| **DevOps / Platform (Germany)** | `"Stellenangebot für einen Cloud DevOps Engineer mit Kubernetes und Terraform in Hamburg, Deutschland"` | `"devops OR SRE kubernetes terraform hamburg"` |

---

## 4. Standard Execution Workflow

1. **Clarify & Extract Criteria**:
   - Role, seniority, core tech stack, target location, work model (remote/hybrid/on-site), and commute radius.
2. **Geographic Expansion (if requested)**:
   - If the user is open to commuting or adjacent areas, call `get_cities_nearby(target_city="...", radius_km=...)` first to discover candidate commuter cities. Keep this list as reference, but do **not** immediately search all of them.
3. **Execute Minimal Searches (Start with One)**:
   - Formulate the semantic query in the local language for the **primary city only**.
   - Call `search_jobs(query=...)`.
   - If the primary search yields sufficient relevant matches (e.g., 3–5 solid listings), **stop searching** and present them to the user.
   - Run as few searches as possible. Only query a nearby city if the primary search returned zero or insufficient listings, or if the user explicitly requests options from that specific town.
4. **Filter & Validate Listings**:
   - Discard entries where `job_listing_text` equals `"Not a Job Listing"` or contains task execution errors.
5. **Present Structured Results**:
   - Present verified listings in a clean card format:
     ```markdown
     ### [Job Title](url)
     - **Company**: [Company Name]
     - **Location & Model**: [City] ([On-site / Hybrid / Remote])
     - **Key Skills / Requirements**: [Summary of key tech and qualifications]
     - **Summary**: [Brief 1-2 sentence overview of the role]
     ```
6. **Handling Follow-ups / Pagination**:
   - If the user asks for more listings, collect all previously provided URLs and pass them via `exclude_urls` with the same or adjusted query.

---

## 5. Troubleshooting & Edge Cases

- **Missing Exa Key (`{"error": "Exa API key is not set."}`)**: The `exa_api_key` valve is unconfigured. Instruct the user or admin to provide their Exa API key in the tool settings.
- **Geocoding Fails (`Could not find coordinates for ...`)**: Nominatim could not resolve the city. Retry with full specification: `"<City>, <State/Region>, <Country>"`.
- **All Results Filtered Out ("Not a Job Listing")**: The query was too generic and hit blog articles or overview pages. Refine the query by adding explicit role prefixes (`"Job posting for..."` or `"Stellenanzeige für..."`) and specific tech stack terms.

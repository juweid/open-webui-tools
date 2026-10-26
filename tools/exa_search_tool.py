"""
title: Exa Search Tool
description: Search the web using Exa's search API.
author: jweid
version: 0.1.0
requirements: exa-py==2.26.0
"""

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional
from pydantic import BaseModel, Field
from dataclasses import asdict

from exa_py import Exa
from exa_py.api import DYNAMIC_HIGHLIGHTS_BETA

from open_webui.models.users import Users


class Tools:
    """Open WebUI tools for searching the web.
    """

    class Valves(BaseModel):
        """Admin-configurable settings for the toolkit.
        :ivar exa_api_key: API key for the Exa search API. ``exa_search`` returns an
            error if this is empty.
        """
        exa_api_key: str = Field(
            default="",
            description="API key for the Exa web search API. Required for web search functionality.",
            json_schema_extra={"input": {"type": "password"}}
        )

    def __init__(self):
        """Create the toolkit with default valves 
        """
        self.valves = self.Valves()
    
    async def exa_search(
        self,
        query: str,
        objective: str,
        category: Optional[str] = None,
        exclude_domains: Optional[list[str]] = None,
        include_domains: Optional[list[str]] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        live_fetch: bool = False,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __user__: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Search the web in natural language and retrieve relevant excerpts from top
        pages. Use this tool for current information, documentation, research papers,
        news, companies, or people. Keep optional filters unset (None) unless results
        outside those hard constraints would be unusable. Express soft source or
        recency preferences in ``query`` and ``objective`` instead.

        :param query: Natural-language description of the ideal webpage, not a list
                of keywords (e.g., "technical blog post comparing hybrid and semantic RAG
                retrieval", not "hybrid vs semantic RAG"). Include the subject, source
                type, and time period when relevant. Do not use ``site:`` operators; use
                ``include_domains`` or ``exclude_domains`` instead.
        :param objective: Goal for this search. Specify which documents should rank
                first, which to exclude, and which facts or figures to extract.
        :param category: Optional specialized search index. Leave unset for general
                web search, technical documentation, forums, or mixed queries. Supported
                values are:

                * ``company`` — Company homepages and corporate profiles with structured
                    data such as headcount, funding, headquarters, and financials. Use to
                    discover or profile organizations, not to find news about them.
                * ``people`` — Professional profiles, researcher pages, and bios searchable
                    by role, skill, location, or company.
                * ``publication`` — Academic papers, preprints (arXiv, bioRxiv), patents,
                    grants, clinical trials, and regulatory approvals.
                * ``news`` — Mainstream and trade press articles; pair with
                    ``start_published_date`` for recent events.
                * ``financial report`` — Formal regulatory filings (10-K, 10-Q, 8-K) and
                    annual reports. Leave unset for live prices or general financial news.
                * ``personal site`` — Independent blogs, developer portfolios, and
                    personal write-ups without corporate SEO noise.
                * ``github`` — Code repositories, issue trackers, and documentation
                    for open-source projects.

                **Constraints:** For ``company`` and ``people``, both publication date
                filters must be unset. For ``people``, ``exclude_domains`` must also be
                unset. Violating these constraints causes an API 400 error.
        :param exclude_domains: Optional hostnames, path prefixes, or wildcard
                subdomains to block (e.g., ["reddit.com", "example.com/forum",
                "*.substack.com"]). Do not use with the ``people`` category.
        :param include_domains: Optional hostnames, path prefixes, or wildcard
                subdomains that results must come from (e.g., ["exa.ai", "arxiv.org"]).
                Use only when restricting results to known domains is necessary.
        :param start_published_date: Optional ISO 8601 datetime string (e.g.,
                "2026-01-01T00:00:00Z"). Restricts results to pages published after this
                date. Do not use with ``company`` or ``people``, or to check for updates
                to older pages; use ``live_fetch`` for page freshness.
        :param end_published_date: Optional ISO 8601 datetime string (e.g.,
                "2026-10-26T23:59:59Z"). Restricts results to pages published before this
                date. Do not use with ``company`` or ``people``.
        :param live_fetch: Set to True only for rapidly changing pages where cached
                data may be inaccurate, such as live pricing, stock quotes, status pages,
                or breaking events. Defaults to False for faster cached retrieval.
        :return: Structured JSON results with titles, URLs, publication dates,
                relevant highlights and entities for certain types of searches. On error, returns a JSON object with an ``error``
                key and a descriptive message.
        """
    
        async def emit_status(description: str, done: bool = False):
            """Emit a status event to the Open WebUI client if an event emitter is configured."""
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": description, "done": done},
                        "hidden": False
                    }
                )
        
        if not self.valves.exa_api_key:
            return json.dumps({"error": "Exa API key is not set."})
        
        if not __user__ or "id" not in __user__:
            return json.dumps({"error": "Injected user context is missing."})
        
        user_id = __user__["id"]
        user_object = await Users.get_user_by_id(user_id)
        if not user_object:
            return json.dumps({"error": "Active user verification failed."})
        
        exa = Exa(api_key=self.valves.exa_api_key)

        await emit_status(f"Searching with query: {query}...")
    
        
        include_domains = include_domains or []
        exclude_domains = exclude_domains if category not in ["people"] else None
        search_type = "auto" if live_fetch else "lite" # lite can not be used with live_fetch
        contents = {
            "highlights": { "dynamic": True },
        }
        if live_fetch:
            contents["max_age_hours"] = 0  # Force live fetch if requested
        num_results = 5
        category = category or None
        start_published_date = start_published_date if category not in ["people", "company"] else None
        end_published_date = end_published_date if category not in ["people", "company"] else None
        
        
        try:
            response = await asyncio.to_thread(
                exa.search,
                query=query,
                objective=objective,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                type=search_type,
                contents=contents,
                num_results=num_results,
                user_identifier=user_id,
                start_published_date=start_published_date,
                end_published_date=end_published_date,
                betas=[DYNAMIC_HIGHLIGHTS_BETA],
            )
        except Exception as e:
            await emit_status(f"Exa search failed: {e}", done=True)
            return json.dumps({"error": f"Exa search failed: {str(e)}"})



        processed_results = []
        for r in response.results:
            item = {
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
                "highlights": "".join(r.highlights),
            }
            if getattr(r, "entities", None) and category in ["company", "people"]:
                item["entities"] = [asdict(e) for e in r.entities]
            processed_results.append(item)
        
        output = {
            "type": "exa_search_results",
            "search_query": query,
            "search_results": processed_results
        }

        return json.dumps(output, ensure_ascii=False)
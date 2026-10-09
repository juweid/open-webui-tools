"""
title: Job Search & Nearby Cities
description: Search for job listings using Exa and find cities near a target location using Nominatim geocoding and geonamescache.
author: jweid
version: 0.1.0
requirements: geonamescache, geopy, exa-py
"""

import asyncio
import json
import math
from typing import Any, Awaitable, Callable, Dict, Optional

import geonamescache
from geopy.geocoders import Nominatim

from exa_py import Exa

from fastapi import Request
from pydantic import BaseModel, Field

from open_webui.utils.chat import generate_chat_completion
from open_webui.models.users import Users

EARTH_RADIUS_KM = 6371.0088

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two geographic coordinates in kilometers.

    Uses the Haversine formula assuming a spherical Earth.

    :param lat1: Latitude of the first point in decimal degrees.
    :param lon1: Longitude of the first point in decimal degrees.
    :param lat2: Latitude of the second point in decimal degrees.
    :param lon2: Longitude of the second point in decimal degrees.
    :return: Distance between the two coordinates in kilometers.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class Tools:
    """Open WebUI tools for finding job listings in a city and its surrounding area.
    """

    class Valves(BaseModel):
        """Admin-configurable settings for the toolkit.

        :ivar nominatim_user_agent: User agent string sent to the Nominatim geocoding
            service, as required by its usage policy.
        :ivar dataset_min_population: Population threshold selecting which
            geonamescache city dataset to load. Must be one of 500, 1000, 5000 or 15000.
        :ivar exa_api_key: API key for the Exa search API. ``search_jobs`` returns an
            error if this is empty.
        """

        nominatim_user_agent: str = Field(
            default="city_finder_tool",
            description="User agent sent to the Nominatim geocoding service (required by its usage policy).",
        )
        dataset_min_population: int = Field(
            default=15000,
            description="geonamescache dataset to search (500, 1000, 5000 or 15000). Smaller values include more, smaller cities.",
        )
        exa_api_key: str = Field(
            default="",
            description="API key for the Exa job search API. Required for job search functionality.",
            json_schema_extra={"input": {"type": "password"}}
        )
        job_sites: list[str] = Field(
            default=["stepstone.de"],
            description="List of urls to include in the job search.",
            json_schema_extra={
                "input": {
                    "type": "multiselect",
                    "options": [
                        {"value": "stepstone.de", "label": "StepStone (Germany)"},
                        {"value": "devjobs.de", "label": "Devjobs (Germany)"},
                        {"value": "get-in-it.de", "label": "Get in IT (Germany)"},
                        {"value": "*.personio.de", "label": "Personio (Germany)"},
                        {"value": "*.personio.com", "label": "Personio"},
                        {
                            "value": "jobs.softgarden.de",
                            "label": "Softgarden (Germany)",
                        },
                        {"value": "*.softgarden.io", "label": "Softgarden"},
                        {"value": "*.teamtailor.com", "label": "Teamtailor"},
                        {"value": "*.recruitee.com", "label": "Recruitee"},
                        {"value": "smartrecruiters.com", "label": "SmartRecruiters"},
                        {"value": "*.dvinci-hr.com", "label": "d.vinci"},
                        {
                            "value": "finest-jobs.com",
                            "label": "Rexx Systems",
                        },
                        {
                            "value": "job-boards.greenhouse.io",
                            "label": "Greenhouse",
                        },
                        {"value": "jobs.lever.co", "label": "Lever"},
                    ],
                }
            },
        )

    def __init__(self):
        """Create the toolkit with default valves and an empty city cache.

        The city dataset is loaded lazily on first use by :meth:`_get_cities`.
        ``_cities`` holds the cached records and ``_cities_dataset`` records the
        ``dataset_min_population`` value they were loaded with.
        """
        self.valves = self.Valves()
        self._cities = None
        self._cities_dataset = None

    def _get_cities(self) -> dict:
        """Return the geonamescache city records, loading them on first use.

        The dataset is cached on the instance and reloaded only when the
        ``dataset_min_population`` valve differs from the value the cache was built with.
        This call is blocking and should be run in a worker thread from async code.

        :return: A dictionary mapping GeoNames IDs to city records. Each record contains
            at least ``name``, ``latitude``, ``longitude`` and ``population``.
        """
        if (
            self._cities is None
            or self._cities_dataset != self.valves.dataset_min_population
        ):
            self._cities = geonamescache.GeonamesCache(
                min_city_population=self.valves.dataset_min_population
            ).get_cities()
            self._cities_dataset = self.valves.dataset_min_population
        return self._cities

    async def get_cities_nearby(
        self,
        target_city: str,
        radius_km: int = 30,
        count: int = 5,
        min_population: int = 25000,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """Find cities near a given city, sorted by distance (closest first).

        Returns a JSON list of {name, distance_km, population}. The target city itself
        is usually included at ~0 km. An empty list means nothing matched: retry with a
        larger radius_km or a lower min_population. A plain-text message means the city
        could not be found: retry with a more specific name (add region or country).

        :param target_city: City name including the country, e.g. "Munich, Germany". Add the region if the name is ambiguous.
        :param radius_km: Search radius in km. Use the user's stated commute distance if given; otherwise keep the default of 30.
        :param count: Maximum number of cities to return. Default is 5.
        :param min_population: Only include cities with at least this many inhabitants. Lower it (e.g. 15000) to include smaller towns; raise it to get only larger cities. Default is 25000.
        :return: JSON list of nearby cities, or a plain-text error message.
        """

        async def emit_status(description: str, done: bool = False):
            """Emit a status event to the Open WebUI client if an event emitter is configured."""
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": description, "done": done},
                    }
                )

        await emit_status(f"Looking up coordinates for {target_city}...")

        # geopy and geonamescache are blocking, so run them in a worker thread
        geolocator = Nominatim(user_agent=self.valves.nominatim_user_agent)
        try:
            location = await asyncio.to_thread(geolocator.geocode, target_city)
        except Exception as e:
            await emit_status(f"Geocoding failed: {e}", done=True)
            return f"Geocoding failed for {target_city}: {e}"

        if not location:
            await emit_status(f"Could not find {target_city}", done=True)
            return f"Could not find coordinates for {target_city}"

        lat, lng = location.latitude, location.longitude

        await emit_status(
            f"Searching cities within {radius_km} km of {location.address}..."
        )
        cities = await asyncio.to_thread(self._get_cities)

        nearby = []
        for place in cities.values():
            population = place.get("population", 0)
            if population < min_population:
                continue
            distance = _haversine_km(lat, lng, place["latitude"], place["longitude"])
            if distance <= radius_km:
                nearby.append((distance, place))

        # Sort all matching cities by distance and return the closest `count`
        nearby.sort(key=lambda item: item[0])

        result = [
            {
                "name": place.get("name"),
                "distance_km": round(distance, 2),
                "population": place.get("population", 0),
            }
            for distance, place in nearby[:count]
        ]

        await emit_status(f"Found {len(result)} cities near {target_city}", done=True)
        return json.dumps(result, ensure_ascii=False)
    
    async def search_jobs(
        self,
        query: str,
        exclude_urls: Optional[list[str]] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __model__: Dict[str, Any] = None,
        __request__: Request = None,
        __user__: Dict[str, Any] = None,
    ) -> str:
        """Search the web for current job listings and get a summary of each one.

        Use this whenever the user wants to find jobs. Each call returns up to 10
        listings and takes a while, so make each query count.

        How to write the query (IMPORTANT):
        This tool uses SEMANTIC search via Exa, not keyword search. Write the query as a
        natural-language description of the job posting you want to find. Do not use
        keyword lists, boolean operators (AND/OR/NOT), quotes, or minus signs. Include
        role, seniority, key skills, exactly ONE location, and work model (remote/hybrid/on-site)
        when known. Because of semantic search, queries written like an actual job listing 
        will return better results than keyword lists. Dont make the query too long, keep it fairly short and concise. The model will try to find the most relevant job listings based on your description.
        Seek in the language of the target location, e.g., German for Germany, English for the US. If you want to find jobs in multiple locations, call this tool once per location.

        Good: "Job posting for a senior Python backend developer working with Django in Frankfurt, Germany, hybrid"
        Bad: "python AND django frankfurt senior -junior"

        Workflow:
        1. If the user is open to jobs around a city, call `get_cities_nearby` first.
        2. Call this tool once per location (the target city plus each nearby city). Only do 
        one search at a time.
        3. Present only real job listings, each with its url.
        4. If the user wants more results, call again with the same query and pass the
        urls you already have in exclude_urls.

        Example: "I'm a junior data analyst looking for jobs around Stuttgart, max 40 km commute."
        1. get_cities_nearby(target_city="Stuttgart, Germany", radius_km=40)
        -> ["Stuttgart, Germany", "Esslingen am Neckar, Germany", "Ludwigsburg, Germany"]
        2. search_jobs(query="Job posting for a junior data analyst position in Stuttgart, Germany")
        3. search_jobs(query="Job posting for a junior data analyst position in Esslingen am Neckar, Germany")
        4. Summarize the matching listings with title, company, location, and url.

        Handling the result:
        Returns a JSON list of {title, url, job_listing_text}. Skip entries whose
        job_listing_text is "Not a Job Listing" or starts with "Error" or "Task Model
        execution failed". Never invent listings or urls. If the result is a JSON object
        with an "error" key, the tool is misconfigured; tell the user instead of retrying.

        :param query: Semantic search query: a natural-language description of the wanted job posting, including role, seniority, skills, work model, and exactly one location, e.g., "Job posting for a senior Python backend developer in Frankfurt, Germany, hybrid".
        :param exclude_urls: Urls from earlier results that should not be returned again. Pass them when the user asks for more or different results.
        :return: JSON list of job listings, or an error message.
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
        
        task_model_id = __model__.get("id")
        if not task_model_id:
            return "Error: Could not resolve background Task Model ID."
        
        if not self.valves.exa_api_key:
            return json.dumps({"error": "Exa API key is not set."})
        
        if not __user__ or "id" not in __user__:
            return json.dumps({"error": "Injected user context is missing."})
        
        user_object = await Users.get_user_by_id(__user__["id"])
        if not user_object:
            return json.dumps({"error": "Active user verification failed."})
        
        exa = Exa(api_key=self.valves.exa_api_key)

        await emit_status(f"Searching for jobs with query: {query}...")
        
        include_domains = self.valves.job_sites or []
        exclude_domains = exclude_urls or []
        type = "fast"
        contents = {
            "text": True,
            "max_age_hours": 0
        }
        num_results = 10
        
        response = await asyncio.to_thread(
            exa.search,
            query=query,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            type=type,
            contents=contents,
            num_results=num_results
        )
        
        await emit_status(f"Processing {len(response.results)} job search results...")
        
        processed_results = []
        for i, result in enumerate(response.results):
            await emit_status(f"Processing job listing {i+1}/{len(response.results)}: {result.title}...")
            body = {
                "model": task_model_id,
                "messages": [
                    {
                        "role": "system", 
                        "content": "Extract relevant information from the job listing text." +
                        "Return only 'Not a Job Listing' if the text does not appear to be a SINGLE job listing." + 
                        "The page has to be a single job listing! Always include the name of the location," + 
                        "if it says 'remote' or 'home office' or 'nationwide' or 'anywhere' add the requested location name."
                    },
                    {"role": "user", "content": f"Potential Job listing: {result.text}"},
                ],
                "stream": False,
            }
        
            try:
                task_response = await generate_chat_completion(__request__, body, user_object)
                
                if isinstance(task_response, dict) and "choices" in task_response:
                    if len(task_response["choices"]) > 0:
                        processed_text = task_response["choices"][0]["message"]["content"]
                    else:
                        processed_text = "Error: Model returned an empty choices list."
                else:
                    processed_text = "Error: Unexpected response format from the model."
            except Exception as e:
                processed_text = f"Task Model execution failed. Error: {str(e)}"
            
            processed_results.append({
                "title": result.title,
                "url": result.url,
                "job_listing_text": processed_text,
            })
            
        await emit_status(f"Found {len(processed_results)} job results.", done=True)

        return json.dumps(processed_results, ensure_ascii=False)
    
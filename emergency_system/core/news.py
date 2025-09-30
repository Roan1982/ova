"""Utilities for fetching real RSS news headlines and current weather.

Designed to be lightweight: pure stdlib + optional feedparser.
If feedparser is missing, a very naive XML fallback parser is used.

Environment variables (define in .env or settings):

NEWS_FEEDS            Comma separated list of RSS/Atom feed URLs.
NEWS_KEYWORDS         (Optional) Comma separated filter keywords (case-insensitive, Spanish/English) - if set only headlines containing one of them are kept.
NEWS_CACHE_SECONDS    Cache TTL for news (default 300 seconds).
WEATHER_API_KEY       OpenWeatherMap API key.
WEATHER_LAT           Latitude for weather (default -34.6037 for CABA Obelisco).
WEATHER_LON           Longitude for weather (default -58.3816).
WEATHER_CACHE_SECONDS Cache TTL for weather (default 600 seconds).

Context objects returned:
news_items: list[{
  'title': str,
  'source': str,
  'published': datetime|None (aware),
  'published_display': str,
  'link': str,
}]

weather: {
  'temp': float,
  'temp_feels': float,
  'humidity': int,
  'pressure': int,
  'condition': str,
  'icon': str (openweathermap icon code),
  'icon_url': str,
  'wind_kmh': float,
  'updated_at': datetime (aware),
  'updated_display': str,
  'source': 'OpenWeatherMap'
}
"""
from __future__ import annotations
import os
import time
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

import requests
from django.utils import timezone as dj_tz
from django.conf import settings

logger = logging.getLogger(__name__)

# Optional feedparser
try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except Exception:  # pragma: no cover - defensive
    feedparser = None
    _HAS_FEEDPARSER = False

_NEWS_CACHE: Dict[str, Any] = {
    'timestamp': 0.0,
    'items': []
}
_WEATHER_CACHE: Dict[str, Any] = {
    'timestamp': 0.0,
    'data': None
}

DEFAULT_NEWS_FEEDS = [
    # Some Argentine / international emergency relevant feeds (can be overridden)
    'https://www.telam.com.ar/rss2/policiales.xml',
    'https://www.infobae.com/feeds/policiales.xml',
    'https://rss.clarin.com/rss/policiales/',
]

HEADLINE_CLEAN_RE = re.compile(r'\s+')

# Palabras clave y pesos para severidad de titulares
SEVERITY_KEYWORDS: List[Tuple[str, int]] = [
    ('incend', 5), ('explosi', 6), ('choque', 4), ('accident', 4),
    ('fatal', 7), ('herido', 5), ('rescate', 3), ('evacuac', 6),
    ('colapso', 5), ('derrum', 6), ('tirote', 7), ('bala', 5),
    ('fuego', 4), ('urgente', 5), ('emergenc', 4)
]

def classify_headline_severity(title: str) -> Dict[str, Any]:
    lt = title.lower()
    score = 0
    for kw, weight in SEVERITY_KEYWORDS:
        if kw in lt:
            score += weight
    if score >= 12:
        level = 'alta'; color = '#dc2626'; label = 'Alta'
    elif score >= 6:
        level = 'media'; color = '#f59e0b'; label = 'Media'
    else:
        level = 'baja'; color = '#3b82f6'; label = 'Baja'
    return {
        'severity': level,
        'severity_color': color,
        'severity_label': label,
        'severity_score': score
    }


def _get_env_list(name: str, default_list: list[str]) -> list[str]:
    raw = getattr(settings, name, None) or os.getenv(name)
    if not raw:
        return default_list
    return [u.strip() for u in raw.split(',') if u.strip()]


def _get_env_int(name: str, default_val: int) -> int:
    raw = getattr(settings, name, None) or os.getenv(name)
    if not raw:
        return default_val
    try:
        return max(10, int(raw))
    except ValueError:
        return default_val


def _filter_keywords(title: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lt = title.lower()
    return any(k.lower() in lt for k in keywords)


def _parse_datetime(entry) -> datetime | None:
    for key in ('published_parsed', 'updated_parsed', 'created_parsed'):
        dt_struct = getattr(entry, key, None) or entry.get(key) if isinstance(entry, dict) else None
        if dt_struct:
            try:
                # feedparser returns time.struct_time
                return datetime(*dt_struct[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _fallback_parse_rss(url: str) -> list[dict]:  # Very naive fallback
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return []
        text = resp.text
        # Extract <item><title>...</title><link>...</link>
        items = []
        for m in re.finditer(r'<item>(.*?)</item>', text, re.DOTALL | re.IGNORECASE):
            block = m.group(1)
            t_match = re.search(r'<title>(.*?)</title>', block, re.IGNORECASE | re.DOTALL)
            l_match = re.search(r'<link>(.*?)</link>', block, re.IGNORECASE | re.DOTALL)
            if not t_match:
                continue
            title = re.sub(r'<.*?>', '', t_match.group(1)).strip()
            link = l_match.group(1).strip() if l_match else ''
            items.append({
                'title': title,
                'link': link,
                'published_dt': None,
                'published_display': '',
                'source': url.split('/')[2]
            })
            if len(items) >= 5:
                break
        return items
    except Exception:
        return []


def get_latest_news(limit: int = 12) -> List[Dict[str, Any]]:
    ttl = _get_env_int('NEWS_CACHE_SECONDS', 300)
    now = time.time()
    if now - _NEWS_CACHE['timestamp'] < ttl and _NEWS_CACHE['items']:
        return _NEWS_CACHE['items'][:limit]

    feeds = _get_env_list('NEWS_FEEDS', DEFAULT_NEWS_FEEDS)
    keywords = _get_env_list('NEWS_KEYWORDS', [])

    collected: List[Dict[str, Any]] = []

    for url in feeds[:6]:  # safety cap
        try:
            if _HAS_FEEDPARSER:
                parsed = feedparser.parse(url)
                for e in parsed.entries[:8]:
                    title_raw = getattr(e, 'title', '') or e.get('title', '') if isinstance(e, dict) else ''
                    title = HEADLINE_CLEAN_RE.sub(' ', title_raw).strip()
                    if not title or not _filter_keywords(title, keywords):
                        continue
                    published_dt = _parse_datetime(e)
                    published_display = ''
                    if published_dt:
                        published_display = dj_tz.localtime(published_dt).strftime('%H:%M') if published_dt.tzinfo else published_dt.strftime('%H:%M')
                    link = getattr(e, 'link', '') or e.get('link', '') if isinstance(e, dict) else ''
                    source = parsed.feed.get('title') if hasattr(parsed, 'feed') else url.split('/')[2]
                    sev = classify_headline_severity(title)
                    collected.append({
                        'title': title[:220],
                        'source': source[:60] if source else url.split('/')[2],
                        'published': published_dt,
                        'published_display': published_display,
                        'link': link,
                        **sev,
                    })
            else:  # fallback
                fallback_items = _fallback_parse_rss(url)
                for item in fallback_items:
                    sev = classify_headline_severity(item['title'])
                    item.update(sev)
                collected.extend(fallback_items)
        except Exception as e:  # pragma: no cover
            logger.warning("Error parsing feed %s: %s", url, e)
            continue

    # Sort by published desc if available
    collected.sort(key=lambda x: x.get('published') or datetime(1970,1,1, tzinfo=timezone.utc), reverse=True)
    # De-duplicate by title
    seen = set()
    unique = []
    for item in collected:
        t = item['title']
        if t in seen:
            continue
        seen.add(t)
        unique.append(item)
        if len(unique) >= limit:
            break

    _NEWS_CACHE['timestamp'] = now
    _NEWS_CACHE['items'] = unique
    return unique


def get_weather_status() -> Dict[str, Any] | None:
    ttl = _get_env_int('WEATHER_CACHE_SECONDS', 600)
    now = time.time()
    if now - _WEATHER_CACHE['timestamp'] < ttl and _WEATHER_CACHE['data']:
        return _WEATHER_CACHE['data']

    api_key = getattr(settings, 'WEATHER_API_KEY', None) or os.getenv('WEATHER_API_KEY')
    lat = getattr(settings, 'WEATHER_LAT', None) or os.getenv('WEATHER_LAT') or '-34.6037'
    lon = getattr(settings, 'WEATHER_LON', None) or os.getenv('WEATHER_LON') or '-58.3816'

    if not api_key:
        # Fallback: Open-Meteo (sin API key) + próximas 6 horas de temperatura
        om_url = (
            "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current_weather=true&timezone=auto&hourly=temperature_2m,relativehumidity_2m,pressure_msl"
        ).format(lat=lat, lon=lon)
        try:
            resp = requests.get(om_url, timeout=8)
            if resp.status_code != 200:
                logger.warning("Open-Meteo non-200: %s", resp.status_code)
                return None
            data = resp.json()
            cw = data.get('current_weather') or {}
            humidity = None
            pressure = None
            # Try to map humidity/pressure from hourly arrays at current time
            forecast_hours = []
            if 'hourly' in data and 'time' in data['hourly']:
                try:
                    times = data['hourly']['time']
                    rh = data['hourly'].get('relativehumidity_2m') or []
                    pm = data['hourly'].get('pressure_msl') or []
                    temps = data['hourly'].get('temperature_2m') or []
                    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:00')
                    if now_iso in times:
                        idx = times.index(now_iso)
                        if idx < len(rh):
                            humidity = rh[idx]
                        if idx < len(pm):
                            pressure = pm[idx]
                    try:
                        current_index = times.index(now_iso)
                    except ValueError:
                        current_index = 0
                    for offset in range(1, 7):
                        idx2 = current_index + offset
                        if idx2 < len(times):
                            hour_label = times[idx2].split('T')[1][:5]
                            temp_val = temps[idx2] if idx2 < len(temps) else None
                            forecast_hours.append({'time': hour_label, 'temp': temp_val})
                except Exception:
                    pass
            updated = dj_tz.now()
            weather = {
                'temp': cw.get('temperature'),
                'temp_feels': cw.get('temperature'),
                'humidity': humidity,
                'pressure': pressure,
                'condition': f"Viento {cw.get('windspeed','')} km/h" if cw else 'Sin datos',
                'icon': None,
                'icon_url': '',
                'wind_kmh': cw.get('windspeed'),
                'updated_at': updated,
                'updated_display': updated.strftime('%H:%M'),
                'source': 'Open-Meteo',
                'forecast_hours': forecast_hours,
            }
            _WEATHER_CACHE['timestamp'] = now
            _WEATHER_CACHE['data'] = weather
            return weather
        except Exception as e:  # pragma: no cover
            logger.warning("Open-Meteo fetch error: %s", e)
            return None

    # Primary: OpenWeatherMap con API key
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=es"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            logger.warning("Weather API non-200: %s", resp.status_code)
            return None
        data = resp.json()
        main = data.get('main') or {}
        weather_arr = data.get('weather') or []
        w0 = weather_arr[0] if weather_arr else {}
        wind = data.get('wind') or {}
        updated = dj_tz.now()
        # Añadir forecast desde Open-Meteo aunque use OpenWeatherMap para datos actuales
        forecast_hours: List[Dict[str, Any]] = []
        try:
            fm_url = (
                "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                "&timezone=auto&hourly=temperature_2m&forecast_days=1"
            ).format(lat=lat, lon=lon)
            fm_resp = requests.get(fm_url, timeout=6)
            if fm_resp.status_code == 200:
                fdata = fm_resp.json()
                times = fdata.get('hourly', {}).get('time', [])
                temps = fdata.get('hourly', {}).get('temperature_2m', [])
                now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:00')
                try:
                    current_index = times.index(now_iso)
                except ValueError:
                    current_index = 0
                for offset in range(1, 7):
                    idx = current_index + offset
                    if idx < len(times):
                        hour_label = times[idx].split('T')[1][:5]
                        forecast_hours.append({'time': hour_label, 'temp': temps[idx] if idx < len(temps) else None})
        except Exception:
            pass

        weather = {
            'temp': round(main.get('temp'), 1) if main.get('temp') is not None else None,
            'temp_feels': round(main.get('feels_like'), 1) if main.get('feels_like') is not None else None,
            'humidity': main.get('humidity'),
            'pressure': main.get('pressure'),
            'condition': w0.get('description', '').capitalize(),
            'icon': w0.get('icon'),
            'icon_url': f"https://openweathermap.org/img/wn/{w0.get('icon')}@2x.png" if w0.get('icon') else '',
            'wind_kmh': round((wind.get('speed') or 0) * 3.6, 1),
            'updated_at': updated,
            'updated_display': updated.strftime('%H:%M'),
            'source': 'OpenWeatherMap',
            'forecast_hours': forecast_hours,
        }
        _WEATHER_CACHE['timestamp'] = now
        _WEATHER_CACHE['data'] = weather
        return weather
    except Exception as e:  # pragma: no cover
        logger.warning("Weather fetch error: %s", e)
        return None

#############################
# Incidents / Traffic Feeds #
#############################

# Additional feeds specifically focused on traffic / incidents / emergency operations.
# Configurable by env var INCIDENT_FEEDS (comma separated). If not provided, we will
# reuse NEWS_FEEDS plus a minimal default list.
DEFAULT_INCIDENT_FEEDS = [
    'https://www.telam.com.ar/rss2/sociedad.xml',  # suele incluir choques / tránsito
    'https://www.cronista.com/files/rss/section/sociedad.xml',
]

# Basic keyword buckets for categorization; can be extended.
CATEGORY_KEYWORDS = {
    'accidente': ['accidente', 'choque', 'colisión', 'colision', 'vuelco', 'volcadura'],
    'incendio': ['incendio', 'fuego', 'llamas'],
    'transito': ['tránsito', 'transito', 'corte', 'piquete', 'demora', 'congestion', 'congestión'],
    'clima': ['tormenta', 'temporal', 'alerta', 'lluvia', 'granizo', 'viento'],
    'rescate': ['rescate', 'evacuac', 'evacuación'],
}

def _get_incident_feeds() -> list[str]:
    return _get_env_list('INCIDENT_FEEDS', DEFAULT_INCIDENT_FEEDS + DEFAULT_NEWS_FEEDS)

def categorize_headline(title: str) -> tuple[str, list[str]]:
    lt = title.lower()
    matched = []
    best = 'general'
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in lt:
                matched.append(cat)
                break
    if matched:
        # pick the first bucket matched as primary category
        best = matched[0]
    return best, matched

def get_incident_items(limit: int = 15, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Return a list of incident / traffic / emergency focused news items.

    Strategy:
    - Reuse the main news cache when possible (do not duplicate fetches).
    - Fetch extra incident feeds (INCIDENT_FEEDS) and merge.
    - Classify each headline into a category bucket and mark is_incident=True
      when any category other than 'general' matches.
    - Apply same severity classification.
    - De-duplicate by title.
    """
    # Start with the already cached general news items
    base = get_latest_news(limit=limit*2)  # small expansion to have enough candidates
    feeds = _get_incident_feeds()

    collected: List[Dict[str, Any]] = []
    titles_seen = {item['title'] for item in base}

    # Copy base items with categorization
    for item in base:
        cat, cats = categorize_headline(item['title'])
        item_copy = {**item, 'category': cat, 'categories': cats, 'is_incident': cat != 'general'}
        collected.append(item_copy)

    # Fetch additional incident feeds (skip those already in NEWS_FEEDS to avoid duplication cost)
    news_feeds = set(_get_env_list('NEWS_FEEDS', DEFAULT_NEWS_FEEDS))
    for url in feeds[:6]:
        if url in news_feeds:
            continue
        try:
            if _HAS_FEEDPARSER:
                parsed = feedparser.parse(url)
                for e in parsed.entries[:8]:
                    title_raw = getattr(e, 'title', '') or e.get('title', '') if isinstance(e, dict) else ''
                    title = HEADLINE_CLEAN_RE.sub(' ', title_raw).strip()
                    if not title or title in titles_seen:
                        continue
                    published_dt = _parse_datetime(e)
                    published_display = ''
                    if published_dt:
                        published_display = dj_tz.localtime(published_dt).strftime('%H:%M') if published_dt.tzinfo else published_dt.strftime('%H:%M')
                    link = getattr(e, 'link', '') or e.get('link', '') if isinstance(e, dict) else ''
                    source = parsed.feed.get('title') if hasattr(parsed, 'feed') else url.split('/')[2]
                    sev = classify_headline_severity(title)
                    cat, cats = categorize_headline(title)
                    collected.append({
                        'title': title[:220],
                        'source': source[:60] if source else url.split('/')[2],
                        'published': published_dt,
                        'published_display': published_display,
                        'link': link,
                        **sev,
                        'category': cat,
                        'categories': cats,
                        'is_incident': cat != 'general'
                    })
                    titles_seen.add(title)
            else:
                fallback_items = _fallback_parse_rss(url)
                for item in fallback_items:
                    if item['title'] in titles_seen:
                        continue
                    sev = classify_headline_severity(item['title'])
                    cat, cats = categorize_headline(item['title'])
                    item.update(sev)
                    item.update({'category': cat, 'categories': cats, 'is_incident': cat != 'general'})
                    collected.append(item)
                    titles_seen.add(item['title'])
        except Exception as e:  # pragma: no cover
            logger.warning("Error parsing incident feed %s: %s", url, e)
            continue

    # Filter to only those that are incidents (or keep all?) – prefer incidents first
    incidents = [c for c in collected if c.get('is_incident')]
    # if not enough, append general
    if len(incidents) < limit:
        others = [c for c in collected if not c.get('is_incident')]
        incidents.extend(others)

    # Sort by severity score desc then published desc
    incidents.sort(key=lambda x: (
        -(x.get('severity_score') or 0),
        x.get('published') or datetime(1970,1,1, tzinfo=timezone.utc)
    ), reverse=False)  # severity_score negative invert earlier -> easier: use reverse sort separately
    incidents.sort(key=lambda x: (x.get('published') or datetime(1970,1,1, tzinfo=timezone.utc)), reverse=True)
    incidents.sort(key=lambda x: (x.get('severity_score') or 0), reverse=True)

    return incidents[:limit]

__all__ = ['get_latest_news', 'get_weather_status', 'classify_headline_severity', 'get_incident_items']

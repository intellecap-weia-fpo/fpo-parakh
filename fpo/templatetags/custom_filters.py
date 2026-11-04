from django import template
from decimal import Decimal

import re

register = template.Library()

@register.filter
def indian_currency(value):
    if not value:
        return "0"
    
    value = float(value)
    if value >= 10000000:  # 1 crore
        formatted = value / 10000000
        return f"{formatted:.1f} Cr" if not formatted.is_integer() else f"{int(formatted)} Cr"
    elif value >= 100000:  # 1 lakh
        formatted = value / 100000
        return f"{formatted:.1f} L" if not formatted.is_integer() else f"{int(formatted)} L"
    else:
        return f"{value:,.0f}"


def _is_number(v):
    try:
        # Support Decimal, int, float, and numeric strings
        if isinstance(v, (int, float, Decimal)):
            return True
        if isinstance(v, str):
            float(v)
            return True
    except Exception:
        return False
    return False


@register.filter
def humanize_label(field_name: str) -> str:
    """Convert snake_case field names to human-friendly labels.

    - Replaces underscores with spaces
    - Title-cases words, while uppercasing known abbreviations (FPO, GST, PAN, etc.)
    - Tweaks common tokens like FY year ranges (e.g., fy 23 24 -> FY 23-24)
    """
    if not isinstance(field_name, str):
        return str(field_name)

    text = field_name.replace("_", " ").strip()
    if not text:
        return ""

    tokens = text.split()
    upper_map = {
        "fpo": "FPO",
        "bod": "BOD",
        "ceo": "CEO",
        "gst": "GST",
        "pan": "PAN",
        "tan": "TAN",
        "msp": "MSP",
        "ngo": "NGO",
        "kvks": "KVKs",
        "pgs": "PGS",
        "figs": "FIGS",
        "fy": "FY",
        "id": "ID",
    }

    def fmt(tok: str) -> str:
        low = tok.lower()
        if low in upper_map:
            return upper_map[low]
        # Numbers or mixed digits remain as-is
        if re.fullmatch(r"[0-9]+", tok):
            return tok
        # Keep common short prepositions/articles lowercase
        if low in {"and", "or", "of", "in", "to", "for", "by", "on", "at"}:
            return low
        return tok.capitalize()

    words = [fmt(t) for t in tokens]

    # Special handling for FY year ranges: e.g., "FY 23 24" -> "FY 23-24"
    if len(words) >= 3 and words[0] == "FY" and re.fullmatch(r"\d{2}", words[1]) and re.fullmatch(r"\d{2}", words[2]):
        words[1] = f"{words[1]}-{words[2]}"
        del words[2]

    return " ".join(words)


@register.filter(name="format_field_value")
def format_field_value(value, field_name: str):
    """Format values with units based on field name heuristics.

    - Currency fields -> prefix with ₹ and compact using indian_currency
    - Percentage fields -> append %
    - Year/day counts -> append units
    - Scores -> append %
    Fallback: return the value as-is.
    """
    # Preserve blank/None
    if value is None or value == "":
        return "-"

    # Booleans are handled elsewhere usually, but keep symbols here if needed
    if isinstance(value, bool):
        return "✓" if value else "✗"

    field = (field_name or "").lower()

    # Heuristics for types
    currency_keywords = [
        "amount",
        "revenue",
        "capital",
        "assets",
        "liabilities",
        "inventory",
        "debt",
        "loan",
        "payable",
        "receivable",
        "cogs",
        "turnover",
        "grant",
        "profit",
        "sales",
        "purchase",
        "expenses",
        "income",
        "net_worth",
        "worth",
        "value_in_inr",
    ]
    percent_keywords = ["percentage", "percent"]

    # Currency formatting
    if any(k in field for k in currency_keywords) and _is_number(value):
        return f"₹ {indian_currency(value)}"

    # Percentage formatting (also for *_score fields)
    if any(k in field for k in percent_keywords) or field.endswith("_score"):
        try:
            num = float(value)
            # Preserve one decimal if present
            return f"{num:.1f}%" if not float(num).is_integer() else f"{int(num)}%"
        except Exception:
            return f"{value}%"

    # Years
    if field.endswith("_years") or field.endswith("_age") or "age_of_fpo" in field or "years_of_experience" in field:
        # Round to 1 decimal; drop .0
        try:
            num = float(value)
            rounded = round(num, 1)
            if abs(rounded - int(rounded)) < 1e-9:
                return f"{int(rounded)} years"
            return f"{rounded:.1f} years"
        except Exception:
            return f"{value} years"

    # Days
    if "days" in field:
        try:
            num = float(value)
            if abs(num - int(num)) < 1e-9:
                return f"{int(num)} days"
            return f"{num:.1f} days"
        except Exception:
            return f"{value} days"

    # Ratios
    if "ratio" in field and _is_number(value):
        try:
            return f"{float(value):.2f}x"
        except Exception:
            return f"{value}x"

    # Default
    return value
    
    
@register.filter
def year_specific_label(field_name: str, financial_year: str = None) -> str:
    """Generate year-specific labels for financial fields.
    
    Converts field names like 'current_year_revenue' to '2023-24 Revenue'
    when provided with a financial year like '2023-2024' or '2023-24'.
    """
    if not field_name or not financial_year:
        return humanize_label(field_name)
    
    # Parse financial year format, handling both "YYYY-YYYY" and "YYYY-YY"
    year_parts = financial_year.split('-')
    if len(year_parts) == 2:
        # Handle "YYYY-YYYY" format
        if len(year_parts[0]) == 4 and len(year_parts[1]) == 4:
            short_year = f"{year_parts[0]}-{year_parts[1][2:]}"
        # Handle "YYYY-YY" format
        elif len(year_parts[0]) == 4 and len(year_parts[1]) == 2:
            short_year = financial_year
        else:
            short_year = financial_year
    else:
        short_year = financial_year
    
    # Map field prefixes to year contexts
    field_lower = field_name.lower()
    
    if field_lower.startswith('current_year_'):
        base_name = field_name.replace('current_year_', '')
        return f"{short_year} {humanize_label(base_name)}"
    elif field_lower.startswith('previous_year_'):
        # Calculate previous year from current financial year
        if len(year_parts) == 2:
            try:
                if len(year_parts[1]) == 4:  # YYYY-YYYY format
                    prev_start = int(year_parts[0]) - 1
                    prev_end = int(year_parts[1]) - 1
                    prev_short = f"{prev_start}-{str(prev_end)[2:]}"
                else:  # YYYY-YY format
                    current_start = int(year_parts[0])
                    current_end_suffix = int(year_parts[1])
                    prev_start = current_start - 1
                    prev_end_suffix = current_end_suffix - 1
                    # Handle year rollover (e.g., 2023-24 -> 2022-23)
                    prev_short = f"{prev_start}-{prev_end_suffix:02d}"
            except (ValueError, TypeError):
                prev_short = "Previous Year"
        else:
            prev_short = "Previous Year"
        
        base_name = field_name.replace('previous_year_', '')
        return f"{prev_short} {humanize_label(base_name)}"
    elif field_lower.startswith('two_years_back_'):
        # Calculate two years back from current financial year
        if len(year_parts) == 2:
            try:
                if len(year_parts[1]) == 4:  # YYYY-YYYY format
                    two_back_start = int(year_parts[0]) - 2
                    two_back_end = int(year_parts[1]) - 2
                    two_back_short = f"{two_back_start}-{str(two_back_end)[2:]}"
                else:  # YYYY-YY format
                    current_start = int(year_parts[0])
                    current_end_suffix = int(year_parts[1])
                    two_back_start = current_start - 2
                    two_back_end_suffix = current_end_suffix - 2
                    # Handle year rollover (e.g., 2023-24 -> 2021-22)
                    two_back_short = f"{two_back_start}-{two_back_end_suffix:02d}"
            except (ValueError, TypeError):
                two_back_short = "Two Years Back"
        else:
            two_back_short = "Two Years Back"
        
        base_name = field_name.replace('two_years_back_', '')
        return f"{two_back_short} {humanize_label(base_name)}"
    
    # Fallback to regular humanization for non-year-specific fields
    return humanize_label(field_name)


@register.filter
def year_from_prefix(year_prefix: str, financial_year: str = None) -> str:
    """Return a display-friendly financial year for a given prefix.

    Args:
        year_prefix: One of "current_year", "previous_year", "two_years_back"
        financial_year: Base financial year like "2023-24" or "2023-2024"
    """
    if not year_prefix:
        return ""

    prefix = str(year_prefix).lower()

    # Fallback labels when we cannot compute exact years
    fallback_map = {
        "current_year": "Current Year",
        "previous_year": "Previous Year",
        "two_years_back": "Two Years Back",
    }

    if not financial_year:
        return fallback_map.get(prefix, year_prefix.replace("_", " ").title())

    year_parts = str(financial_year).split('-')
    try:
        start_year = int(year_parts[0])
    except (ValueError, IndexError):
        return fallback_map.get(prefix, year_prefix.replace("_", " ").title())

    # Determine the end year for the base financial year
    try:
        if len(year_parts) > 1:
            end_part = year_parts[1]
            if len(end_part) == 4:
                end_year = int(end_part)
            elif len(end_part) == 2:
                century = (start_year // 100) * 100
                end_year = century + int(end_part)
            else:
                end_year = start_year + 1
        else:
            end_year = start_year + 1
    except ValueError:
        end_year = start_year + 1

    def fmt_range(start: int, end: int) -> str:
        return f"{start}-{str(end)[-2:].zfill(2)}"

    if prefix == "current_year":
        return fmt_range(start_year, end_year)
    if prefix == "previous_year":
        return fmt_range(start_year - 1, end_year - 1)
    if prefix == "two_years_back":
        return fmt_range(start_year - 2, end_year - 2)

    return fallback_map.get(prefix, year_prefix.replace("_", " ").title())


@register.filter
def comma_to_space(value):
    return value.replace(',', ', ') if value else value

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    return dictionary.get(key)

@register.filter
def split(value, delimiter):
    """Split a string by delimiter."""
    return value.split(delimiter)

@register.filter
def score_percentage(value, section_name):
    """Convert raw score to percentage based on section maximum.
    
    Args:
        value: Raw score value
        section_name: Name of the section ('governance', 'business', 'process', 'financial')
    
    Returns:
        str: Formatted percentage (e.g., "60.7%")
    """
    if value is None:
        return "N/A"
    
    try:
        score = float(value)
    except (ValueError, TypeError):
        return "N/A"
    
    # Define maximum scores for each section
    max_scores = {
        'governance': 27,
        'business': 30,
        'process': 21,
        'financial': 30
    }
    
    max_score = max_scores.get(section_name.lower())
    if max_score is None:
        return f"{score}"
    
    if max_score == 0:
        return "N/A"
    
    percentage = (score / max_score) * 100
    
    # Format with one decimal place if needed
    if percentage.is_integer():
        return f"{int(percentage)}%"
    else:
        return f"{percentage:.1f}%"

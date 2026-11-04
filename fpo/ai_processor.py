import os
import sys
from pathlib import Path
import time
from django.db import transaction
import json
import base64
import logging
import re
from datetime import datetime
import fitz  # PyMuPDF
from openai import OpenAI
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed
from fpo.models import *

# ===== ENUM MAPPING FUNCTIONS =====
def map_producer_org_type(ai_value):
    """Map AI-extracted producer organization type to valid enum values"""
    if not ai_value:
        return 'producer_company'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'producer company': 'producer_company',
        'producer co': 'producer_company',
        'producer organization': 'producer_company',
        'co-operative society': 'co_operative_society',
        'cooperative society': 'co_operative_society',
        'non-profit society': 'non_profit_society',
        'non profit society': 'non_profit_society',
        'npo': 'non_profit_society',
        'trust': 'trust',
        'section 8 company': 'section_8_company',
        'section 8': 'section_8_company',
        'section8': 'section_8_company'
    }
    return mapping.get(ai_value, 'producer_company')  # Default to producer_company

def map_minutes_maintenance(ai_value):
    """Map AI-extracted minutes maintenance to valid enum values"""
    if not ai_value:
        return 'detailed_compliant'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'physical': 'detailed_compliant',  # Map "physical" to detailed_compliant
        'digital': 'detailed_compliant',
        'both': 'detailed_compliant',
        'detailed': 'detailed_compliant',
        'compliant': 'detailed_compliant',
        'not updated': 'detailed_not_updated',
        'sketchy': 'sketchy_quality',
        'poor': 'sketchy_quality',
        'not maintained': 'not_maintained',
        'none': 'not_maintained'
    }
    return mapping.get(ai_value, 'detailed_compliant')  # Default to detailed_compliant

def map_experience_type(ai_value):
    """Map AI-extracted experience type to valid enum values"""
    if not ai_value:
        return 'any_other'  # Default value for required field
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'agriculture': 'agricultural_cooperatives',
        'agricultural': 'agricultural_cooperatives',
        'cooperative': 'agricultural_cooperatives',
        'farmer owned': 'farmer_owned_enterprises',
        'farmer enterprise': 'farmer_owned_enterprises',
        'ngo': 'ngo_agriculture',
        'non-governmental': 'ngo_agriculture',
        'non profit': 'ngo_agriculture',
        'farm management': 'farm_management',
        'village council': 'village_councils',
        'self help group': 'self_help_groups',
        'shg': 'self_help_groups',
        'government': 'government_agriculture',
        'business': 'business_functions',
        'commercial': 'business_functions',
        'finance': 'business_functions',
        'marketing': 'business_functions'
    }
    return mapping.get(ai_value, 'any_other')  # Default to any_other

def map_second_line_management(ai_value):
    """Map AI-extracted second line management to valid enum values"""
    if not ai_value:
        return 'only_ceo'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'ceo with accounts and two managers': 'ceo_accounts_two_managers',
        'ceo accounts two managers': 'ceo_accounts_two_managers',
        'ceo with accounts and one manager': 'ceo_accounts_one_manager',
        'ceo accounts one manager': 'ceo_accounts_one_manager',
        'ceo with accounts': 'ceo_with_accounts',
        'ceo accounts': 'ceo_with_accounts',
        'only ceo': 'only_ceo',
        'just ceo': 'only_ceo',
        'no ceo': 'no_ceo',
        'without ceo': 'no_ceo',
        'ceo': 'only_ceo',
        'manager': 'ceo_with_accounts',
        'secretary': 'ceo_with_accounts'
    }
    return mapping.get(ai_value, 'only_ceo')  # Default to only_ceo

def map_promoting_agency_type(ai_value):
    """Map AI-extracted promoting agency type to valid enum values"""
    if not ai_value:
        return 'others'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'ngo': 'ngo',
        'non-governmental': 'ngo',
        'non profit': 'ngo',
        'trust': 'trusts',
        'trusts': 'trusts',
        'cooperative': 'cooperatives',
        'cooperatives': 'cooperatives',
        'corporate': 'corporate_wings',
        'corporate wings': 'corporate_wings',
        'corporate foundation': 'corporate_wings',
        'state government': 'state_govt',
        'state govt': 'state_govt',
        'government': 'state_govt',
        'kvk': 'kvks',
        'kvks': 'kvks',
        'farmer federation': 'farmer_federations',
        'farmer federations': 'farmer_federations',
        'commodity board': 'commodity_boards',
        'commodity boards': 'commodity_boards',
        'big farmer company': 'big_farmer_companies',
        'big farmer companies': 'big_farmer_companies',
        'other': 'others',
        'others': 'others'
    }
    return mapping.get(ai_value, 'others')  # Default to others

def map_act_registered_type(ai_value):
    """Map AI-extracted act registered type to valid enum values"""
    if not ai_value:
        return 'company_act'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'company act': 'company_act',
        'companies act': 'company_act',
        'cooperative societies act': 'cooperative_societies_act',
        'cooperative act': 'cooperative_societies_act',
        'coop act': 'cooperative_societies_act',
        'societies act': 'cooperative_societies_act',
        'other': 'other',
        'others': 'other'
    }
    return mapping.get(ai_value, 'company_act')  # Default to company_act

def map_price_volatility(ai_value):
    """Map AI-extracted price volatility to valid enum values"""
    if not ai_value:
        return 'not_applicable'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'highly volatile': 'highly_volatile_fpo_risk',
        'high volatility': 'highly_volatile_fpo_risk',
        'volatile': 'highly_volatile_fpo_risk',
        'msp risk': 'msp_fpo_risk',
        'msp': 'msp_fpo_risk',
        'partial hedge': 'partial_hedge',
        'partially hedged': 'partial_hedge',
        'well hedged': 'well_hedged',
        'hedged': 'well_hedged',
        'medium': 'partial_hedge',  # Map "medium" to partial_hedge
        'moderate': 'partial_hedge',  # Map "moderate" to partial_hedge
        'not applicable': 'not_applicable',
        'na': 'not_applicable',
        'n/a': 'not_applicable'
    }
    return mapping.get(ai_value, 'not_applicable')  # Default to not_applicable

def map_input_timeliness(ai_value):
    """Map AI-extracted input timeliness to valid enum values"""
    if not ai_value:
        return 'not_applicable'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        '30 days': '30_days_prior',
        '30 days prior': '30_days_prior',
        '20 days': '20_days_prior',
        '20 days prior': '20_days_prior',
        '15 days': '15_days_prior',
        '15 days prior': '15_days_prior',
        '7 days': '7_days_prior',
        '7 days prior': '7_days_prior',
        'not applicable': 'not_applicable',
        'na': 'not_applicable',
        'n/a': 'not_applicable'
    }
    return mapping.get(ai_value, 'not_applicable')  # Default to not_applicable

def map_price_affordability(ai_value):
    """Map AI-extracted price affordability to valid enum values"""
    if not ai_value:
        return 'not_applicable'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        '10-15% less': '10_15_percent_less',
        '10 to 15%': '10_15_percent_less',
        '10-15%': '10_15_percent_less',
        '5-10% less': '5_10_percent_less',
        '5 to 10%': '5_10_percent_less',
        '5-10%': '5_10_percent_less',
        '3-5% less': '3_5_percent_less',
        '3 to 5%': '3_5_percent_less',
        '3-5%': '3_5_percent_less',
        '1-3% less': '1_3_percent_less',
        '1 to 3%': '1_3_percent_less',
        '1-3%': '1_3_percent_less',
        'not applicable': 'not_applicable',
        'na': 'not_applicable',
        'n/a': 'not_applicable'
    }
    return mapping.get(ai_value, 'not_applicable')  # Default to not_applicable

def map_distance_availability(ai_value):
    """Map AI-extracted distance availability to valid enum values"""
    if not ai_value:
        return 'not_applicable'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        '3 km': '3_km_available',
        'within 3 km': '3_km_available',
        '6 km': '6_km_available',
        'within 6 km': '6_km_available',
        '10 km': '10_km_available',
        'within 10 km': '10_km_available',
        'not within 10 km': 'not_within_10_km',
        'beyond 10 km': 'not_within_10_km',
        'not applicable': 'not_applicable',
        'na': 'not_applicable',
        'n/a': 'not_applicable'
    }
    return mapping.get(ai_value, 'not_applicable')  # Default to not_applicable

def map_accounts_mis(ai_value):
    """Map AI-extracted accounts MIS to valid enum values"""
    if not ai_value:
        return 'ms_office_tools'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'no mis': 'no_mis',
        'no system': 'no_mis',
        'ms office': 'ms_office_tools',
        'excel': 'ms_office_tools',
        'word': 'ms_office_tools',
        'tally': 'tally_no_digital',
        'tally no digital': 'tally_no_digital',
        'software': 'software_digital',
        'digital': 'software_digital',
        'automated': 'software_digital'
    }
    return mapping.get(ai_value, 'ms_office_tools')  # Default to ms_office_tools

def map_insurance_stock(ai_value):
    """Map AI-extracted insurance stock to valid enum values"""
    if not ai_value:
        return 'no_insurance'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'no insurance': 'no_insurance',
        'uninsured': 'no_insurance',
        'less than 50%': 'less_than_50_fire',
        'under 50%': 'less_than_50_fire',
        '50%': '50_fire_theft',
        'fifty percent': '50_fire_theft',
        '100%': '100_fire_theft',
        'hundred percent': '100_fire_theft',
        'fully insured': '100_fire_theft'
    }
    return mapping.get(ai_value, 'no_insurance')  # Default to no_insurance

def map_credit_record(ai_value):
    """Map AI-extracted credit record to valid enum values"""
    if not ai_value:
        return 'no_credit_history'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'no history': 'no_credit_history',
        'no record': 'no_credit_history',
        'multiple delays': 'multiple_delays',
        'multiple defaults': 'multiple_delays',
        'one delay': 'one_delay',
        'single delay': 'one_delay',
        'no delays': 'no_delays',
        'no defaults': 'no_delays',
        'clean record': 'no_delays'
    }
    return mapping.get(ai_value, 'no_credit_history')  # Default to no_credit_history

def map_statutory_fillings(ai_value):
    """Map AI-extracted statutory fillings to valid enum values"""
    if not ai_value:
        return 'no_delays'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'delays not filled': 'delays_not_filled',
        'unfilled delays': 'delays_not_filled',
        'multiple delays filled': 'multiple_delays_filled',
        'many delays': 'multiple_delays_filled',
        'few delays filled': 'few_delays_filled',
        'some delays': 'few_delays_filled',
        'no delays': 'no_delays',
        'up to date': 'no_delays',
        'current': 'no_delays'
    }
    return mapping.get(ai_value, 'no_delays')  # Default to no_delays

def map_books_records(ai_value):
    """Map AI-extracted books records to valid enum values"""
    if not ai_value:
        return 'current'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'processes systems': 'processes_systems',
        'processes': 'processes_systems',
        'weekly updated': 'weekly_updated',
        'weekly': 'weekly_updated',
        'lag 2-3 days': 'lag_2_3_days',
        '2-3 days': 'lag_2_3_days',
        'current': 'current',
        'up to date': 'current',
        'real time': 'current'
    }
    return mapping.get(ai_value, 'current')  # Default to current

def map_reconciliation_stocks(ai_value):
    """Map AI-extracted reconciliation stocks to valid enum values"""
    if not ai_value:
        return 'monthly'  # Default value
    
    ai_value = ai_value.lower().strip()
    mapping = {
        'absent annual': 'absent_annual',
        'annual': 'absent_annual',
        'yearly': 'absent_annual',
        '2-4 times': '2_4_times_year',
        'quarterly': '2_4_times_year',
        'monthly': 'monthly',
        'every month': 'monthly',
        'every 15 days': 'every_15_days',
        'bi-monthly': 'every_15_days',
        'fortnightly': 'every_15_days'
    }
    return mapping.get(ai_value, 'monthly')  # Default to monthly


def test_enum_mappings():
    """Test function to verify all enum mappings work correctly"""
    print("Testing enum mappings...")
    
    # Test producer organization mapping
    assert map_producer_org_type("PRODUCER COMPANY") == "producer_company"
    assert map_producer_org_type("Co-operative Society") == "co_operative_society"
    assert map_producer_org_type("") == "producer_company"
    
    # Test minutes maintenance mapping
    assert map_minutes_maintenance("physical") == "detailed_compliant"
    assert map_minutes_maintenance("digital") == "detailed_compliant"
    assert map_minutes_maintenance("not maintained") == "not_maintained"
    
    # Test experience type mapping
    assert map_experience_type("agriculture") == "agricultural_cooperatives"
    assert map_experience_type("NGO") == "ngo_agriculture"
    assert map_experience_type("") == "any_other"
    
    # Test second line management mapping
    assert map_second_line_management("ceo with accounts and two managers") == "ceo_accounts_two_managers"
    assert map_second_line_management("only ceo") == "only_ceo"
    assert map_second_line_management("") == "only_ceo"
    
    # Test promoting agency mapping
    assert map_promoting_agency_type("NGO") == "ngo"
    assert map_promoting_agency_type("government") == "state_govt"
    assert map_promoting_agency_type("") == "others"
    
    # Test act registered mapping
    assert map_act_registered_type("company act") == "company_act"
    assert map_act_registered_type("cooperative societies act") == "cooperative_societies_act"
    assert map_act_registered_type("") == "company_act"
    
    # Test price volatility mapping
    assert map_price_volatility("highly volatile") == "highly_volatile_fpo_risk"
    assert map_price_volatility("msp") == "msp_fpo_risk"
    assert map_price_volatility("") == "not_applicable"
    assert map_price_volatility("medium") == "partial_hedge"
    assert map_price_volatility("moderate") == "partial_hedge"
    
    # Test all other enum mappings
    assert map_input_timeliness("30 days") == "30_days_prior"
    assert map_price_affordability("10-15% less") == "10_15_percent_less"
    assert map_distance_availability("3 km") == "3_km_available"
    assert map_accounts_mis("no mis") == "no_mis"
    assert map_insurance_stock("no insurance") == "no_insurance"
    assert map_credit_record("no history") == "no_credit_history"
    assert map_statutory_fillings("no delays") == "no_delays"
    assert map_books_records("current") == "current"
    assert map_reconciliation_stocks("monthly") == "monthly"
    
    print("All enum mappings tested successfully!")

def validate_and_map_enum(field_name, ai_value, default_value):
    """Generic function to validate and map enum values"""
    if not ai_value:
        return default_value
    
    if field_name == 'type_of_producer_organization':
        return map_producer_org_type(ai_value)
    elif field_name == 'minutes_maintenance':
        return map_minutes_maintenance(ai_value)
    elif field_name == 'type_of_experience':
        return map_experience_type(ai_value)
    elif field_name == 'type_of_fpo':
        # Simple mapping for FPO type
        ai_value = ai_value.lower().strip()
        if 'input' in ai_value and 'output' in ai_value:
            return 'inputs_and_output'
        elif 'input' in ai_value or 'output' in ai_value:
            return 'inputs_or_output'
        elif 'high' in ai_value or '50' in ai_value:
            return 'high_capacity'
        elif 'low' in ai_value:
            return 'low_capacity'
        else:
            return 'inputs_and_output'  # Default
    elif field_name == 'second_line_management':
        return map_second_line_management(ai_value)
    elif field_name == 'type_of_promoting_agency':
        return map_promoting_agency_type(ai_value)
    elif field_name == 'act_under_registered':
        return map_act_registered_type(ai_value)
    elif field_name == 'price_volatility_of_products':
        return map_price_volatility(ai_value)
    elif field_name == 'availability_of_inputs_timeliness':
        return map_input_timeliness(ai_value)
    elif field_name == 'availability_of_inputs_price_affordability':
        return map_price_affordability(ai_value)
    elif field_name == 'availability_of_inputs_place':
        return map_distance_availability(ai_value)
    elif field_name == 'accounts_and_mis':
        return map_accounts_mis(ai_value)
    elif field_name == 'insurance_of_stock':
        return map_insurance_stock(ai_value)
    elif field_name == 'credit_record_of_fpo':
        return map_credit_record(ai_value)
    elif field_name == 'statutory_fillings':
        return map_statutory_fillings(ai_value)
    elif field_name == 'books_and_records_up_to_date':
        return map_books_records(ai_value)
    elif field_name == 'reconciliation_of_stocks':
        return map_reconciliation_stocks(ai_value)
    
    return ai_value  # Return as-is for non-enum fields

logger = logging.getLogger(__name__)


import certifi
from openai import OpenAI

openai_client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE_URL
)



class FPODocumentProcessor:
    """
    Generic FPO document processor with AI-only extraction
    Modular system for processing different data models
    """
    
    def __init__(self):
        self.openai_client = openai_client
        self.ocr_model = settings.PDF_OCR_MODEL
        self.extraction_model = settings.PDF_EXTRACT_MODEL
        
    
    def extract_text_from_pdf(self, pdf_bytes):
        """Determine if PDF needs OCR or has extractable text"""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            pages_with_text = 0
            all_text = ""
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                text = page.get_text()
                
                if text.strip():
                    pages_with_text += 1
                    all_text += f"\n--- Page {page_num + 1} ---\n{text}"
            
            doc.close()
            
            # If more than 50% pages have text, use direct extraction
            has_extractable_text = pages_with_text > (total_pages * 0.5)
            
            return {
                "has_text": has_extractable_text,
                "text_content": all_text if has_extractable_text else "",
                "total_pages": total_pages,
                "pages_with_text": pages_with_text
            }
            
        except Exception as e:
            logger.error(f"Error analyzing PDF: {str(e)}")
            return {"has_text": False, "text_content": "", "error": str(e)}
    
    def _process_single_page(self, page_data):
        """Process a single page for OCR (to be used in parallel)"""
        page_num, page, ocr_model = page_data
        try:
            print(f"Processing page {page_num + 1} with model: {ocr_model} via {self.openai_client.base_url}")
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img_data = pix.tobytes("png")
            base64_image = base64.b64encode(img_data).decode('utf-8')
            
            messages = [
                {
                    "role": "system",
                    "content": """Extract ALL text from this financial document page.
                    
                    FOCUS ON:
                    - Company names and registration details
                    - Financial figures and tables
                    - Director names and signatures
                    - Address and contact information
                    - Dates and numerical data
                    
                    Preserve exact formatting and numbers."""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Extract all text from page {page_num + 1}:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ]
            
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=ocr_model,
                    messages=messages,
                    max_tokens=2000,
                    temperature=0.1
                )
            )
            
            page_text = response.choices[0].message.content
            return page_num, f"\n=== PAGE {page_num + 1} ===\n{page_text}"
            
        except Exception as e:
            logger.error(f"OCR failed for page {page_num + 1}: {str(e)}")
            return page_num, f"\n=== PAGE {page_num + 1} ===\n[OCR FAILED: {str(e)}]"
    
    def ocr_with_qwen(self, pdf_bytes):
        """OCR using Qwen VL-Max for image-based PDFs with parallel processing"""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            
            # Limit to 5 pages for testing
            pages_to_process = total_pages
            print(f"Processing {pages_to_process} pages with parallel OCR...")
            
            # Prepare page data for parallel processing
            page_data_list = []
            for page_num in range(pages_to_process):
                page = doc.load_page(page_num)
                page_data_list.append((page_num, page, self.ocr_model))
            
            # Process pages in parallel
            all_ocr_text = ""
            with ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all tasks
                future_to_page = {
                    executor.submit(self._process_single_page, page_data): page_data 
                    for page_data in page_data_list
                }
                
                # Process completed tasks as they finish
                completed_count = 0
                for future in as_completed(future_to_page):
                    page_data = future_to_page[future]
                    page_num = page_data[0]
                    try:
                        page_num, page_text = future.result()
                        all_ocr_text += page_text
                        completed_count += 1
                        print(f"Completed page {page_num + 1}/{pages_to_process}")
                    except Exception as e:
                        logger.error(f"Page {page_num + 1} generated an exception: {str(e)}")
                        all_ocr_text += f"\n=== PAGE {page_num + 1} ===\n[PROCESSING ERROR: {str(e)}]"
            
            doc.close()
            return all_ocr_text
            
        except Exception as e:
            logger.error(f"OCR failed: {str(e)}")
            raise Exception(f"OCR extraction failed: {str(e)}")
    
    def _api_call_with_retry(self, api_func, max_retries=1):
        """API call with retry logic"""
        for attempt in range(max_retries):
            try:
                return api_func()
            except Exception as e:
                if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + 1
                    print(f"Rate limit hit, waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif attempt == max_retries - 1:
                    raise e
                else:
                    time.sleep(1)
    
    # ===== BASIC DETAILS EXTRACTION =====
    def extract_basic_details_only(self, text_content):
        """
        Extract ONLY basic organization details for FPODetailsSubmission
        Specialized AI prompt for maximum accuracy
        """
        
        print(f"Extracting financial details using model: {self.extraction_model}")
        
        system_prompt = """You are a data extraction specialist for Indian FPO (Farmer Producer Organization) documents.

TASK: Extract and clean basic organization information with perfect accuracy.

TEXT CLEANING RULES:
- Remove document headers/prefixes from company names
- Clean location names (remove trailing text after line breaks)
- Extract core entity names from formal titles
- Handle OCR artifacts and formatting issues

EXTRACTION RULES:
1. Company Name: Remove document headers like "TO THE MEMBERS OF", "M/s", "INDEPENDENT AUDITOR'S REPORT"
2. Clean Data: Extract only actual values, no extra text
3. Dates: Use YYYY-MM-DD format only
4. Numbers: Extract numeric values only
5. Location: Clean place names (Place: Palghar → "Palghar")

REQUIRED FIELDS:
- name: Legal company name (cleaned)
- registration_number: CIN or registration number
- state: State name only
- district: District name only
- address: Full registered address
- contact_email: Email address
- contact_phone: Phone number
- pin_code: PIN code
- date_of_incorporation: YYYY-MM-DD format
- age_of_fpo_years: Age in years (numeric)

If any field is not found, leave it empty."""

        user_prompt = f"""Extract basic organization details from this FPO document:

{text_content[:15000]}

Return ONLY a JSON object with these exact field names:
{{
  "name": "",
  "registration_number": "",
  "state": "",
  "district": "",
  "address": "",
  "contact_email": "",
  "contact_phone": "",
  "pin_code": "",
  "date_of_incorporation": "",
  "age_of_fpo_years": 0
}}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            
            # Clean company name
            if extracted_data.get('name'):
                name = extracted_data['name']
                # Remove common prefixes
                prefixes_to_remove = [
                    r'^(TO THE MEMBERS OF\s+)',
                    r'^(M/s\s+)',
                    r'^(INDEPENDENT AUDITOR.S REPORT\s+)',
                    r'^(ANNUAL REPORT\s+OF\s+)'
                ]
                for prefix in prefixes_to_remove:
                    name = re.sub(prefix, '', name, flags=re.IGNORECASE)
                extracted_data['name'] = name.strip()
            
            # Convert age to float
            if extracted_data.get('age_of_fpo_years'):
                try:
                    extracted_data['age_of_fpo_years'] = float(extracted_data['age_of_fpo_years'])
                except:
                    extracted_data['age_of_fpo_years'] = 1.0
            
            print(f"Extracted basic details: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Raw response: {content}")
            return {}
        except Exception as e:
            print(f"Basic details extraction failed: {e}")
            return {}
    
    def save_basic_details(self, fpo_id, basic_data, financial_year=None, text_content=""):
        """Save basic details to database with logging - only save to yearly submission, not FPO model"""
        if not fpo_id or not basic_data:
            print("No data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)

            print(f"Saving basic details for FPO: {fpo.name} (yearly submission only)")
            
            # Create FPODetailsSubmission - only store in yearly submission, not update FPO model
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Parse dates
            incorporation_date = None
            if basic_data.get('date_of_incorporation'):
                try:
                    incorporation_date = datetime.strptime(basic_data['date_of_incorporation'], '%Y-%m-%d').date()
                except:
                    incorporation_date = datetime(1900, 1, 1).date()
            else:
                incorporation_date = datetime(1900, 1, 1).date()
            
            defaults = {
                'name_of_producer_organization': basic_data.get('name', '')[:500],
                'registered_address': basic_data.get('address', '')[:1000],
                'district': basic_data.get('district', '')[:100],
                'state': basic_data.get('state', '')[:100],
                'type_of_producer_organization': validate_and_map_enum(
                    'type_of_producer_organization',
                    basic_data.get('type_of_producer_organization'),
                    'producer_company'
                ),
                'date_of_incorporation': incorporation_date,
                'date_of_commencement': incorporation_date,
                'age_of_fpo_years': basic_data.get('age_of_fpo_years', 1.0),
                'type_of_fpo': validate_and_map_enum(
                    'type_of_fpo',
                    basic_data.get('type_of_fpo'),
                    'inputs_and_output'
                ),
            }
            
            obj, created = FPODetailsSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated existing FPODetailsSubmission")
            else:
                print("Created new FPODetailsSubmission")
            
            # Log what was saved
            print("Saved to database:")
            for key, value in defaults.items():
                if value and str(value) != 'producer_company' and str(value) != 'inputs_and_output':
                    print(f"  {key}: {str(value)[:100]}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving basic details: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ===== FINANCIAL DETAILS EXTRACTION =====
    def extract_financial_details(self, text_content):
        """
        Extract financial details for FinancialDetailsSubmissionV2 model
        Specialized AI prompt for financial data extraction
        """
        
        system_prompt = """You are a financial data extraction specialist for Indian FPO (Farmer Producer Organization) documents.

TASK: Extract financial information from financial statements and reports.

TEXT CLEANING RULES:
- Remove document headers/prefixes from company names
- Clean location names (remove trailing text after line breaks)
- Extract core entity names from formal titles
- Handle OCR artifacts and formatting issues

EXTRACTION RULES:
1. Extract numerical values only (no text descriptions)
2. For monetary values: Convert to decimal numbers (e.g., "₹ 1,50,000" → 150000.00)
3. For percentages: Convert to decimal numbers (e.g., "15%" → 15.00)
4. For quantities: Convert to decimal numbers (e.g., "25.5 MT" → 25.50)
5. If a value is not found, use 0 or empty string
6. For years: Use format "YYYY-YYYY" (e.g., "2022-2023")
7. For product names: Extract comma-separated list

FOCUS ON:
- Revenue figures for current, previous, and 2 years back
- Profit figures (gross and net)
- Share capital and shareholders
- Assets and liabilities
- Inventory details
- Grant details
- Loan and credit information

IDENTIFY FINANCIAL SECTION TYPES:
- Profit & Loss statements (various title formats)
- Balance sheets (current/previous year comparisons)
- Notes to accounts/financial statements
- Revenue/income line items
- Asset/liability tables and summaries
- Share capital and reserves sections



"""


        user_prompt = f"""Extract financial details from this FPO document:

{text_content[:20000]}

Return ONLY a JSON object with these exact field names:
{{
  "current_year_revenue": 0.0,
  "previous_year_revenue": 0.0,
  "two_years_back_revenue": 0.0,
  "current_year_products": "",
  "previous_year_products": "",
  "two_years_back_products": "",
  "target_revenue": 0.0,
  "current_year_quantity_procured": 0.0,
  "current_year_quantity_products": "",
  "previous_year_quantity_procured": 0.0,
  "previous_year_quantity_products": "",
  "two_years_back_quantity_procured": 0.0,
  "two_years_back_quantity_products": "",
  "current_year_retail_revenue": 0.0,
  "current_year_retail_products": "",
  "previous_year_retail_revenue": 0.0,
  "previous_year_retail_products": "",
  "two_years_back_retail_revenue": 0.0,
  "two_years_back_retail_products": "",
  "current_year_wholesale_revenue": 0.0,
  "current_year_wholesale_products": "",
  "previous_year_wholesale_revenue": 0.0,
  "previous_year_wholesale_products": "",
  "two_years_back_wholesale_revenue": 0.0,
  "two_years_back_wholesale_products": "",
  "current_year_institutional_revenue": 0.0,
  "current_year_institutional_products": "",
  "previous_year_institutional_revenue": 0.0,
  "previous_year_institutional_products": "",
  "two_years_back_institutional_revenue": 0.0,
  "two_years_back_institutional_products": "",
  "current_year_cogs": 0.0,
  "previous_year_cogs": 0.0,
  "two_years_back_cogs": 0.0,
  "current_year_gross_profit": 0.0,
  "current_year_net_profit": 0.0,
  "previous_year_gross_profit": 0.0,
  "previous_year_net_profit": 0.0,
  "two_years_back_gross_profit": 0.0,
  "two_years_back_net_profit": 0.0,
  "operating_margin_current_year": 0.0,
  "gross_net_profit_margin_difference": 0.0,
  "current_year_share_capital": 0.0,
  "current_year_shareholders": 0,
  "previous_year_share_capital": 0.0,
  "previous_year_shareholders": 0,
  "two_years_back_share_capital": 0.0,
  "two_years_back_shareholders": 0,
  "current_year_accounts_payable": 0.0,
  "current_year_accounts_receivable": 0.0,
  "previous_year_accounts_payable": 0.0,
  "previous_year_accounts_receivable": 0.0,
  "two_years_back_accounts_payable": 0.0,
  "two_years_back_accounts_receivable": 0.0,
  "current_year_opening_inventory": 0.0,
  "current_year_closing_inventory": 0.0,
  "previous_year_opening_inventory": 0.0,
  "previous_year_closing_inventory": 0.0,
  "two_years_back_opening_inventory": 0.0,
  "two_years_back_closing_inventory": 0.0,
  "current_year_project_grant": 0.0,
  "current_year_matching_grant": 0.0,
  "previous_year_project_grant": 0.0,
  "previous_year_matching_grant": 0.0,
  "two_years_back_project_grant": 0.0,
  "two_years_back_matching_grant": 0.0,
  "current_year_assets": 0.0,
  "current_year_liabilities": 0.0,
  "previous_year_assets": 0.0,
  "previous_year_liabilities": 0.0,
  "two_years_back_assets": 0.0,
  "two_years_back_liabilities": 0.0,
  "current_year_current_assets": 0.0,
  "current_year_current_liabilities": 0.0,
  "previous_year_current_assets": 0.0,
  "previous_year_current_liabilities": 0.0,
  "two_years_back_current_assets": 0.0,
  "two_years_back_current_liabilities": 0.0,
  "current_year_lender_name": "",
  "current_year_loan_amount": 0.0,
  "previous_year_lender_name": "",
  "previous_year_loan_amount": 0.0,
  "two_years_back_lender_name": "",
  "two_years_back_loan_amount": 0.0,
  "cash_cheque_percentage": 0.0,
  "days_payable_receivable_difference": 0,
  "total_debt_today": 0.0,
  "institutional_lending_history": "",
  "credit_default_year": "",
  "credit_default_lender": "",
  "credit_default_amount": 0.0
}}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=3000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            
            print(f"Extracted financial details: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Raw response: {content}")
            return {}
        except Exception as e:
            print(f"Financial details extraction failed: {e}")
            return {}
    
    def save_financial_details(self, fpo_id, financial_data, financial_year=None, text_content=""):
        """Save financial details to database with logging"""
        if not fpo_id or not financial_data:
            print("No financial data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            print(f"Saving financial details for FPO: {fpo.name}")
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            # Get or create yearly submission
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Prepare financial data for saving
            financial_defaults = {}
            for field_name, value in financial_data.items():
                if hasattr(FinancialDetailsSubmissionV2, field_name):
                    field = FinancialDetailsSubmissionV2._meta.get_field(field_name)
                    if isinstance(field, models.DecimalField):
                        financial_defaults[field_name] = float(value) if value else 0.0
                    elif isinstance(field, models.IntegerField):
                        financial_defaults[field_name] = int(value) if value else 0
                    else:
                        financial_defaults[field_name] = value
            
            # Create or update financial details
            obj, created = FinancialDetailsSubmissionV2.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=financial_defaults
            )
            
            if not created:
                for key, value in financial_defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated existing FinancialDetailsSubmissionV2")
            else:
                print("Created new FinancialDetailsSubmissionV2")
            
            # Log what was saved
            print("Saved financial details to database:")
            for key, value in financial_defaults.items():
                if value and value != 0 and value != 0.0:
                    print(f"  {key}: {str(value)[:100]}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving financial details: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ===== BOARD DIRECTOR EXTRACTION =====
    def extract_board_director_details(self, text_content):
        """
        Enhanced board director extraction with better AI prompting
        """
        system_prompt = """You are an expert at extracting information from Indian FPO financial documents.

    Your task is to find ALL people who serve as directors, board members, or key management personnel in this organization.


    TEXT CLEANING RULES:
    - Remove document headers/prefixes from company names
    - Clean location names (remove trailing text after line breaks)
    - Extract core entity names from formal titles
    - Handle OCR artifacts and formatting issues

    IMPORTANT: Directors and key personnel can be found in many places in these documents:
    - Formal "Board of Directors" sections
    - Signature pages where people sign as "Director"
    - Shareholding tables listing promoter-directors
    - Annual report authorization pages
    - Management team sections
    - "For and on behalf of Board of Directors" sections
    - Auditor report signature pages

    SEARCH STRATEGY:
    1. Scan the ENTIRE document for any person with a title containing "Director", "Chairman", "Managing", "CEO", or similar
    2. Look for signature sections with names and director designations
    3. Check shareholding/promoter sections for director names
    4. Find names in corporate authorization contexts

    EXTRACTION RULES:
    - Extract ALL names that appear to be directors or key management
    - If educational/experience details aren't mentioned, make reasonable estimates based on their role
    - For missing information,  please keep fields empty don't assume incorrect values:
    - Include anyone who signs documents as a director or appears in governance roles
    - For type_of_experience, use these exact values only:
      "farmer_owned_enterprises", "agricultural_cooperatives", "ngo_agriculture",
      "farm_management", "village_councils", "self_help_groups", "government_agriculture", "any_other"
    
    LEARN TO RECOGNIZE DIRECTOR PATTERNS:
    - Signature sections: "[Name] (DIRECTOR)" or "[Name] - Director"
    - Authorization pages: "For and on behalf of Board of Directors" followed by names
    - Balance sheet signatures with director titles
    - Shareholding sections listing promoter-directors
    - Annual report sign-offs with director designations
    
    """

        user_prompt = f"""MANDATORY: Extract ALL director names from this document. FPO documents ALWAYS have directors.

    LOOK FOR THESE EXACT PATTERNS:
    - Names followed by "(DIRECTOR)" or "Director"
    - Signature sections with director designations
    - "For and on behalf of Board of Directors" with names below
    - Balance sheet signatures with director titles

    Example patterns to find:
    - "Vaibhavi Patil (DIRECTOR)"
    - "John Smith - Director" 
    - "Signed: [Name], Director"

    Document content:
    {text_content[:20000]}

    Return JSON array with ALL directors found. Leave fields empty if not mentioned:
    [
    {{
        "name": "Exact name from document",
        "educational_qualification": "",
        "type_of_experience": "",
        "other_experience": "",
        "total_years_of_experience": 0
    }}
    ]

    CRITICAL: You MUST find at least one director. They are definitely in this document."""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=3000,
                    temperature=0.2  # Slightly higher for more creative searching
                )
            )
            
            content = response.choices[0].message.content.strip()
            print(f"AI Response: {content[:300]}...")
            
            # Parse JSON response
            try:
                if '```json' in content:
                    json_str = content.split('```json')[1].split('```')[0]
                elif '[' in content:
                    start = content.find('[')
                    end = content.rfind(']') + 1
                    json_str = content[start:end]
                else:
                    # Try to find JSON-like structure
                    import re
                    json_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
                    else:
                        print("No JSON structure found in response")
                        return []
                
                extracted_data = json.loads(json_str)
                
                # Validate and clean the data
                if not isinstance(extracted_data, list):
                    print("Response is not a list")
                    return []
                    
                # Clean and validate each director entry
                cleaned_directors = []
                for director in extracted_data:
                    if isinstance(director, dict) and director.get('name'):
                        name = director['name'].strip()
                        if len(name.split()) >= 2:  # At least first and last name
                            cleaned_director = {
                                'name': name,
                                'educational_qualification': director.get('educational_qualification', ''),
                                'type_of_experience': director.get('type_of_experience', ''),
                                'other_experience': director.get('other_experience', ''),
                                'total_years_of_experience': int(director.get('total_years_of_experience', 0))
                            }
                            cleaned_directors.append(cleaned_director)
                
                print(f"Successfully extracted {len(cleaned_directors)} directors")
                for i, director in enumerate(cleaned_directors):
                    print(f"  {i+1}. {director['name']}")
                
                return cleaned_directors
                
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}")
                print(f"Raw content: {content}")
                return []
                
        except Exception as e:
            print(f"Director extraction failed: {e}")
            return []
   
    def save_board_director_details(self, fpo_id, director_data, financial_year=None, text_content=""):
        """Save board director details to database"""
        if not fpo_id or not director_data:
            print("No director data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            print(f"Saving board director details for FPO: {fpo.name}")
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            # Get yearly submission
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Clear existing directors
            yearly_submission.board_directors.all().delete()
            
            # Save new directors
            saved_count = 0
            for director in director_data:
                try:
                    # Validate required fields before saving
                    name = director.get('name', 'Unknown Director')[:200]
                    if not name or name == 'Unknown Director':
                        name = f"Director {saved_count + 1}"
                    
                    educational_qualification = director.get('educational_qualification', 'Not specified')[:500]
                    type_of_exp = validate_and_map_enum(
                        'type_of_experience',
                        director.get('type_of_experience'),
                        'any_other'
                    )
                    total_experience = max(0, int(director.get('total_years_of_experience', 0)))  # Ensure non-negative
                    
                    BoardDirectorProfile.objects.create(
                        yearly_submission=yearly_submission,
                        name=name,
                        educational_qualification=educational_qualification,
                        type_of_experience=type_of_exp,
                        other_experience=director.get('other_experience', '')[:300],
                        total_years_of_experience=total_experience
                    )
                    saved_count += 1
                except Exception as e:
                    print(f"Error saving director {director.get('name', 'Unknown')}: {e}")
            
            print(f"Saved {saved_count} board directors")
            return yearly_submission
            
        except Exception as e:
            print(f"Error saving board director details: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def extract_fpo_details(self, text_content):
        """
        Extract FPO details for FPODetailsSubmission model
        """
        system_prompt = """You are a data extraction specialist for Indian FPO documents.

    TASK: Extract and clean organizational details with perfect accuracy.

    TEXT CLEANING RULES:
        - Remove document headers/prefixes from company names
        - Clean location names (remove trailing text after line breaks)
        - Extract core entity names from formal titles
        - Handle OCR artifacts and formatting issues

    EXTRACTION RULES:
    1. Extract only what is explicitly stated in the document
    2. Leave fields empty ("" or 0) if information is not found
    3. Do NOT make assumptions or provide default values
    4. Use exact text from document for names and addresses
    5. For dates: use YYYY-MM-DD format only if clearly stated
    6. For numbers: extract only if explicitly mentioned
    7. For ENUM fields, use these exact values only:
       - type_of_producer_organization: "producer_company", "co_operative_society", "non_profit_society", "trust", "section_8_company"
       - type_of_fpo: "inputs_and_output", "inputs_or_output", "high_capacity", "low_capacity"
       - type_of_promoting_agency: "ngo", "trusts", "cooperatives", "corporate_wings", "state_govt", "kvks", "farmer_federations", "commodity_boards", "big_farmer_companies", "others"
    
    
    RECOGNIZE ORGANIZATIONAL INFO PATTERNS:
    - Document headers/letterheads for company names
    - Balance sheet headers for registration details
    - Footer sections containing CIN numbers
    - Address blocks in letterheads or contact sections
    - Date patterns near incorporation/commencement references

    """

        user_prompt = f"""Extract FPO organizational details from this document:

    {text_content[:20000]}

    Find these specific details and return JSON (leave empty if not found):

    BASIC INFO:
    - name_of_producer_organization: Legal name of the FPO/company
    - registered_address: Full registered office address
    - district: District name where registered
    - state: State name where registered
    - type_of_producer_organization: Type like "Producer Company", "Cooperative", etc.
    - date_of_incorporation: Date when company was incorporated (YYYY-MM-DD)
    - date_of_commencement: Date when business operations started (YYYY-MM-DD)
    - age_of_fpo_years: How many years old the FPO is
    - type_of_fpo: Business type like "Input Supply", "Output Marketing", etc.

    MEMBERSHIP DATA:
    - size_of_fpo_fy_23_24: Number of members in FY 2023-24
    - size_of_fpo_fy_22_23: Number of members in FY 2022-23  
    - size_of_fpo_fy_21_22: Number of members in FY 2021-22
    - farmers_transacted: Number of farmers who did business with FPO
    - women_members: Number of female members
    - target_size_of_fpo: Target number of members

    STRUCTURE & SUPPORT:
    - deals_through_pgs_figs: Does FPO work through Producer Groups? (true/false)
    - num_pgs_figs: Number of Producer Groups
    - supported_by_promoting_agency: Is there a promoting agency? (true/false)
    - promoting_agency_name: Name of promoting agency
    - type_of_promoting_agency: Type like "NGO", "Government", etc.
    - other_promoting_agency_type: Other type if not standard
    - received_grants: Has FPO received grants? (true/false)
    - grant_making_organization: Name of grant provider

    Return JSON:
    {{
    "name_of_producer_organization": "",
    "registered_address": "",
    "district": "",
    "state": "",
    "type_of_producer_organization": "",
    "date_of_incorporation": "",
    "date_of_commencement": "",
    "age_of_fpo_years": 0,
    "type_of_fpo": "",
    "size_of_fpo_fy_23_24": 0,
    "size_of_fpo_fy_22_23": 0,
    "size_of_fpo_fy_21_22": 0,
    "farmers_transacted": 0,
    "women_members": 0,
    "target_size_of_fpo": 0,
    "deals_through_pgs_figs": null,
    "num_pgs_figs": 0,
    "supported_by_promoting_agency": null,
    "promoting_agency_name": "",
    "type_of_promoting_agency": "",
    "other_promoting_agency_type": "",
    "received_grants": null,
    "grant_making_organization": ""
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            
            print(f"Extracted FPO details: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            return {}
        except Exception as e:
            print(f"FPO details extraction failed: {e}")
            return {}

    def save_fpo_details(self, fpo_id, fpo_data, financial_year=None, text_content=""):
        """Save FPO details to database with empty values for missing data"""
        if not fpo_id or not fpo_data:
            print("No FPO data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            print(f"Saving FPO details for: {fpo.name}")
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)

            # Get yearly submission
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Parse dates safely
            def parse_date_safe(date_str):
                if not date_str:
                    return None
                try:
                    from datetime import datetime
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    return None
            
            # Convert boolean strings to actual booleans
            def parse_bool_safe(value):
                if value is None or value == "":
                    return None
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ['true', 'yes', '1']
                return None
            
            # Prepare data with proper type conversion and empty handling
            defaults = {
                'name_of_producer_organization': fpo_data.get('name_of_producer_organization', '')[:500],
                'registered_address': fpo_data.get('registered_address', '')[:1000],
                'district': fpo_data.get('district', '')[:100],
                'state': fpo_data.get('state', '')[:100],
                'type_of_producer_organization': validate_and_map_enum(
                    'type_of_producer_organization',
                    fpo_data.get('type_of_producer_organization'),
                    'producer_company'
                ),
                'date_of_incorporation': parse_date_safe(fpo_data.get('date_of_incorporation')),
                'date_of_commencement': parse_date_safe(fpo_data.get('date_of_commencement')),
                'age_of_fpo_years': float(fpo_data.get('age_of_fpo_years', 0)) or 0.0,
                'type_of_fpo': validate_and_map_enum(
                    'type_of_fpo',
                    fpo_data.get('type_of_fpo'),
                    'inputs_and_output'
                ),
                'size_of_fpo_fy_23_24': int(fpo_data.get('size_of_fpo_fy_23_24', 0)) or None,
                'size_of_fpo_fy_22_23': int(fpo_data.get('size_of_fpo_fy_22_23', 0)) or None,
                'size_of_fpo_fy_21_22': int(fpo_data.get('size_of_fpo_fy_21_22', 0)) or None,
                'farmers_transacted': int(fpo_data.get('farmers_transacted', 0)) or None,
                'women_members': int(fpo_data.get('women_members', 0)) or None,
                'target_size_of_fpo': int(fpo_data.get('target_size_of_fpo', 0)) or None,
                'deals_through_pgs_figs': parse_bool_safe(fpo_data.get('deals_through_pgs_figs')),
                'num_pgs_figs': int(fpo_data.get('num_pgs_figs', 0)) or None,
                'supported_by_promoting_agency': parse_bool_safe(fpo_data.get('supported_by_promoting_agency')),
                'promoting_agency_name': fpo_data.get('promoting_agency_name', '')[:200],
                'type_of_promoting_agency': validate_and_map_enum(
                    'type_of_promoting_agency',
                    fpo_data.get('type_of_promoting_agency'),
                    'others'
                ),
                'other_promoting_agency_type': fpo_data.get('other_promoting_agency_type', '')[:200],
                'received_grants': parse_bool_safe(fpo_data.get('received_grants')),
                'grant_making_organization': fpo_data.get('grant_making_organization', '')[:200],
            }
            
            # Handle required fields that need fallbacks for model constraints
            if not defaults['date_of_incorporation']:
                from datetime import datetime
                defaults['date_of_incorporation'] = datetime(1900, 1, 1).date()
            if not defaults['date_of_commencement']:
                defaults['date_of_commencement'] = defaults['date_of_incorporation']
            
            # Create or update FPO details
            obj, created = FPODetailsSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated existing FPODetailsSubmission")
            else:
                print("Created new FPODetailsSubmission")
            
            # Log saved data (only non-empty values)
            print("Saved FPO details:")
            for key, value in defaults.items():
                if value and str(value) not in ['0', '0.0', 'False', 'producer_company', 'inputs_and_output']:
                    print(f"  {key}: {str(value)[:100]}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving FPO details: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def extract_governance_details(self, text_content):
        """Extract governance details for GovernanceSubmission model"""
        
        system_prompt = """Extract and clean governance information from FPO documents.


    TEXT CLEANING RULES:
    - Remove document headers/prefixes from company names
    - Clean location names (remove trailing text after line breaks)
    - Extract core entity names from formal titles
    - Handle OCR artifacts and formatting issues

    RULES:
    - Extract only explicitly stated information
    - Leave fields empty/zero if not found
    - Do not make assumptions
    - For minutes_maintenance field, use these exact values only:
      "detailed_compliant", "detailed_not_updated", "sketchy_quality", "not_maintained"
    - For second_line_management field, use these exact values only:
      "ceo_accounts_two_managers", "ceo_accounts_one_manager", "ceo_with_accounts", "only_ceo", "no_ceo"""

        user_prompt = f"""Find governance details in this FPO document:

    {text_content[:20000]}

    LOOK FOR:
    - annual_general_body_meetings: Number of AGM meetings held
    - bod_meetings_last_financial_year: Number of Board of Directors meetings
    - minutes_maintenance: How meeting minutes are maintained ("detailed_compliant", "detailed_not_updated", "sketchy_quality", "not_maintained")
    - num_bods: Total number of Board of Directors
    - num_women_bods: Number of women directors on board
    - second_line_management: Type of second line management ("ceo_accounts_two_managers", "ceo_accounts_one_manager", "ceo_with_accounts", "only_ceo", "no_ceo")

    Return JSON:
    {{
    "annual_general_body_meetings": 0,
    "bod_meetings_last_financial_year": 0,
    "minutes_maintenance": "",
    "num_bods": 0,
    "num_women_bods": 0,
    "second_line_management": ""
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            print(f"Extracted governance details: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"Governance extraction failed: {e}")
            return {}

    def save_governance_details(self, fpo_id, governance_data, financial_year=None, text_content=""):
        """Save governance details to database"""
        if not fpo_id or not governance_data:
            print("No governance data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)

            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            defaults = {
                'annual_general_body_meetings': int(governance_data.get('annual_general_body_meetings', 0)) or 0,
                'bod_meetings_last_financial_year': int(governance_data.get('bod_meetings_last_financial_year', 0)) or 0,
                'minutes_maintenance': validate_and_map_enum(
                    'minutes_maintenance',
                    governance_data.get('minutes_maintenance'),
                    'detailed_compliant'
                ),
                'num_bods': int(governance_data.get('num_bods', 0)) or 0,
                'num_women_bods': int(governance_data.get('num_women_bods', 0)) or 0,
                'second_line_management': validate_and_map_enum(
                    'second_line_management',
                    governance_data.get('second_line_management'),
                    'only_ceo'
                ),
            }
            
            obj, created = GovernanceSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated GovernanceSubmission")
            else:
                print("Created GovernanceSubmission")
            
            return yearly_submission
                
        except Exception as e:
            print(f"Error saving governance details: {e}")
            return None

    def extract_ceo_profile_details(self, text_content):
        """Extract CEO profile for CEOProfileSubmission model"""
        
        system_prompt = """Extract and clean CEO/Manager profile from FPO documents.

    TEXT CLEANING RULES:
    - Remove document headers/prefixes from company names
    - Clean location names (remove trailing text after line breaks)
    - Extract core entity names from formal titles
    - Handle OCR artifacts and formatting issues

    RULES:
    - Extract only explicitly stated information
    - Leave fields empty if not found
    - Look for CEO, Manager, or key management person details
    - For type_of_experience, use these exact values only:
      "agricultural_cooperatives", "farmer_owned_enterprises", "ngo_agriculture",
      "farm_management", "village_councils", "self_help_groups",
      "government_agriculture", "business_functions", "any_other"""

        user_prompt = f"""Find CEO/Manager profile in this FPO document:

    {text_content[:20000]}

    LOOK FOR:
    - name: Name of CEO/Manager/key management person
    - qualification: Educational qualifications/degrees
    - type_of_experience: Type ("agricultural_cooperatives", "farmer_owned_enterprises", "ngo_agriculture", "farm_management", "village_councils", "self_help_groups", "government_agriculture", "business_functions", "any_other")
    - other_experience_type: Additional experience details if mentioned
    - total_years_of_experience: Years of relevant experience

    Return JSON:
    {{
    "name": "",
    "qualification": "",
    "type_of_experience": "",
    "other_experience_type": "",
    "total_years_of_experience": 0
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            print(f"Extracted CEO profile: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"CEO profile extraction failed: {e}")
            return {}

    def save_ceo_profile_details(self, fpo_id, ceo_data, financial_year=None, text_content=""):
        """Save CEO profile to database"""
        if not fpo_id or not ceo_data:
            print("No CEO data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            defaults = {
                'name': ceo_data.get('name', ''),
                'qualification': ceo_data.get('qualification', ''),
                'type_of_experience': validate_and_map_enum(
                    'type_of_experience',
                    ceo_data.get('type_of_experience'),
                    'any_other'
                ),
                'other_experience_type': ceo_data.get('other_experience_type', ''),
                'total_years_of_experience': int(ceo_data.get('total_years_of_experience', 0)) or 0,
            }
            
            obj, created = CEOProfileSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated CEOProfileSubmission")
            else:
                print("Created CEOProfileSubmission")
            
            return yearly_submission
                
        except Exception as e:
            print(f"Error saving CEO profile: {e}")
            return None
    
    def extract_financial_year_from_text(self, text_content):
        raise "Invalid finance time"

    def extract_business_operations_details(self, text_content):
        """Extract business operations for BusinessOperationsSubmission model"""
        
        system_prompt = """Extract business operations information from FPO documents.

    FOCUS AREAS:
    1. Price volatility mentions
    2. Input supply details (timing, pricing, accessibility)
    3. Infrastructure facilities and services
    4. Value addition capabilities
    5. Support services provided

    EXTRACTION RULES:
    - Extract only explicitly mentioned information
    - Use "true/false" for boolean capabilities
    - Leave empty if not found
    - For enum fields, use these exact values only:
      - price_volatility_of_products: "highly_volatile_fpo_risk", "msp_fpo_risk", "partial_hedge", "well_hedged", "not_applicable"
      - availability_of_inputs_timeliness: "30_days_prior", "20_days_prior", "15_days_prior", "7_days_prior", "not_applicable"
      - availability_of_inputs_price_affordability: "10_15_percent_less", "5_10_percent_less", "3_5_percent_less", "1_3_percent_less", "not_applicable"
      - availability_of_inputs_place: "3_km_available", "6_km_available", "10_km_available", "not_within_10_km", "not_applicable"""

        user_prompt = f"""Extract business operations data from this FPO document:

    {text_content[:20000]}

    LOOK FOR:
    - Price volatility: Market price volatility ("highly_volatile_fpo_risk", "msp_fpo_risk", "partial_hedge", "well_hedged", "not_applicable")
    - Accessibility: Distance/reach percentages
    - Input availability:
      - Timing ("30_days_prior", "20_days_prior", "15_days_prior", "7_days_prior", "not_applicable")
      - Affordability ("10_15_percent_less", "5_10_percent_less", "3_5_percent_less", "1_3_percent_less", "not_applicable")
      - Location ("3_km_available", "6_km_available", "10_km_available", "not_within_10_km", "not_applicable")
    - Collection centers: Distance mentioned
    - Facilities: Electronic weighing, transportation, storage, cleaning, grading and sorting, chilling, packaging, labelling, processing, quality check
    - Services: Soil testing, custom hiring centers, contract farming, advisory services, credit facilities

    Return JSON:
    {{
    "price_volatility_of_products": "",
    "accessibility_percentage": 0.0,
    "availability_of_inputs_timeliness": "",
    "availability_of_inputs_price_affordability": "",
    "availability_of_inputs_place": "",
    "distance_of_output_collection_centres": "",
    "electronic_weighing_machines": null,
    "transportation_facility": null,
    "storage": null,
    "cleaning": null,
    "grading_and_sorting": null,
    "chilling": null,
    "packaging": null,
    "labelling": null,
    "processing": null,
    "quality_check": null,
    "soil_testing_facility": null,
    "custom_hiring_centers": null,
    "contract_farming": null,
    "advisory_services": null,
    "credit_facilities": null
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            print(f"Extracted business operations: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"Business operations extraction failed: {e}")
            return {}

    def save_business_operations_details(self, fpo_id, operations_data, financial_year=None, text_content=""):
        """Save business operations to database"""
        if not fpo_id or not operations_data:
            print("No business operations data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Convert and validate data
            def parse_bool_safe(value):
                if value is None or value == "":
                    return None
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ['true', 'yes', '1']
                return None
            
            defaults = {
                'price_volatility_of_products': validate_and_map_enum(
                    'price_volatility_of_products',
                    operations_data.get('price_volatility_of_products'),
                    'not_applicable'
                ),
                'accessibility_percentage': float(operations_data.get('accessibility_percentage', 0)) or None,
                'availability_of_inputs_timeliness': validate_and_map_enum(
                    'availability_of_inputs_timeliness',
                    operations_data.get('availability_of_inputs_timeliness'),
                    'not_applicable'
                ),
                'availability_of_inputs_price_affordability': validate_and_map_enum(
                    'availability_of_inputs_price_affordability',
                    operations_data.get('availability_of_inputs_price_affordability'),
                    'not_applicable'
                ),
                'availability_of_inputs_place': validate_and_map_enum(
                    'availability_of_inputs_place',
                    operations_data.get('availability_of_inputs_place'),
                    'not_applicable'
                ),
                'distance_of_output_collection_centres': operations_data.get('distance_of_output_collection_centres', ''),
                'electronic_weighing_machines': parse_bool_safe(operations_data.get('electronic_weighing_machines')),
                'transportation_facility': parse_bool_safe(operations_data.get('transportation_facility')),
                'storage': parse_bool_safe(operations_data.get('storage')),
                'cleaning': parse_bool_safe(operations_data.get('cleaning')),
                'grading_and_sorting': parse_bool_safe(operations_data.get('grading_and_sorting')),
                'chilling': parse_bool_safe(operations_data.get('chilling')),
                'packaging': parse_bool_safe(operations_data.get('packaging')),
                'labelling': parse_bool_safe(operations_data.get('labelling')),
                'processing': parse_bool_safe(operations_data.get('processing')),
                'quality_check': parse_bool_safe(operations_data.get('quality_check')),
                'soil_testing_facility': parse_bool_safe(operations_data.get('soil_testing_facility')),
                'custom_hiring_centers': parse_bool_safe(operations_data.get('custom_hiring_centers')),
                'contract_farming': parse_bool_safe(operations_data.get('contract_farming')),
                'advisory_services': parse_bool_safe(operations_data.get('advisory_services')),
                'credit_facilities': parse_bool_safe(operations_data.get('credit_facilities')),
            }
            
            obj, created = BusinessOperationsSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated BusinessOperationsSubmission")
            else:
                print("Created BusinessOperationsSubmission")
            
            # Log saved data
            print("Saved business operations:")
            for key, value in defaults.items():
                if value and str(value) not in ['not_applicable', 'False']:
                    print(f"  {key}: {str(value)[:100]}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving business operations: {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_compliance_details(self, text_content):
        """Extract compliance details for ComplianceDetailsSubmission model"""
        
        system_prompt = """Extract regulatory compliance information from FPO documents with maximum accuracy.

    CRITICAL SEARCH AREAS:
    1. Registration details (Act, date, place, number)
    2. Incorporation information 
    3. Commencement details
    4. GST registration
    5. PAN and TAN numbers
    6. CIN (Corporate Identification Number)

    PATTERNS TO IDENTIFY:
    - "Registered under [Act Name]"
    - "CIN: [number]" or "Corporate Identity Number"
    - "Date of Incorporation: [date]"
    - "GST No:" or "GSTIN:"
    - "PAN: [10-digit alphanumeric]"
    - "TAN: [10-digit alphanumeric]"
    - Certificate numbers and dates
    - Place names in registration contexts

    EXTRACTION PRECISION:
    - Extract exact dates (DD/MM/YYYY or YYYY-MM-DD)
    - Capture complete registration numbers
    - Identify specific places mentioned
    - Distinguish between different types of registrations"""

        user_prompt = f"""Extract ALL compliance and registration details from this FPO document:

    {text_content}

    FIND THESE SPECIFIC DETAILS:

    REGISTRATION:
    - Act under which registered (company_act/cooperative_societies_act/other)
    - Registration date, place, and number

    INCORPORATION:
    - Incorporation date, place, and registration number
    - CIN number if mentioned

    COMMENCEMENT:
    - Business commencement date, place, and number

    GST:
    - GST registration date, place, and GST number

    TAX NUMBERS:
    - PAN (Permanent Account Number) - 10 characters
    - TAN (Tax Deduction Account Number) - 10 characters

    Return JSON with YYYY-MM-DD date format:
    {{
    "act_under_registered": "",
    "date_of_registration": "",
    "place_of_registration": "",
    "registration_no": "",
    "incorporation_date": "",
    "incorporation_place": "",
    "incorporation_reg_no": "",
    "commencement_date": "",
    "commencement_place": "",
    "commencement_reg_no": "",
    "gst_date": "",
    "gst_place": "",
    "gst_reg_no": "",
    "permanent_account_number": "",
    "tax_account_number": ""
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            print(f"Extracted compliance details: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"Compliance extraction failed: {e}")
            return {}

    def save_compliance_details(self, fpo_id, compliance_data, financial_year=None, text_content=""):
        """Save compliance details to database"""
        if not fpo_id or not compliance_data:
            print("No compliance data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Date parsing helper
            def parse_date_safe(date_str):
                if not date_str:
                    return None
                try:
                    # Try different date formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            return datetime.strptime(date_str, fmt).date()
                        except:
                            continue
                    return None
                except:
                    return None
            
            defaults = {
                'act_under_registered': validate_and_map_enum(
                    'act_under_registered',
                    compliance_data.get('act_under_registered'),
                    'company_act'
                ),
                'date_of_registration': parse_date_safe(compliance_data.get('date_of_registration')),
                'place_of_registration': (compliance_data.get('place_of_registration') or '')[:200],
                'registration_no': (compliance_data.get('registration_no') or '')[:100],
                'incorporation_date': parse_date_safe(compliance_data.get('incorporation_date')),
                'incorporation_place': (compliance_data.get('incorporation_place') or '')[:200],
                'incorporation_reg_no': (compliance_data.get('incorporation_reg_no') or '')[:100],
                'commencement_date': parse_date_safe(compliance_data.get('commencement_date')),
                'commencement_place': (compliance_data.get('commencement_place') or '')[:200],
                'commencement_reg_no': (compliance_data.get('commencement_reg_no') or '')[:100],
                'gst_date': parse_date_safe(compliance_data.get('gst_date')),
                'gst_place': (compliance_data.get('gst_place') or '')[:200],
                'gst_reg_no': (compliance_data.get('gst_reg_no') or '')[:100],
                'permanent_account_number': (compliance_data.get('permanent_account_number') or '')[:10],
                'tax_account_number': (compliance_data.get('tax_account_number') or'')[:10],
            }
            
            # Handle required fields with fallbacks
            if not defaults['date_of_registration']:
                defaults['date_of_registration'] = datetime(1900, 1, 1).date()
            if not defaults['permanent_account_number']:
                defaults['permanent_account_number'] = 'NOT_FOUND'
            
            obj, created = ComplianceDetailsSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated ComplianceDetailsSubmission")
            else:
                print("Created ComplianceDetailsSubmission")
            
            # Log saved data
            print("Saved compliance details:")
            for key, value in defaults.items():
                if value and str(value) not in ['companies_act', 'NOT_FOUND'] and str(value) != '1900-01-01':
                    print(f"  {key}: {str(value)[:100]}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving compliance details: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def extract_sustainable_activities_details(self, text_content):
        """Extract sustainable activities for SustainableActivitiesSubmission model"""
        
        system_prompt = """Extract sustainability and environmental activities from FPO documents.

    SEARCH FOR THESE SPECIFIC ACTIVITIES:
    1. Climate-resilient seeds distribution
    2. Organic/bio manure/fertilizer supply
    3. Composting units establishment
    4. Drip/sprinkler irrigation systems
    5. Pest/disease alert services
    6. Weather advisory services
    7. Agricultural residue to bio-CNG supply
    8. Organic farming training programs
    9. Solar panel installations
    10. Rainwater harvesting systems

    KEYWORDS TO IDENTIFY:
    - "climate resilient", "drought resistant", "heat tolerant seeds"
    - "organic manure", "bio fertilizer", "vermicompost"
    - "composting unit", "compost facility"
    - "drip irrigation", "sprinkler system", "micro irrigation"
    - "pest alert", "disease warning", "IPM"
    - "weather advisory", "meteorological", "agro-meteorology"
    - "agricultural residue", "bio-CNG", "biomass"
    - "organic farming training", "sustainable agriculture"
    - "solar panels", "renewable energy", "photovoltaic"
    - "rainwater harvesting", "water conservation"

    Return true/false for each activity based on evidence found."""

        user_prompt = f"""Analyze this FPO document for sustainable activities:

    {text_content[:20000]}

    Look for evidence of these 10 activities (return true if mentioned, false if not):

    1. Climate-resilient seeds provided to farmers
    2. Organic/bio manure/fertilizers supplied to farmers  
    3. Composting units established at FPO level
    4. Drip/sprinkler irrigation provided to farmers
    5. Pest/disease alerts sent to farmers
    6. Weather advisories provided to farmers
    7. Agricultural residue supplied to bio-CNG plants
    8. Organic farming training given to farmers
    9. Solar panels installed at FPO level
    10. Rainwater harvesting established at FPO level

    Return JSON:
    {{
    "climate_resilient_seeds_to_farmers": false,
    "organic_bio_manure_fertilizers_to_farmers": false,
    "composting_units_at_fpo_level": false,
    "drip_sprinkler_irrigation_to_farmers": false,
    "pest_disease_alerts_to_farmers": false,
    "weather_advisories_to_farmers": false,
    "supplying_agricultural_residue_to_bio_cng_gas_plants": false,
    "training_on_organic_farming_to_farmers": false,
    "solar_panels_at_fpo_level": false,
    "establishment_of_rainwater_harvesting_at_fpo_level": false
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1500,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            extracted_data = json.loads(json_str)
            print(f"Extracted sustainable activities: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"Sustainable activities extraction failed: {e}")
            return {}

    def save_sustainable_activities_details(self, fpo_id, activities_data, financial_year=None, text_content=""):
        """Save sustainable activities to database"""
        if not fpo_id or not activities_data:
            print("No sustainable activities data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Convert to boolean values
            def parse_bool_required(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ['true', 'yes', '1']
                return False  # Default to False for required boolean fields
            
            defaults = {
                'climate_resilient_seeds_to_farmers': parse_bool_required(activities_data.get('climate_resilient_seeds_to_farmers')),
                'organic_bio_manure_fertilizers_to_farmers': parse_bool_required(activities_data.get('organic_bio_manure_fertilizers_to_farmers')),
                'composting_units_at_fpo_level': parse_bool_required(activities_data.get('composting_units_at_fpo_level')),
                'drip_sprinkler_irrigation_to_farmers': parse_bool_required(activities_data.get('drip_sprinkler_irrigation_to_farmers')),
                'pest_disease_alerts_to_farmers': parse_bool_required(activities_data.get('pest_disease_alerts_to_farmers')),
                'weather_advisories_to_farmers': parse_bool_required(activities_data.get('weather_advisories_to_farmers')),
                'supplying_agricultural_residue_to_bio_cng_gas_plants': parse_bool_required(activities_data.get('supplying_agricultural_residue_to_bio_cng_gas_plants')),
                'training_on_organic_farming_to_farmers': parse_bool_required(activities_data.get('training_on_organic_farming_to_farmers')),
                'solar_panels_at_fpo_level': parse_bool_required(activities_data.get('solar_panels_at_fpo_level')),
                'establishment_of_rainwater_harvesting_at_fpo_level': parse_bool_required(activities_data.get('establishment_of_rainwater_harvesting_at_fpo_level')),
            }
            
            obj, created = SustainableActivitiesSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated SustainableActivitiesSubmission")
            else:
                print("Created SustainableActivitiesSubmission")
            
            # Log saved activities (only True values)
            true_activities = [key for key, value in defaults.items() if value]
            if true_activities:
                print(f"Sustainable activities found: {len(true_activities)}")
                for activity in true_activities:
                    print(f"  ✓ {activity}")
            else:
                print("No sustainable activities detected")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving sustainable activities: {e}")
            import traceback
            traceback.print_exc()
            return None
            
            
    def extract_processes_systems_details(self, text_content):
        """Extract processes and systems for ProcessesSystemsSubmission model"""
        
        system_prompt = """Extract internal processes and systems information from FPO documents.

    SEARCH FOR:
    1. Accounting/MIS systems
    2. Insurance coverage for stock/inventory
    3. Credit record status
    4. Statutory compliance filing status
    5. Books and records maintenance
    6. Stock reconciliation practices
    7. Board meeting penalties

    KEYWORDS TO IDENTIFY:
    - "accounting software", "MIS", "computerized", "manual books"
    - "insurance policy", "stock insurance", "inventory coverage"
    - "credit rating", "credit history", "default", "repayment"
    - "statutory filing", "compliance", "returns filed"
    - "books updated", "records maintained", "accounting records"
    - "stock reconciliation", "physical verification"
    - "penalty", "board meeting", "attendance"

    EXACT ENUM VALUES TO USE:
    - accounts_and_mis: "no_mis", "ms_office_tools", "tally_no_digital", "software_digital"
    - insurance_of_stock: "no_insurance", "less_than_50_fire", "50_fire_theft", "100_fire_theft"
    - credit_record_of_fpo: "no_credit_history", "multiple_delays", "one_delay", "no_delays"
    - statutory_fillings: "delays_not_filled", "multiple_delays_filled", "few_delays_filled", "no_delays"
    - books_and_records_up_to_date: "processes_systems", "weekly_updated", "lag_2_3_days", "current"
    - reconciliation_of_stocks: "absent_annual", "2_4_times_year", "monthly", "every_15_days"""

        user_prompt = f"""Extract processes and systems data from this FPO document:

    {text_content[:20000]}

    Determine status for each area:

    1. Accounts & MIS: "no_mis", "ms_office_tools", "tally_no_digital", "software_digital"
    2. Insurance of stock: "no_insurance", "less_than_50_fire", "50_fire_theft", "100_fire_theft"
    3. Credit record: "no_credit_history", "multiple_delays", "one_delay", "no_delays"
    4. Statutory fillings: "delays_not_filled", "multiple_delays_filled", "few_delays_filled", "no_delays"
    5. Books and records: "processes_systems", "weekly_updated", "lag_2_3_days", "current"
    6. Stock reconciliation: "absent_annual", "2_4_times_year", "monthly", "every_15_days"
    7. Board meeting penalties: true/false

    Return JSON:
    {{
    "accounts_and_mis": "",
    "insurance_of_stock": "",
    "credit_record_of_fpo": "",
    "statutory_fillings": "",
    "books_and_records_up_to_date": "",
    "reconciliation_of_stocks": "",
    "penalties_levied_board_meeting": false
    }}"""

        try:
            response = self._api_call_with_retry(
                lambda: self.openai_client.chat.completions.create(
                    model=self.extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1500,
                    temperature=0.1
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0]
            elif '{' in content:
                json_str = content[content.find('{'):content.rfind('}')+1]
            else:
                json_str = content
            
            json_str = json_str.replace('<|begin_of_box|>', '').strip()
            
            extracted_data = json.loads(json_str)
            print(f"Extracted processes systems: {json.dumps(extracted_data, indent=2)}")
            return extracted_data
            
        except Exception as e:
            print(f"Processes systems extraction failed: {e}")
            return {}

    def save_processes_systems_details(self, fpo_id, systems_data, financial_year=None, text_content=""):
        """Save processes and systems to database"""
        if not fpo_id or not systems_data:
            print("No processes systems data to save")
            return None
            
        try:
            fpo = FPO.objects.get(id=fpo_id)
            
            # Use provided financial_year or extract from text_content if not provided
            if financial_year is None:
                financial_year = self.extract_financial_year_from_text(text_content)
            yearly_submission, created = YearlySubmission.objects.get_or_create(
                fpo=fpo,
                financial_year=financial_year,
                defaults={'status': 'draft', 'submitted_by': None}
            )
            
            # Parse boolean for penalties
            def parse_bool_required(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ['true', 'yes', '1']
                return False
            
            defaults = {
                'accounts_and_mis': validate_and_map_enum(
                    'accounts_and_mis',
                    systems_data.get('accounts_and_mis'),
                    'ms_office_tools'
                ),
                'insurance_of_stock': validate_and_map_enum(
                    'insurance_of_stock',
                    systems_data.get('insurance_of_stock'),
                    'no_insurance'
                ),
                'credit_record_of_fpo': validate_and_map_enum(
                    'credit_record_of_fpo',
                    systems_data.get('credit_record_of_fpo'),
                    'no_credit_history'
                ),
                'statutory_fillings': validate_and_map_enum(
                    'statutory_fillings',
                    systems_data.get('statutory_fillings'),
                    'no_delays'
                ),
                'books_and_records_up_to_date': validate_and_map_enum(
                    'books_and_records_up_to_date',
                    systems_data.get('books_and_records_up_to_date'),
                    'current'
                ),
                'reconciliation_of_stocks': validate_and_map_enum(
                    'reconciliation_of_stocks',
                    systems_data.get('reconciliation_of_stocks'),
                    'monthly'
                ),
                'penalties_levied_board_meeting': parse_bool_required(systems_data.get('penalties_levied_board_meeting')),
            }
            
            obj, created = ProcessesSystemsSubmission.objects.get_or_create(
                yearly_submission=yearly_submission,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
                print("Updated ProcessesSystemsSubmission")
            else:
                print("Created ProcessesSystemsSubmission")
            
            # Log saved data
            print("Saved processes systems:")
            for key, value in defaults.items():
                if str(value) not in ['manual', 'no', 'average', 'up_to_date', 'periodic', 'False']:
                    print(f"  {key}: {value}")
            
            return yearly_submission
                    
        except Exception as e:
            print(f"Error saving processes systems: {e}")
            import traceback
            traceback.print_exc()
            return None
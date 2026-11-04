import math
from datetime import date
from decimal import Decimal
from fpo.models import (
    FPOType,
    MinutesMaintenanceType,
    PriceAffordabilityType,
    AccountsMISType,
    InsuranceStockType,
    CreditRecordType,
    StatutoryFillingsType,
    BooksRecordsType,
    ReconciliationStocksType,
)


class FPOScoreCalculator:
    """
    Calculates the composite FPO score (0-100) for a YearlySubmission.
    Usage:
        calc = FPOScoreCalculator(submission)
        score = calc.calculate_total_score()
    """

    def __init__(self, submission):
        self.sub = submission
        # Initialize section scores to
        # prevent AttributeError
        self._section_scores = {"governance": 0, "business": 0, "process": 0, "financial": 0}

    def format_indicator_value(self, field_name, enum_value, raw_value=None):
        """Convert enum values to human-readable sentences"""

        # Concluding statements that must be consistent for frontend display
        if field_name == "size_achievement":
            if raw_value is None:
                return "Target/size data not available"

            try:
                pct = float(raw_value)
            except (TypeError, ValueError):
                return "Target/size data not available"

            pct_str = f"{int(pct)}%" if pct.is_integer() else f"{pct:.1f}%"

            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket in (2, 3):
                return f"FPO has achieved {pct_str} of target size"
            return f"FPO has achieved only {pct_str} of target size"

        if field_name == "active_membership":
            if raw_value is None:
                return "Active membership data not available"

            try:
                pct_str = f"{float(raw_value):.1f}%"
            except (TypeError, ValueError):
                return "Active membership data not available"

            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket in (2, 3):
                return f"Active membership is \"{pct_str}\""
            return f"Active membership is only \"{pct_str}\""

        if field_name == "price_volatility":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket in (2, 3):
                return "Price risk covered through hedging"
            return "Price risk of the commodities is not hedged"

        if field_name == "accessibility":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket == 3:
                return "Inputs are made available to more than 80% of the farmers"
            if score_bucket == 2:
                return "Inputs are made available to upto 80% of the farmers"
            if score_bucket == 1:
                return "Inputs are made available to less than 60% of the farmers"
            return "Inputs are made available to less than 40% of the farmers"

        if field_name == "timeliness":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket == 4:
                return "Inputs are made available 30 days prior to the sowing season"
            if score_bucket == 3:
                return "Inputs are made available 20 days prior to the sowing"
            if score_bucket == 2:
                return "Inputs are made available only 10 days prior to the sowing"
            if score_bucket == 1:
                return "Inputs are made available only 7 days prior to the sowing"
            return "Inputs are not provided to the farmers"

        if field_name == "price_affordability":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket == 4:
                return "Inputs are made available to member farmers at upto 15% less than market price"
            if score_bucket == 3:
                return "Inputs are made available to member farmers at upto 10% less than market price"
            if score_bucket == 2:
                return "Inputs are made available to member farmers at upto 5% less than market price"
            if score_bucket == 1:
                return "Inputs are made available  to member farmers at upto  3% less than market price"
            return "Inputs are not provided to the farmers"

        if field_name == "place":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket in (4, 3):
                return "Inputs are made available within 6 KM of distance for the majority of the farmers"
            if score_bucket in (2, 1):
                return "Inputs are not made available within 6 KM of distance for the majority of the farmers"
            return "Inputs are not provided to the farmers"

        if field_name == "output_collection":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket in (4, 3):
                return "Output collection facility is made available within 6 KM of distance for the majority of the farmers"
            if score_bucket in (2, 1):
                return "Output Collection facility is not made available within 6 KM of distance for the majority of the farmers"
            return "Output collection facility is not provided to the farmers"

        if field_name == "accounts_mis":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket == 3:
                return "A proper digital MIS is maintained for all operational records"
            if score_bucket == 2:
                return "Only accounting operations are managed through Tally"
            return "No software packages are used for maintaining operational records"

        if field_name == "statutory_fillings":
            try:
                score_bucket = int(enum_value)
            except (TypeError, ValueError):
                score_bucket = None

            if score_bucket == 3:
                return "FPO has made no delay in Statutory filings in the last 12 months"
            if score_bucket == 2:
                return "FPO has made only a few delays in statutory filings in the last 12 months"
            return "FPO has made multiple delays in statutory filings in the last 12 months"

        mappings = {
            "institutional_lending_history": {
                "no_history": "FPO has no history of institutional lending in last 2 financial years",
                "at_least_one": "FPO has at least 1 institutional lending in last 2 financial years",
                "repeated_lending": "FPO has history of repeated lending from institutional lenders in last 2 financial years",
            },
            "books_and_records_up_to_date": {
                "current": "Books are updated regularly",
                "lag_2_3_days": "Books are updated with a lag of 2 - 3 days only",
                "weekly_updated": "Books are updated only on a weekly basis",
                "monthly_or_more": "Books are updated only on a monthly basis",
            },
            "reconciliation_of_stocks": {
                "every_15_days": "Reconciliation of stocks is done at least every 15 days",
                "monthly": "Reconciliation of stocks is done every month",
                "2_4_times_year": "Reconciliation of stocks is done only 2 - 4 times a year",
                "absent_annual": "Reconciliation of stocks is not done",
            },
            "statutory_fillings": {
                "delays_not_filled": "FPO has delays in statutory filings in the past 12 months that are not yet filled",
                "multiple_delays_filled": "FPO had multiple delays (>5) in statutory filings over the past 12 months but have been filled as of date",
                "few_delays_filled": "FPO had few delays (<3) in statutory filings over the past 12 months but have been filled as of date",
                "no_delays": "FPO makes no delays in statutory filings",
            },
            "availability_of_output_collection_centres": {
                "A_3_KM_AVAILABLE": "Output Collection Centres are available within 3 KM of distance for majority of farmers",
                "A_6_KM_AVAILABLE": "Output Collection Centres are available within 6 KM of distance for majority of farmers",
                "A_10_KM_AVAILABLE": "Output Collection Centres are available within 10 KM of distance for majority of farmers",
                "NOT_WITHIN_10_KM": "Output Collection Centres are not available within 10 KM of distance for majority of farmers",
                # Add these missing mappings:
                "3_km_available": "Output Collection Centres are available within 3 KM of distance for majority of farmers",
                "6_km_available": "Output Collection Centres are available within 6 KM of distance for majority of farmers",
                "10_km_available": "Output Collection Centres are available within 10 KM of distance for majority of farmers",
                "not_within_10_km": "Output Collection Centres are not available within 10 KM of distance for majority of farmers",
                "not_applicable": "Output collection centres are not available",
            },
            "insurance_of_stock": {
                "no_insurance": "FPO has no insurance coverage for its stock",
                "less_than_50_fire": "Less than 50% of the stock is insured against fire & theft",
                "50_fire_theft": "50% of the stock is insured against fire & theft",
                "100_fire_theft": "100% stock is insured against fire & theft",
            },
            "credit_record_of_fpo": {
                "no_credit_history": "No credit history of the FPO",
                "multiple_delays": "More than one credit record of delays/defaults in the last 3 financial years",
                "one_delay": "Only one credit record of delays/defaults in the last 3 financial years",
                "no_delays": "No record of delays/default",
            },
            "accounts_and_mis": {
                "no_mis": "FPO has no MIS system present for account management",
                "ms_office_tools": "Accounting is managed using basic MS Office tools but not software packages",
                "tally_no_digital": "Accounting is managed by Tally, but no digitalization of other operational records",
                "software_digital": "Software is used for managing accounts with digitalization of MIS",
            },
            "availability_of_inputs_timeliness": {
                "30_days_prior": "Inputs are available to members 30 days prior to the sowing season",
                "20_days_prior": "Inputs are available to members 20 days prior to the sowing season",
                "15_days_prior": "Inputs are available to members 15 days prior to the sowing season",
                "7_days_prior": "Inputs are available to members 7 days prior to the sowing season",
                "not_applicable": "Inputs are not provided to the farmers",
            },
            "availability_of_inputs_price_affordability": {
                "10_15_percent_less": "Inputs are available to member farmers at only 10-15% less than market price",
                "5_10_percent_less": "Inputs are available to member farmers at only 5-10% less than market price",
                "3_5_percent_less": "Inputs are available to member farmers at only 3-5% less than market price",
                "1_3_percent_less": "Inputs are available to member farmers at only 1-3% less than market price",
                "not_applicable": "Input price affordability is not available",
            },
            "availability_of_inputs_place": {
                "3_km_available": "Inputs are available within 3 KM of distance for majority of farmers",
                "6_km_available": "Inputs are available within 6 KM of distance for majority of farmers",
                "10_km_available": "Inputs are available within 10 KM of distance for majority of farmers",
                "not_within_10_km": "Inputs are not available within 10 KM of distance for majority of farmers",
                "not_applicable": "Input location availability is not available",
            },
            "type_of_experience": {
                "farmer_owned_enterprises": "FPO has experience in farmer-owned enterprises",
                "agricultural_cooperatives": "FPO has experience in agricultural cooperatives/farmer producer organizations",
                "ngo_agriculture": "FPO has experience in NGO/non-profit organizations focused on agricultural sector/fisheries/animal husbandry",
                "farm_management": "FPO has experience in farm management",
                "village_councils": "FPO has experience in village councils",
                "self_help_groups": "FPO has experience in self-help groups",
                "government_agriculture": "FPO has experience in government departments of agricultural sector/fisheries/animal husbandry",
                "any_other": "FPO has experience in other areas",
            },
            "price_volatility_of_products": {
                "highly_volatile_fpo_risk": "FPO deals in highly price sensitive/volatile commodities with price risk borne by FPO",
                "msp_fpo_risk": "FPO deals in commodities with MSP but price risk remains on FPO",
                "partial_hedge": "Part of commodities are hedged against price risk or deals in non-volatile commodities",
                "well_hedged": "Price risk is covered through well-defined hedging via NCDEX or other mediums",
                "not_applicable": "Not available - FPO only involved in lending/supplying inputs",
            },
            "producer_org_type": {
                "co_operative_society": "Organization type is Co-operative Society",
                "producer_company": "Organization type is Producer Company",
                "non_profit_society": "Organization type is Non-Profit Society",
                "trust": "Organization type is Trust",
                "section_8_company": "Organization type is Section-8 Company",
            },
            "promoting_agency_type": {
                "ngo": "Promoting agency is NGO",
                "trusts": "Promoting agency is Trust",
                "cooperatives": "Promoting agency is Cooperative",
                "corporate_wings": "Promoting agency is corporate wing/development foundation",
                "state_govt": "Promoting agency is state government department",
                "kvks": "Promoting agency is KVK",
                "farmer_federations": "Promoting agency is farmer federation",
                "commodity_boards": "Promoting agency is commodity board",
                "big_farmer_companies": "Promoting agency is big farmer producer company",
                "others": "Promoting agency is other type",
            },
            "second_line_management": {
                "ceo_accounts_two_managers": "CEO supported by accounts team & atleast 2 divisional manager (eg : marketing, sales, procurement)",
                "ceo_accounts_one_manager": "CEO supported by accounts team & atleast one divisional manager (eg : marketing, sales, procurement)",
                "ceo_with_accounts": "No second line of management , CEO is supported only by the accounts team",
                "only_ceo": "No second line of management to support CEO",
                "no_ceo": "Currently, there is no CEO",
            },
            # "minutes_maintenance": {
            #     "detailed_compliant": "Meeting minutes are detailed with proper decisions recorded and compliance maintained",
            #     "detailed_not_updated": "Meeting minutes are detailed with decisions recorded but not updated on MCA portal",
            #     "sketchy_quality": "Meeting minutes are maintained but lack sufficient detail",
            #     "not_maintained": "Meeting minutes are not maintained properly",
            # },
        }

        def _format_days(prefix: str, val) -> str:
            if val is None:
                return f"{prefix} 0 days"

            try:
                days = int(val)
            except (TypeError, ValueError):
                return f"{prefix} 0 days"

            unit = "day" if days == 1 else "days"
            return f"{prefix} {days} {unit}"

        non_enum_formatters = {
            "type_of_fpo": lambda val: (
                "FPO deals in the processing of raw commodities"
                if val >= 2
                else "FPO does not deal in the processing of raw commodities"
            ),
            "penalties_levied": lambda val: (
                "No Statutory Penalty has been levied in the last financial year"
                if not val
                else "Statutory Penalty has been levied in the last financial year"
            ),
            "revenue_per_member": lambda val: f"Revenue per active member is INR {int(val):,}",
            "net_profit_margin": lambda val: (
                f"Net profit margin(%) is {int(val)}"
                if val == 0 or val.is_integer()
                else f"Net profit margin(%) is {val:.1f}"
            ),
            "current_ratio": lambda val: f"Current ratio is {int(val):}",
            "inventory_period": lambda val: _format_days("Inventory period is", val),
            "accounts_payable": lambda val: _format_days("Accounts payable period is", val),
            "accounts_receivable": lambda val: _format_days("Accounts receivable period is", val),
            "asset_turnover": lambda val: (
                "Asset turnover ratio is 0" if val is None else f"Asset turnover ratio is {val:.2f}"
            ),
            "debt_to_networth": lambda val: (
                "Debt to networth ratio is ∞" if val is None else f"Debt to networth ratio is {int(val)}"
            ),
            "cash_dealings": lambda val: (
                f"Cash dealings as % of gross revenue is {int(val)}"
                if val == 0 or val.is_integer()
                else f"Cash dealings as % of gross revenue is {val:.1f}"
            ),
            "trend_profitability": lambda val: f"FPO has been profitable for {int(val)} out of the last 3 financial years",
            "board_directors_size": lambda val: (
                f"Number of Board of Directors as % of optimal number of Board of Directors is {int(val)}%"
                if val == 0 or val.is_integer()
                else f"Number of Board of Directors as % of optimal number of Board of Directors is {val:.1f}%"
            ),
            "board_quality": lambda val: (
                "The BODs have relevant experience" if val >= 2 else "The BODs do not have relevant experience"
            ),
            "ceo_experience": lambda val: (
                "CEO has relevant experience" if val >= 2 else "CEO does not have relevant experience"
            ),
            "size_achievement": lambda val: (
                "Target/size data not available"
                if val is None
                else (
                    f"FPO has achieved {int(val)}% of target size"
                    if val == 0 or val.is_integer()
                    else f"FPO has achieved {val:.1f}% of target size"
                )
            ),
            "accessibility": lambda val: (
                f"Inputs are made accessible to {int(val)}% of the members"
                if val == 0 or val.is_integer()
                else f"Inputs are made accessible to {val:.1f}% of the members"
            ),
            "value_chain_services": lambda val: (
                "FPO provides the majority of the value chain services to the farmers"
                if val > 1.4
                else "FPO does not provide many important value chain services to the farmers"
            ),
            "institutional_buyers": lambda val: (
                f"Institutional buyers represent {int(val)}% of total revenue"
                if val == 0 or val.is_integer()
                else f"Institutional buyers represent {val:.1f}% of total revenue"
            ),
        }

        if field_name in non_enum_formatters:
            # Use explicit None check so 0/False values are preserved
            value = raw_value if raw_value is not None else enum_value
            return non_enum_formatters[field_name](value)

        return mappings.get(field_name, {}).get(str(enum_value), str(enum_value))

    # ------------------------------------------------------------------
    # TOP-LEVEL ENTRY
    # ------------------------------------------------------------------
    def calculate_total_score(self) -> Decimal:
        """Calculate and return the total weighted score along with individual section scores."""
        # Check if we have the required data to calculate the score

        self._raw_scores = {
            "governance": Decimal("0.00"),
            "business": Decimal("0.00"),
            "process": Decimal("0.00"),
            "financial": Decimal("0.00"),
        }
        self._section_scores = {
            "governance": Decimal("0.00"),
            "business": Decimal("0.00"),
            "process": Decimal("0.00"),
            "financial": Decimal("0.00"),
        }

        if not hasattr(self.sub, "fpo_details") or not self.sub.fpo_details:
            return Decimal("0.00")

        try:
            # Use financial year end date (March 31 of financial year) instead of today's date
            financial_year = self.sub.financial_year
            if financial_year and "-" in financial_year:
                year_part = financial_year.split("-")[1]  # Get the second part (e.g., "2024" or "24")
                # Handle both 4-digit and 2-digit year formats
                if len(year_part) == 2:  # Format like "23-24" -> convert "24" to "2024"
                    year_part = "20" + year_part
                financial_year_end = date(int(year_part), 11, 1)  # November 1 of the year
            else:
                # Fallback to today's date if financial year not properly formatted
                financial_year_end = date.today()

            age = (financial_year_end - self.sub.fpo_details.date_of_incorporation).days / 365.25

            weights = self._age_based_weights(age)

            # Wrap each section calculation in try-catch to return 0 if it fails
            try:
                gov_score, _ = self._governance_score()
            except Exception as e:
                print(f"Error in governance score calculation: {e}")
                gov_score = 0

            try:
                biz_score, _ = self._business_score()
            except Exception as e:
                print(f"Error in business score calculation: {e}")
                biz_score = 0

            try:
                proc_score, _ = self._process_score()
            except Exception as e:
                print(f"Error in process score calculation: {e}")
                proc_score = 0

            try:
                fin_score, _ = self._financial_score()
            except Exception as e:
                print(f"Error in financial score calculation: {e}")
                fin_score = 0

            self._raw_scores = {
                "governance": Decimal(gov_score).quantize(Decimal("0.01")),
                "business": Decimal(biz_score).quantize(Decimal("0.01")),
                "process": Decimal(proc_score).quantize(Decimal("0.01")),
                "financial": Decimal(fin_score).quantize(Decimal("0.01")),
            }

            gov_normalized = (Decimal(gov_score) / Decimal(25)) * Decimal(100)
            biz_normalized = (Decimal(biz_score) / Decimal(33)) * Decimal(100)
            proc_normalized = (Decimal(proc_score) / Decimal(19)) * Decimal(100)
            fin_normalized = (Decimal(fin_score) / Decimal(31)) * Decimal(100)

            # weighted = gov_normalized + biz_normalized + proc_normalized + fin_normalized

            # print(f"Weighted: {weighted}")
            # Store individual section scores for later retrieval

            self._section_scores = {
                "governance": gov_normalized.quantize(Decimal("0.01")),
                "business": biz_normalized.quantize(Decimal("0.01")),
                "process": proc_normalized.quantize(Decimal("0.01")),
                "financial": fin_normalized.quantize(Decimal("0.01")),
            }

            # Weights: governance=30 (means 30%), business=25 (25%), etc.
            weighted_score = (
                (gov_normalized * Decimal(weights["governance"]) / Decimal(100))  # 60% × 30% = 0.60 × 0.30 = 0.18
                + (biz_normalized * Decimal(weights["business"]) / Decimal(100))  # 70% × 25% = 0.70 × 0.25 = 0.175
                + (proc_normalized * Decimal(weights["process"]) / Decimal(100))  # 80% × 20% = 0.80 × 0.20 = 0.16
                + (fin_normalized * Decimal(weights["financial"]) / Decimal(100))  # 50% × 25% = 0.50 × 0.25 = 0.125
            )  # Total = 0.18 + 0.175 + 0.16 + 0.125 = 0.64 (64%)

            final_score = weighted_score.quantize(Decimal("0.01"))

            self._performance_category = self.get_performance_category(final_score)

            return final_score
        except (AttributeError, TypeError, ValueError) as e:
            # Print detailed error information for easier debugging
            print("Error in calculate_total_score:", e)
            import traceback

            traceback.print_exc()

            # Handle cases where data is missing or invalid
            return Decimal("0.00")

    def get_section_scores(self):
        """Return individual section scores as a dictionary."""
        if not hasattr(self, "_section_scores"):
            # Calculate scores if not already calculated
            self.calculate_total_score()
        return self._section_scores

    def get_raw_scores(self):
        """Return individual section raw scores as a dictionary."""
        if not hasattr(self, "_raw_scores"):
            self.calculate_total_score()

        # Fallback if calculate_total_score failed
        if not hasattr(self, "_raw_scores"):
            self._raw_scores = {
                "governance": Decimal("0.00"),
                "business": Decimal("0.00"),
                "process": Decimal("0.00"),
                "financial": Decimal("0.00"),
            }

        return self._raw_scores

    def get_performance_category_stored(self) -> str:
        """Return stored performance category."""
        if not hasattr(self, "_performance_category"):
            # Calculate scores if not already calculated
            self.calculate_total_score()
        return self._performance_category

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def get_performance_category(self, score: Decimal = None) -> str:
        """Return performance category based on score."""
        if score is None:
            score = self.calculate_total_score()

        score_percentage = float(score)  # Convert to percentage

        if score_percentage >= 70:
            return "Achievers"
        elif score_percentage >= 50:
            return "Performer"
        else:
            return "Aspirational"

    def _age_based_weights(self, age):
        if age < 1:  # less than one year
            return {"governance": 40, "business": 20, "process": 25, "financial": 15}
        elif age < 3:  # less than 3 years
            return {"governance": 35, "business": 20, "process": 25, "financial": 20}
        elif age < 5:  # less than 5 years
            return {"governance": 30, "business": 25, "process": 20, "financial": 25}
        else:  # more than 5 years
            return {"governance": 25, "business": 30, "process": 15, "financial": 30}

    def get_indicator_hit_miss(self, indicator_name, score):
        """Determine Hit/Miss status for each indicator"""

        hit_thresholds = {
            # Governance
            # "board_directors_size": [3, 2],  # Intentionally excluded: this indicator doesn't show Hit/Miss in frontend
            "board_quality": [4, 3, 2],
            "ceo_experience": [4, 3, 2],
            "size_achievement": [3, 2],
            "active_membership": [3, 2],
            "second_line_management": [4, 3],
            # Business & Operations
            "type_of_fpo": [3, 2],
            "price_volatility": [3, 2],
            "institutional_buyers": [3],
            "institutional_lending_history": [2, 1],
            "accessibility": [3, 2],
            "timeliness": [4, 3, 2],
            "price_affordability": [4, 3],
            "place": [4, 3],
            "output_collection": [4, 3],
            "value_chain_services": 1.4,  # Special case: > 1.4
            # Process & Systems
            "accounts_mis": [3, 2],
            "insurance": [3, 2],
            "credit_record": [3, 2],
            "statutory_fillings": [3, 2],
            "books_records": [3, 2],
            "stock_reconciliation": [3, 2],
            "penalties": [1],
            # Financial
            "revenue_per_member": [3, 2],
            "net_profit_margin": [3, 2],
            "trend_profitability": [3, 2],
            "debt_to_networth": [3, 2],
            "cash_dealings": [3, 2],
            "current_ratio": [3, 2],
            "inventory_period": [3, 2],
            "accounts_payable": [3, 2],
            "accounts_receivable": [3, 2],
            "asset_turnover": [3, 2],
        }

        threshold = hit_thresholds.get(indicator_name, [])

        if indicator_name == "board_quality":
            return "Hit" if score >= 2 else "Miss"
        elif indicator_name == "asset_turnover":
            return "Hit" if score >= 2 else "Miss"
        elif indicator_name == "value_chain_services":
            return "Hit" if score > threshold else "Miss"
        else:
            return "Hit" if round(score) in threshold else "Miss"

    def get_detailed_indicators(self):
        """Get all indicators with hit/miss status"""
        governance_score, governance_indicators = self._governance_score()
        business_score, business_indicators = self._business_score()
        process_score, process_indicators = self._process_score()
        financial_score, financial_indicators = self._financial_score()

        return {
            "governance": governance_indicators,
            "business": business_indicators,
            "process": process_indicators,
            "financial": financial_indicators,
        }

    def get_active_membership_percentage(self):
        fpo = self.sub.fpo_details
        if fpo.size_of_fpo_fy_23_24 is not None and fpo.farmers_transacted is not None and fpo.size_of_fpo_fy_23_24 > 0:
            pct = (fpo.farmers_transacted / fpo.size_of_fpo_fy_23_24) * 100
            return f"{pct:.1f}%"
        return "0%"

    # ------------------------------------------------------------------
    # 1. GOVERNANCE
    # ------------------------------------------------------------------
    def _governance_score(self):
        score = 0
        indicators = []
        gov = getattr(self.sub, "governance", None)
        fpo = self.sub.fpo_details
        board = self.sub.board_directors.all()

        # 1. Promoting agency - if Yes then 1, else 0
        section_score = 0
        promoting_agency = "Yes" if fpo.supported_by_promoting_agency else "No"
        if fpo.supported_by_promoting_agency:
            section_score = 1
        score += section_score

        # 2. Board of directors size
        section_score = 0
        size_fpo = fpo.size_of_fpo_fy_23_24 or 0
        if size_fpo <= 1000:
            optimal_bod = 5
        else:
            additional_bods = math.ceil((size_fpo - 1000) / 1000)
            optimal_bod = min(5 + additional_bods, 15)
        actual_bod = len(board)
        bod_percentage = (actual_bod / optimal_bod) * 100

        if size_fpo < 1000:
            # For FPOs with less than 1000 members, at least 5 BOD are mandatory = rating 3
            section_score = 3 if actual_bod >= 5 else 2
        else:
            # For FPOs with more than 1000 members, rated based on BOD as % of optimal
            if bod_percentage >= 100:
                section_score = 3
            elif bod_percentage >= 75:
                section_score = 2
            elif bod_percentage >= 50:
                section_score = 1
            else:
                section_score = 0

        # NOTE: Board of directors size score is counted in the governance score,
        # but this indicator is intentionally NOT shown in the PDF/UI hit-miss lists.
        # (Per requirement: ignore from hit/miss logic and do not display.)
        score += section_score

        # 3. Board quality - calculate average
        section_score = 0
        bod_quality_scores = []
        quality_details = []
        for b in board:
            y = b.total_years_of_experience
            experience_type = getattr(b, "type_of_experience", None)
            quality_score = 0
            if y >= 12:
                quality_score = 4
            elif y >= 10:
                quality_score = 3
            elif y >= 8:
                quality_score = 2
            elif y >= 5:
                quality_score = 1
            else:
                quality_score = 0

            # Apply penalty for non-relevant experience
            # Apply penalty for non-relevant experience
            experience_type = getattr(b, "type_of_experience", None)
            penalty_applied = False
            if experience_type == "any_other":  # Remove the enum check, use string directly
                quality_score *= 0.5
                penalty_applied = True

            bod_quality_scores.append(quality_score)
            quality_details.append(
                f"Director: {y} years exp, Score: {quality_score}" + (" (penalty applied)" if penalty_applied else "")
            )

        # Calculate average BOD quality
        average_bod_quality = 0
        if bod_quality_scores:
            average_bod_quality = sum(bod_quality_scores) / len(bod_quality_scores)
            section_score = average_bod_quality  # Direct average, no normalization

        formatted_value = self.format_indicator_value("board_quality", average_bod_quality)
        status = self.get_indicator_hit_miss("board_quality", section_score)
        indicators.append(
            {"name": "Board Quality", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 4. CEO
        section_score = 0
        ceo = getattr(self.sub, "ceo_profile", None)
        ceo_details = "No CEO data"
        formatted_value = "No CEO data"
        experience_type = None
        y = 0
        if ceo:
            y = ceo.total_years_of_experience
            if y >= 12:
                section_score = 4
            elif y >= 10:
                section_score = 3
            elif y >= 8:
                section_score = 2
            elif y >= 5:
                section_score = 1
            else:
                section_score = 0

            # Apply penalty for non-relevant experience
            experience_type = getattr(ceo, "type_of_experience", None)
            penalty_applied = False
            if experience_type:
                from .models import ExperienceType

                if experience_type == ExperienceType.ANY_OTHER:
                    section_score *= 0.5
                    penalty_applied = True

            ceo_details = f"{y} years exp, Score: {section_score}" + (" (penalty applied)" if penalty_applied else "")

            # Build complete description with experience type and score
            if experience_type:
                experience_description = self.format_indicator_value("ceo_experience", section_score)
                formatted_value = f"{experience_description}"
            else:
                formatted_value = f"{y} years experience"

        status = self.get_indicator_hit_miss("ceo_experience", section_score)
        indicators.append(
            {"name": "Leadership Quality ", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 5. Size achievement
        section_score = 0
        achievement_details = "No target/size data"
        pct = None
        if fpo.target_size_of_fpo and fpo.size_of_fpo_fy_23_24:
            pct = (fpo.size_of_fpo_fy_23_24 / fpo.target_size_of_fpo) * 100
            if pct >= 75:
                section_score = 3
            elif pct >= 50:
                section_score = 2
            elif pct >= 25:
                section_score = 1
            else:
                section_score = 0
            achievement_details = (
                f"Target: {fpo.target_size_of_fpo}, Actual: {fpo.size_of_fpo_fy_23_24}, Achievement: {pct:.1f}%"
            )

        formatted_value = self.format_indicator_value("size_achievement", section_score, pct)
        status = self.get_indicator_hit_miss("size_achievement", section_score)
        indicators.append(
            {
                "name": "Achievement for size of the FPO",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 6. Second line management
        section_score = 0
        second_line_details = "No data"
        second_line_mapping = {
            "ceo_accounts_two_managers": 4,
            "ceo_accounts_one_manager": 3,
            "ceo_with_accounts": 2,
            "only_ceo": 1,
            "no_ceo": 0,
        }

        if gov and gov.second_line_management in second_line_mapping:
            section_score = second_line_mapping[gov.second_line_management]
            formatted_value = self.format_indicator_value("second_line_management", gov.second_line_management)

        status = self.get_indicator_hit_miss("second_line_management", section_score)
        indicators.append(
            {
                "name": "Second line of Management",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # 7. Minutes maintenance
        section_score = 0
        minutes_details = "No data"
        minutes_mapping = {
            MinutesMaintenanceType.DETAILED_COMPLIANT: 3,
            MinutesMaintenanceType.DETAILED_NOT_UPDATED: 2,
            MinutesMaintenanceType.SKETCHY_QUALITY: 1,
            MinutesMaintenanceType.NOT_MAINTAINED: 0,
        }

        if gov and gov.minutes_maintenance in minutes_mapping:
            section_score = minutes_mapping[gov.minutes_maintenance]
            minutes_details = f"{gov.minutes_maintenance}"

        # formatted_value = self.format_indicator_value("minutes_maintenance", gov.minutes_maintenance)
        # status = self.get_indicator_hit_miss("minutes_maintenance", section_score)
        # indicators.append(
        #     {
        #         "name": "Minutes of the meeting",
        #         "score": float(section_score),
        #         "value": formatted_value,
        #         "status": status,
        #     }
        # )
        score += section_score

        # 8. Active membership
        section_score = 0
        active_pct = None
        if fpo.size_of_fpo_fy_23_24 and fpo.farmers_transacted:
            active_pct = (fpo.farmers_transacted / fpo.size_of_fpo_fy_23_24) * 100
            if active_pct >= 75:
                section_score = 3
            elif active_pct >= 50:
                section_score = 2
            elif active_pct >= 25:
                section_score = 1
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("active_membership", section_score, active_pct)
        status = self.get_indicator_hit_miss("active_membership", section_score)
        indicators.append(
            {
                "name": "Active membership",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score
        if score != round(score, 1):  # Has more than 1 decimal place
            score = round(score, 1)
        return score, indicators  # Return actual score without capping at 27

    # ------------------------------------------------------------------
    # 2. BUSINESS & OPERATIONS
    # ------------------------------------------------------------------
    def _business_score(self):
        score = 0
        indicators = []

        biz = getattr(self.sub, "business_operations", None)
        if not biz:
            return score, indicators

        fpo_details = biz.yearly_submission.fpo_details
        fin = getattr(self.sub, "financial_details_v2", None)

        # 1. Type of FPO
        section_score = 0
        fpo_type_mapping = {
            FPOType.INPUTS_OR_OUTPUT: 0,
            FPOType.INPUTS_AND_OUTPUT: 1,
            FPOType.LOW_CAPACITY: 2,
            FPOType.HIGH_CAPACITY: 3,
        }

        if fpo_details.type_of_fpo in fpo_type_mapping:
            section_score = fpo_type_mapping[fpo_details.type_of_fpo]

        formatted_value = self.format_indicator_value("type_of_fpo", section_score)
        status = self.get_indicator_hit_miss("type_of_fpo", section_score)
        indicators.append(
            {"name": "Type of FPO", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 2. Price volatility
        section_score = 0
        price_volatility_mapping = {
            "highly_volatile_fpo_risk": 0,
            "msp_fpo_risk": 1,
            "partial_hedge": 2,
            "well_hedged": 3,
            "not_applicable": 3,
        }

        # Check if it's in the mapping
        if biz.price_volatility_of_products in price_volatility_mapping:
            section_score = price_volatility_mapping[biz.price_volatility_of_products]

        formatted_value = self.format_indicator_value("price_volatility", section_score)
        status = self.get_indicator_hit_miss("price_volatility", section_score)
        indicators.append(
            {
                "name": "Price volatility of the products",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 3. Institutional buyers share
        section_score = 0
        institutional_share = 0
        if fin and fin.current_year_revenue and fin.current_year_revenue > 0:
            institutional_share = (
                float(fin.current_year_institutional_revenue) / float(fin.current_year_revenue)
            ) * 100
            if institutional_share >= 50:
                section_score = 3
            elif institutional_share >= 30:
                section_score = 2
            elif institutional_share >= 10:
                section_score = 1
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("institutional_buyers", None, institutional_share)
        status = self.get_indicator_hit_miss("institutional_buyers", section_score)
        indicators.append(
            {
                "name": "Share of institutional buyers in total revenue",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 4. Institutional lending history
        section_score = 0
        lending_history = "No data"
        enum_key = "no_history"  # Initialize default
        lending_history = "No data"
        enum_key = "no_history"  # Initialize default

        if fin and fin.institutional_lending_history:
            lending_history = fin.institutional_lending_history

            if fin.institutional_lending_history == "repeated_lending":
                enum_key = "repeated_lending"
                section_score = 2
            elif fin.institutional_lending_history == "at_least_one":
                enum_key = "at_least_one"
                section_score = 1
            else:
                enum_key = "no_history"
                section_score = 0

        formatted_value = self.format_indicator_value("institutional_lending_history", enum_key)
        status = self.get_indicator_hit_miss("institutional_lending_history", section_score)
        indicators.append(
            {
                "name": "History of Institutional lending",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # 5. Input accessibility
        section_score = 0
        acc = float(biz.accessibility_percentage or 0)
        if acc >= 80:
            section_score = 3
        elif acc >= 60:
            section_score = 2
        elif acc >= 40:
            section_score = 1
        else:
            section_score = 0

        formatted_value = self.format_indicator_value("accessibility", section_score, acc)
        status = self.get_indicator_hit_miss("accessibility", section_score)
        if biz.availability_of_inputs_timeliness != "not_applicable":
            indicators.append(
                {
                    "name": "Availability of inputs to members - Accessibility",
                    "score": float(section_score),
                    "value": formatted_value,
                    "status": status,
                }
            )

        score += section_score

        # 6. Timeliness
        section_score = 0
        timeliness_mapping = {
            "30_days_prior": 4,
            "20_days_prior": 3,
            "15_days_prior": 2,
            "7_days_prior": 1,
            "not_applicable": 0,
        }
        if biz.availability_of_inputs_timeliness in timeliness_mapping:
            section_score = timeliness_mapping[biz.availability_of_inputs_timeliness]

        formatted_value = self.format_indicator_value("timeliness", section_score)
        status = self.get_indicator_hit_miss("timeliness", section_score)
        indicators.append(
            {
                "name": "Availability of inputs to members - Timeliness",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # 7. Price affordability - only add to indicators if timeliness is not "not_applicable"
        section_score = 0
        affordability_mapping = {
            PriceAffordabilityType.TEN_TO_FIFTEEN_PERCENT: 4,
            PriceAffordabilityType.FIVE_TO_TEN_PERCENT: 3,
            PriceAffordabilityType.THREE_TO_FIVE_PERCENT: 2,
            PriceAffordabilityType.ONE_TO_THREE_PERCENT: 1,
            PriceAffordabilityType.NOT_APPLICABLE: 0,
        }

        if biz.availability_of_inputs_price_affordability in affordability_mapping:
            section_score = affordability_mapping[biz.availability_of_inputs_price_affordability]

        formatted_value = self.format_indicator_value("price_affordability", section_score)
        status = self.get_indicator_hit_miss("price_affordability", section_score)

        # Only add to indicators if timeliness is not "not_applicable"
        if biz.availability_of_inputs_timeliness != "not_applicable":
            indicators.append(
                {
                    "name": "Availability of inputs to members - Price/Affordability",
                    "score": float(section_score),
                    "value": formatted_value,
                    "status": status,
                }
            )
        else:
            pass

        score += section_score

        # 8. Distance – inputs - only add to indicators if timeliness is not "not_applicable"
        section_score = 0
        distance_mapping = {
            "3_km_available": 4,
            "6_km_available": 3,
            "10_km_available": 2,
            "not_within_10_km": 1,
            "not_applicable": 0,
        }

        if biz.availability_of_inputs_place in distance_mapping:
            section_score = distance_mapping[biz.availability_of_inputs_place]

        formatted_value = self.format_indicator_value("place", section_score)
        status = self.get_indicator_hit_miss("place", section_score)

        # Only add to indicators if timeliness is not "not_applicable"
        if biz.availability_of_inputs_timeliness != "not_applicable":
            indicators.append(
                {
                    "name": "Availability of inputs to members - Place",
                    "score": float(section_score),
                    "value": formatted_value,
                    "status": status,
                }
            )
        else:
            pass

        score += section_score

        # 9. Distance – outputs
        section_score = 0

        # Use the same distance_mapping for consistency
        if biz.distance_of_output_collection_centres in distance_mapping:
            section_score = distance_mapping[biz.distance_of_output_collection_centres]

        formatted_value = self.format_indicator_value("output_collection", section_score)
        status = self.get_indicator_hit_miss("output_collection", section_score)

        indicators.append(
            {
                "name": "Output collection centres",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score
        # 10. Value chain services - 0.2 points for each service provided
        section_score = 0
        services = [
            biz.electronic_weighing_machines,
            biz.transportation_facility,
            biz.storage,
            biz.cleaning,
            biz.grading_and_sorting,
            biz.chilling,
            biz.packaging,
            biz.labelling,
            biz.processing,
            biz.quality_check,
            biz.soil_testing_facility,
            biz.custom_hiring_centers,
            biz.contract_farming,
            biz.advisory_services,
            biz.credit_facilities,
        ]
        section_score = sum(0.2 for s in services if s)

        formatted_value = self.format_indicator_value("value_chain_services", None, section_score)
        status = self.get_indicator_hit_miss("value_chain_services", section_score)
        indicators.append(
            {
                "name": "Value chain services to the members",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # Print value chain services details
        services_provided = [
            service_name
            for service_name, service_value in [
                ("Electronic weighing machines", biz.electronic_weighing_machines),
                ("Transportation facility", biz.transportation_facility),
                ("Storage", biz.storage),
                ("Cleaning", biz.cleaning),
                ("Grading and sorting", biz.grading_and_sorting),
                ("Chilling", biz.chilling),
                ("Packaging", biz.packaging),
                ("Labelling", biz.labelling),
                ("Processing", biz.processing),
                ("Quality check", biz.quality_check),
                ("Soil testing facility", biz.soil_testing_facility),
                ("Custom hiring centers", biz.custom_hiring_centers),
                ("Contract farming", biz.contract_farming),
                ("Advisory services", biz.advisory_services),
                ("Credit facilities", biz.credit_facilities),
            ]
            if service_value
        ]

        # if services_provided:
        #     print(f"  Services: {', '.join(services_provided)}")
        return score, indicators  # Return actual score without capping at 30

    # ------------------------------------------------------------------
    # 3. PROCESS & SYSTEMS
    # ------------------------------------------------------------------
    def _process_score(self):
        score = 0
        indicators = []
        ps = getattr(self.sub, "processes_systems", None)
        if not ps:
            return score, indicators

        # 1. Accounts & MIS
        section_score = 0
        accounts_mapping = {
            AccountsMISType.SOFTWARE_DIGITAL: 3,
            AccountsMISType.TALLY_NO_DIGITAL: 2,
            AccountsMISType.MS_OFFICE_TOOLS: 1,
            AccountsMISType.NO_MIS: 0,
        }

        if ps.accounts_and_mis in accounts_mapping:
            section_score = accounts_mapping[ps.accounts_and_mis]

        formatted_value = self.format_indicator_value("accounts_mis", section_score)
        status = self.get_indicator_hit_miss("accounts_mis", section_score)
        indicators.append(
            {"name": "Accounts & MIS", "score": float(section_score), "value": formatted_value, "status": status}
        )

        score += section_score

        # 2. Insurance of stock against fire & theft
        section_score = 0
        insurance_mapping = {
            InsuranceStockType.HUNDRED_PERCENT_FIRE_THEFT: 3,
            InsuranceStockType.FIFTY_PERCENT_FIRE_THEFT: 2,
            InsuranceStockType.LESS_THAN_50_FIRE: 1,
            InsuranceStockType.NO_INSURANCE: 0,
        }

        if ps.insurance_of_stock in insurance_mapping:
            section_score = insurance_mapping[ps.insurance_of_stock]

        formatted_value = self.format_indicator_value("insurance_of_stock", ps.insurance_of_stock)
        status = self.get_indicator_hit_miss("insurance", section_score)
        indicators.append(
            {
                "name": "Insurance of stock against fire & theft",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 3. Credit Record of FPO
        section_score = 0
        credit_mapping = {
            CreditRecordType.NO_DELAYS: 3,
            CreditRecordType.ONE_DELAY: 2,
            CreditRecordType.MULTIPLE_DELAYS: 1,
            CreditRecordType.NO_CREDIT_HISTORY: 0,
        }

        if ps.credit_record_of_fpo in credit_mapping:
            section_score = credit_mapping[ps.credit_record_of_fpo]

        formatted_value = self.format_indicator_value("credit_record_of_fpo", ps.credit_record_of_fpo)
        status = self.get_indicator_hit_miss("credit_record", section_score)
        indicators.append(
            {"name": "Credit Record of FPO", "score": float(section_score), "value": formatted_value, "status": status}
        )

        score += section_score

        # 4. Statutory filings
        section_score = 0
        filings_mapping = {
            StatutoryFillingsType.NO_DELAYS: 3,
            StatutoryFillingsType.FEW_DELAYS_FILLED: 2,
            StatutoryFillingsType.MULTIPLE_DELAYS_FILLED: 1,
            StatutoryFillingsType.DELAYS_NOT_FILLED: 0,
        }

        if ps.statutory_fillings in filings_mapping:
            section_score = filings_mapping[ps.statutory_fillings]

        formatted_value = self.format_indicator_value("statutory_fillings", section_score)
        status = self.get_indicator_hit_miss("statutory_fillings", section_score)
        indicators.append(
            {"name": "Statutory Filings", "score": float(section_score), "value": formatted_value, "status": status}
        )

        score += section_score

        # 5. Are the books and records upto date
        section_score = 0
        books_mapping = {
            BooksRecordsType.CURRENT: 3,
            BooksRecordsType.LAG_2_3_DAYS: 2,
            BooksRecordsType.WEEKLY_UPDATED: 1,
            BooksRecordsType.MONTHLY_OR_MORE: 0,
        }

        if ps.books_and_records_up_to_date in books_mapping:
            section_score = books_mapping[ps.books_and_records_up_to_date]

        formatted_value = self.format_indicator_value("books_and_records_up_to_date", ps.books_and_records_up_to_date)
        status = self.get_indicator_hit_miss("books_records", section_score)
        indicators.append(
            {
                "name": "Are the books and records up to date",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 6. Reconciliation of stocks
        section_score = 0
        reconciliation_mapping = {
            ReconciliationStocksType.EVERY_15_DAYS: 3,
            ReconciliationStocksType.MONTHLY: 2,
            ReconciliationStocksType.TWO_TO_FOUR_TIMES: 1,
            ReconciliationStocksType.ABSENT_ANNUAL: 0,
        }

        if ps.reconciliation_of_stocks in reconciliation_mapping:
            section_score = reconciliation_mapping[ps.reconciliation_of_stocks]

        formatted_value = self.format_indicator_value("reconciliation_of_stocks", ps.reconciliation_of_stocks)
        status = self.get_indicator_hit_miss("stock_reconciliation", section_score)
        indicators.append(
            {
                "name": "Reconciliation of stocks",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score

        # 7. Have penalties been levied for non compliance with statutory frequency of Board meeting
        section_score = 0
        # Score is 1 if NO penalties were levied (good), 0 if penalties were levied (bad)
        if ps.penalties_levied_board_meeting is False:
            section_score = 1
        else:
            section_score = 0

        formatted_value = self.format_indicator_value("penalties_levied", None, ps.penalties_levied_board_meeting)
        status = self.get_indicator_hit_miss("penalties", section_score)

        indicators.append(
            {
                "name": "Have penalties been levied",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )

        score += section_score
        return score, indicators  # Return actual score without capping at 21

    # ------------------------------------------------------------------
    # 4. FINANCIAL PERFORMANCE
    # ------------------------------------------------------------------
    def _financial_score(self):
        score = 0
        indicators = []

        fin = getattr(self.sub, "financial_details_v2", None)
        fpo = self.sub.fpo_details
        if not fin or not fpo:
            return score, indicators

        # 1. Revenue per active member
        section_score = 0
        rpm = 0
        if fpo.farmers_transacted is not None and fpo.farmers_transacted > 0 and fin.current_year_revenue is not None:
            rpm = float(fin.current_year_revenue / fpo.farmers_transacted)
            if rpm >= 100000:
                section_score = 3
            elif rpm >= 75000:
                section_score = 2
            elif rpm >= 50000:
                section_score = 1
            else:
                section_score = 0

        status = self.get_indicator_hit_miss("revenue_per_member", section_score)
        formatted_value = self.format_indicator_value("revenue_per_member", None, rpm)
        indicators.append(
            {"name": "Revenue per Member", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 2. Net profit margin
        section_score = 0
        npm = 0
        if fin.current_year_revenue is not None and fin.current_year_revenue > 0:
            npm = float(fin.current_year_net_profit / fin.current_year_revenue * 100)

            if npm >= 10:
                section_score = 3
            elif npm >= 5:
                section_score = 2
            elif npm >= 0:
                section_score = 1
            else:
                section_score = 0

            formatted_value = self.format_indicator_value("net_profit_margin", None, npm)
            status = self.get_indicator_hit_miss("net_profit_margin", section_score)
            indicators.append(
                {"name": "Net Profit Margin", "score": float(section_score), "value": formatted_value, "status": status}
            )

        score += section_score

        # 3. Trend profitability
        section_score = 0
        # Count profitable years in past 3 financial years
        if fin.two_years_back_net_profit is not None and fin.two_years_back_net_profit > 0:
            section_score += 1
        if fin.previous_year_net_profit is not None and fin.previous_year_net_profit > 0:
            section_score += 1
        if fin.current_year_net_profit is not None and fin.current_year_net_profit > 0:
            section_score += 1

        formatted_value = self.format_indicator_value("trend_profitability", section_score)
        status = self.get_indicator_hit_miss("trend_profitability", section_score)
        indicators.append(
            {"name": "Trend Profitability", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 4. Debt to net-worth
        # 4. Debt to net-worth
        section_score = 0
        dtn = None

        # Calculate net worth as assets - liabilities (Excel formula)
        if fin.current_year_assets is not None and fin.current_year_liabilities is not None:
            net_worth = float(fin.current_year_assets) - float(fin.current_year_liabilities)
            if net_worth != 0:
                dtn = float(fin.total_debt_today or 0) / net_worth
                if dtn <= 3:
                    section_score = 3
                elif dtn <= 6:
                    section_score = 2
                elif dtn <= 10:
                    section_score = 1
                else:
                    section_score = 0
            else:
                if fin.total_debt_today == 0:
                    section_score = 3
                    dtn = 0.0
                else:
                    section_score = 0
        else:
            if fin.total_debt_today == 0:
                section_score = 3
                dtn = 0.0
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("debt_to_networth", dtn)
        status = self.get_indicator_hit_miss("debt_to_networth", section_score)
        indicators.append(
            {"name": "Debt to Net-worth", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 5. Cash dealings
        section_score = 0
        cash_pct = float(fin.cash_cheque_percentage or 0)
        if cash_pct < 20:
            section_score = 3
        elif cash_pct < 50:
            section_score = 2
        elif cash_pct < 70:
            section_score = 1
        else:
            section_score = 0

        formatted_value = self.format_indicator_value("cash_dealings", cash_pct)
        status = self.get_indicator_hit_miss("cash_dealings", section_score)
        indicators.append(
            {"name": "Cash Dealings", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 6. Current ratio
        section_score = 0
        if fin.current_year_current_ratio is not None and fin.current_year_current_ratio > 0:
            cr = float(fin.current_year_current_ratio)
        else:
            # Calculate current ratio if not provided
            if fin.current_year_current_liabilities and fin.current_year_current_liabilities > 0:
                cr = float(fin.current_year_current_assets or 0) / float(fin.current_year_current_liabilities)
            else:
                cr = 0

        if cr >= 2:
            section_score = 3
        elif cr >= 1.5:
            section_score = 2
        elif cr >= 1:
            section_score = 1
        else:
            section_score = 0

        formatted_value = self.format_indicator_value("current_ratio", None, cr)
        status = self.get_indicator_hit_miss("current_ratio", section_score)
        indicators.append(
            {"name": "Current Ratio", "score": float(section_score), "value": formatted_value, "status": status}
        )
        score += section_score

        # 7. Inventory period
        # Update inventory period calculation
        section_score = 0
        inv_period = None
        if (
            fin.current_year_opening_inventory is not None
            and fin.previous_year_opening_inventory is not None
            and fin.current_year_cogs is not None
            and float(fin.current_year_cogs) > 0
        ):

            # Use average of opening inventories like Excel
            average_inventory = (
                float(fin.current_year_opening_inventory) + float(fin.previous_year_opening_inventory)
            ) / 2

            inv_period = average_inventory / (float(fin.current_year_cogs) / 365)

            if inv_period < 30:
                section_score = 3
            elif inv_period < 60:
                section_score = 2
            elif inv_period < 90:
                section_score = 1
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("inventory_period", None, inv_period)
        status = self.get_indicator_hit_miss("inventory_period", section_score)
        indicators.append(
            {"name": "Inventory Period", "score": float(section_score), "value": formatted_value, "status": status}
        )

        score += section_score

        # 8. Accounts payable
        section_score = 0
        ap_days = None
        if (
            fin.current_year_accounts_payable is not None
            and fin.previous_year_accounts_payable is not None
            and fin.current_year_cogs is not None
            and float(fin.current_year_cogs) > 0
        ):

            # Use average of 2 years like Excel
            average_accounts_payable = (
                float(fin.current_year_accounts_payable) + float(fin.previous_year_accounts_payable)
            ) / 2

            ap_days = average_accounts_payable / (float(fin.current_year_cogs) / 365)

            if ap_days < 30:
                section_score = 3
            elif ap_days < 60:
                section_score = 2
            elif ap_days < 90:
                section_score = 1
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("accounts_payable", None, ap_days)
        status = self.get_indicator_hit_miss("accounts_payable", section_score)
        indicators.append(
            {
                "name": "Accounts Payable Period",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # 9. Accounts receivable
        section_score = 0
        ar_days = None
        if (
            fin.current_year_accounts_receivable is not None
            and fin.previous_year_accounts_receivable is not None
            and fin.current_year_cogs is not None
            and float(fin.current_year_cogs) > 0
        ):

            # Use average of 2 years and divide by COGS (not revenue)
            average_accounts_receivable = (
                float(fin.current_year_accounts_receivable) + float(fin.previous_year_accounts_receivable)
            ) / 2

            ar_days = average_accounts_receivable / (float(fin.current_year_cogs) / 365)

            if ar_days < 30:
                section_score = 3
            elif ar_days < 60:
                section_score = 2
            elif ar_days < 90:
                section_score = 1
            else:
                section_score = 0

        formatted_value = self.format_indicator_value("accounts_receivable", None, ar_days)
        status = self.get_indicator_hit_miss("accounts_receivable", section_score)
        indicators.append(
            {
                "name": "Accounts Receivable Period",
                "score": float(section_score),
                "value": formatted_value,
                "status": status,
            }
        )
        score += section_score

        # 10. Asset turnover
        section_score = 0
        at = None
        if (
            fin.current_year_assets is not None
            and fin.previous_year_assets is not None
            and fin.current_year_revenue is not None
            and float(fin.current_year_revenue) > 0
        ):
            # Use average of 2 years assets like Excel
            average_assets = (float(fin.current_year_assets) + float(fin.previous_year_assets)) / 2

            # Avoid division by zero
            if average_assets > 0:
                at = float(fin.current_year_revenue) / average_assets

                if at >= 2:
                    section_score = 4
                elif at >= 1.5:
                    section_score = 3
                elif at >= 1:
                    section_score = 2
                elif at >= 0.5:
                    section_score = 1
                else:
                    section_score = 0

        formatted_value = self.format_indicator_value("asset_turnover", None, at)
        status = self.get_indicator_hit_miss("asset_turnover", section_score)
        indicators.append(
            {"name": "Asset Turnover", "score": float(section_score), "value": formatted_value, "status": status}
        )

        score += section_score

        return score, indicators  # Return actual score without capping at 30


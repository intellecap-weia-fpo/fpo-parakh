from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ProducerOrgType(models.TextChoices):
    CO_OPERATIVE_SOCIETY = "co_operative_society", "Co-operative Society"
    PRODUCER_COMPANY = "producer_company", "Producer Company"
    NON_PROFIT_SOCIETY = "non_profit_society", "Non-Profit Society"
    TRUST = "trust", "Trust"
    SECTION_8_COMPANY = "section_8_company", "Section-8 Company"


class FPOType(models.TextChoices):
    HIGH_CAPACITY = "high_capacity", "Dealing in inputs, output and processing with more than 50% capacity utilization"
    LOW_CAPACITY = "low_capacity", "Dealing in inputs, output and processing with less than 50% capacity utilization"
    INPUTS_OR_OUTPUT = "inputs_or_output", "Dealing in inputs or output"
    INPUTS_AND_OUTPUT = "inputs_and_output", "Dealing in inputs and output"


class PromotingAgencyType(models.TextChoices):
    NGO = "ngo", "NGO"
    TRUSTS = "trusts", "Trusts"
    COOPERATIVES = "cooperatives", "Cooperatives"
    CORPORATE_WINGS = "corporate_wings", "Wings/Development Foundation of Corporates"
    STATE_GOVT = "state_govt", "State Govt. Departments"
    KVKS = "kvks", "KVKs"
    FARMER_FEDERATIONS = "farmer_federations", "Farmer Federations"
    COMMODITY_BOARDS = "commodity_boards", "Commodity Boards"
    BIG_FARMER_COMPANIES = "big_farmer_companies", "Big Farmer Producer Companies"
    OTHERS = "others", "Others"


class MinutesMaintenanceType(models.TextChoices):
    DETAILED_COMPLIANT = (
        "detailed_compliant",
        "Minutes are detailed with decisions recorded and proper compliance followed.",
    )
    DETAILED_NOT_UPDATED = (
        "detailed_not_updated",
        "Minutes are detailed with decisions recorded but not updated on MCA.",
    )
    SKETCHY_QUALITY = "sketchy_quality", "Minutes are sketchy in quality."
    NOT_MAINTAINED = "not_maintained", "Minutes are not maintained."


class ExperienceType(models.TextChoices):
    AGRICULTURAL_COOPERATIVES = "agricultural_cooperatives", "Agricultural Cooperatives / Farmer Producer Organizations"
    FARMER_OWNED_ENTERPRISES = "farmer_owned_enterprises", "Farmer-owned enterprises"
    NGO_AGRICULTURE = (
        "ngo_agriculture",
        "Non-governmental organization / Non-profit organization focused on agriculture, fisheries, or animal husbandry",
    )
    FARM_MANAGEMENT = "farm_management", "Farm management"
    VILLAGE_COUNCILS = "village_councils", "Village councils"
    SELF_HELP_GROUPS = "self_help_groups", "Self-help groups"
    GOVERNMENT_AGRICULTURE = (
        "government_agriculture",
        "Government departments related to agriculture, fisheries, or animal husbandry",
    )
    BUSINESS_FUNCTIONS = (
        "business_functions",
        "Knowledge of key business functions (Marketing, Finance, Business Development, etc.)",
    )
    ANY_OTHER = "any_other", "Any other"


class BoardExperienceType(models.TextChoices):
    FARMER_OWNED_ENTERPRISES = "farmer_owned_enterprises", "Farmer-owned enterprises"
    AGRICULTURAL_COOPERATIVES = "agricultural_cooperatives", "Agricultural Cooperatives/Farmer producer organizations"
    NGO_AGRICULTURE = (
        "ngo_agriculture",
        "Non-governmental organization / Non-profit organization focused on agricultural sector / fisheries / animal husbandry",
    )
    FARM_MANAGEMENT = "farm_management", "Farm Management"
    VILLAGE_COUNCILS = "village_councils", "Village councils"
    SELF_HELP_GROUPS = "self_help_groups", "Self-help groups"
    GOVERNMENT_AGRICULTURE = (
        "government_agriculture",
        "Governmental departments of agricultural sector / fisheries / animal husbandry",
    )
    ANY_OTHER = "any_other", "Any other"


class PriceVolatilityType(models.TextChoices):
    HIGHLY_VOLATILE_FPO_RISK = (
        "highly_volatile_fpo_risk",
        "FPO dealing in highly price sensitive/volatile commodities (oil seed, gram etc) and price risk borne by the FPO",
    )
    MSP_FPO_RISK = "msp_fpo_risk", "Commodities with MSP, but price risk on FPO"
    PARTIAL_HEDGE = "partial_hedge", "Part of the commodities hedged against price risk/or non volatile commodities"
    WELL_HEDGED = "well_hedged", "Price risk covered through well defined hedging through NCDEX or other mediums"
    NOT_APPLICABLE = "not_applicable", "Not applicable - FPO only in lending/supplying inputs"


class InputTimelinessType(models.TextChoices):
    THIRTY_DAYS = "30_days_prior", "30 days prior to the sowing season"
    TWENTY_DAYS = "20_days_prior", "20 days prior to the sowing season"
    FIFTEEN_DAYS = "15_days_prior", "15 days prior to the sowing season"
    SEVEN_DAYS = "7_days_prior", "7 days prior to the sowing season"
    NOT_APPLICABLE = "not_applicable", "Not Applicable"


class PriceAffordabilityType(models.TextChoices):
    TEN_TO_FIFTEEN_PERCENT = "10_15_percent_less", "Available to member farmers at 10% - 15% less than market price"
    FIVE_TO_TEN_PERCENT = "5_10_percent_less", "Available to member farmers at 5% - 10% less than market price"
    THREE_TO_FIVE_PERCENT = "3_5_percent_less", "Available to member farmers at 3% - 5% less than market price"
    ONE_TO_THREE_PERCENT = "1_3_percent_less", "Available to member farmers at 1% - 3% less than market price"
    NOT_APPLICABLE = "not_applicable", "Not Applicable"


class DistanceAvailabilityType(models.TextChoices):
    THREE_KM = "3_km_available", "Available within 3 KM of distance for majority of farmers"
    SIX_KM = "6_km_available", "Available within 6 KM of distance for the majority of farmers"
    TEN_KM = "10_km_available", "Available within 10 KM of distance for majority of farmers"
    NOT_WITHIN_TEN_KM = "not_within_10_km", "Not available within 10 KM of distance for majority of farmers"
    NOT_APPLICABLE = "not_applicable", "Not Applicable"


class AccountsMISType(models.TextChoices):
    NO_MIS = "no_mis", "No MIS is present"
    MS_OFFICE_TOOLS = "ms_office_tools", "Accounting managed by using basic MS Office tools but not software packages"
    TALLY_NO_DIGITAL = (
        "tally_no_digital",
        "Accounting managed by tally, but no digitalization of the other operational records",
    )
    SOFTWARE_DIGITAL = "software_digital", "Software for managing accounts & digitalization of MIS"


class InsuranceStockType(models.TextChoices):
    NO_INSURANCE = "no_insurance", "No insurance cover"
    LESS_THAN_50_FIRE = "less_than_50_fire", "Less than 50% of the stock is insured against fire"
    FIFTY_PERCENT_FIRE_THEFT = "50_fire_theft", "50% of the stock is insured against fire & theft"
    HUNDRED_PERCENT_FIRE_THEFT = "100_fire_theft", "100% stock is insured against fire & theft"


class CreditRecordType(models.TextChoices):
    NO_CREDIT_HISTORY = "no_credit_history", "No Credit History"
    MULTIPLE_DELAYS = "multiple_delays", "More than one record of delays/defaults in the last 3 financial years"
    ONE_DELAY = "one_delay", "One record of delays/defaults in last 3 financial years"
    NO_DELAYS = "no_delays", "No records of delays or default"


class StatutoryFillingsType(models.TextChoices):
    DELAYS_NOT_FILLED = "delays_not_filled", "Any delays in the past 12 months that are not yet filled"
    MULTIPLE_DELAYS_FILLED = (
        "multiple_delays_filled",
        "Multiple delays (>5) over the past 12 months but filled as on date",
    )
    FEW_DELAYS_FILLED = "few_delays_filled", "Few delays (<3) over the past 12 months but filled as on date"
    NO_DELAYS = "no_delays", "No delays"


class BooksRecordsType(models.TextChoices):
    PROCESSES_SYSTEMS = "processes_systems", "Processes and Systems (E)"
    MONTHLY_OR_MORE = "monthly_or_more", "Updated on monthly or more basis"
    WEEKLY_UPDATED = "weekly_updated", "Updated on weekly basis"
    LAG_2_3_DAYS = "lag_2_3_days", "Updated with a lag of 2-3 days"
    CURRENT = "current", "Current"


class ReconciliationStocksType(models.TextChoices):
    ABSENT_ANNUAL = "absent_annual", "Absent or Annual"
    TWO_TO_FOUR_TIMES = "2_4_times_year", "2-4 times in a year"
    MONTHLY = "monthly", "Monthly"
    EVERY_15_DAYS = "every_15_days", "At least every 15 days"


class InstitutionalLendingHistoryType(models.TextChoices):
    NO_HISTORY = "no_history", "No history of institutional lending"
    AT_LEAST_ONE = "at_least_one", "At least 1 institutional lending in last 2 financial year"
    REPEATED_LENDING = (
        "repeated_lending",
        "History Repeated lending from any institutional lenders in last 2 financial years",
    )


class FPOVerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending verification"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class FPOQuerySet(models.QuerySet):
    def publicly_visible(self):
        """FPOs that may be exposed in public listings and report aggregates."""
        return self.filter(
            is_active=True,
            verification_status=FPOVerificationStatus.APPROVED,
        )


class FPO(models.Model):
    # Basic Information
    name = models.CharField(max_length=200, unique=True)
    logo = models.ImageField(upload_to="fpo_logos/", blank=True, null=True)

    # Contact Information
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    alternate_phone = models.CharField(max_length=15, blank=True)

    # Address Fields
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)

    # Store Link
    store_link = models.URLField(max_length=500, blank=True, null=True, help_text="Link to the FPO's online store")

    # Status and Metadata
    is_active = models.BooleanField(default=True)
    verification_status = models.CharField(
        max_length=20,
        choices=FPOVerificationStatus.choices,
        default=FPOVerificationStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fpo_verification_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="fpos_created")

    objects = FPOQuerySet.as_manager()

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        address_parts = [self.address_line_1]
        if self.address_line_2:
            address_parts.append(self.address_line_2)
        address_parts.extend([self.city, self.district, self.state, self.pincode])
        return ", ".join(filter(None, address_parts))

    @property
    def contact_person_name(self):
        """Best-effort contact person display name.

        Prefers the first active admin member's name; falls back to creator.
        """
        try:
            admin_member = self.get_admin_members().first()
        except Exception:
            admin_member = None

        if admin_member and admin_member.user:
            full_name = admin_member.user.get_full_name()
            return full_name or admin_member.user.username

        if self.created_by:
            full_name = self.created_by.get_full_name()
            return full_name or self.created_by.username

        return None

    def get_admin_members(self):
        """Return a list of admin members for this FPO"""
        return self.members.filter(role="admin", is_active=True).select_related("user")

    @property
    def is_verified(self):
        return self.verification_status == FPOVerificationStatus.APPROVED

    def approve_verification(self, user, notes=""):
        self.verification_status = FPOVerificationStatus.APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.verification_notes = notes
        self.save(
            update_fields=[
                "verification_status",
                "reviewed_by",
                "reviewed_at",
                "verification_notes",
                "updated_at",
            ]
        )

    def reject_verification(self, user, notes=""):
        self.verification_status = FPOVerificationStatus.REJECTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.verification_notes = notes
        self.save(
            update_fields=[
                "verification_status",
                "reviewed_by",
                "reviewed_at",
                "verification_notes",
                "updated_at",
            ]
        )

    class Meta:
        verbose_name = "FPO"
        verbose_name_plural = "FPOs"
        ordering = ["name"]
        permissions = [("verify_fpo", "Can approve or reject FPO verification")]


class FPOMember(models.Model):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("viewer", "Viewer"),
    ]

    fpo = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="viewer")
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["fpo", "user"]
        verbose_name = "FPO Member"
        verbose_name_plural = "FPO Members"
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.fpo.name} ({self.role})"


class YearlySubmissionQuerySet(models.QuerySet):
    def reportable(self):
        """Submissions belonging to active, admin-approved FPO profiles."""
        return self.filter(
            fpo__is_active=True,
            fpo__verification_status=FPOVerificationStatus.APPROVED,
        )


class YearlySubmission(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("revision_required", "Revision Required"),
    ]

    fpo = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name="yearly_submissions")
    financial_year = models.CharField(max_length=9, help_text="Format: 2023-2024")

    # Submission details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="submissions_made")
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Approval workflow
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="submissions_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approval_comments = models.TextField(blank=True, help_text="Comments from reviewer")

    # Score fields - calculated on save
    calculated_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Automatically calculated FPO score"
    )
    governance_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Governance section percentage score"
    )
    business_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Business & Operations section percentage score",
    )
    process_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Process & Systems section percentage score"
    )
    financial_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Financial Performance section percentage score",
    )

    governance_raw_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Raw governance score"
    )
    business_raw_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Raw business operations score"
    )
    financial_raw_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Raw financial performance score"
    )

    process_raw_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Raw process & systems score"
    )

    objects = YearlySubmissionQuerySet.as_manager()

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["fpo", "financial_year"]
        verbose_name = "Yearly Submission"
        verbose_name_plural = "Yearly Submissions"
        ordering = ["-financial_year", "-created_at"]

    def __str__(self):
        return f"{self.fpo.name} - {self.financial_year} ({self.get_status_display()})"

    @property
    def year(self):
        """Extract the starting year from financial_year (e.g., '2023-24' -> 2023)"""
        if self.financial_year and "-" in self.financial_year:
            try:
                return int(self.financial_year.split("-")[0])
            except (ValueError, IndexError):
                pass
        return None

    def can_edit(self):
        return self.status in ["draft", "revision_required"]

    def can_submit(self):
        return self.status == "draft"

    def submit_for_review(self, user):
        if self.can_submit():
            self.status = "submitted"
            self.submitted_by = user
            self.submitted_at = timezone.now()
            self.save()
            return True
        return False

    def approve(self, user, comments=""):
        self.status = "approved"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.approval_comments = comments
        self.save()

    def reject(self, user, comments=""):
        self.status = "rejected"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.approval_comments = comments
        self.save()

    def request_revision(self, user, comments=""):
        self.status = "revision_required"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.approval_comments = comments
        self.save()

    def save(self, *args, **kwargs):
        """Override save method to calculate and store the score."""
        # Skip calculation during import
        skip_calc = kwargs.pop("skip_score_calculation", False)

        if not skip_calc:
            try:
                # Calculate score before saving using the v2 score calculator
                from .score_calculator_v2 import FPOScoreCalculator

                calculator = FPOScoreCalculator(self)
                self.calculated_score = calculator.calculate_total_score()

                # Store individual section scores
                section_scores = calculator.get_section_scores()

                print(f"DEBUG - Section scores from calculator: {section_scores}")

                self.governance_score = section_scores["governance"]
                self.business_score = section_scores["business"]
                self.process_score = section_scores["process"]
                self.financial_score = section_scores["financial"]

                print(
                    f"DEBUG - Saving to DB: Gov={self.governance_score}, Biz={self.business_score}, Fin={self.financial_score}, Proc={self.process_score}"
                )

                raw_scores = calculator.get_raw_scores()
                self.governance_raw_score = raw_scores["governance"]
                self.business_raw_score = raw_scores["business"]
                self.financial_raw_score = raw_scores["financial"]
                self.process_raw_score = raw_scores["process"]
            except Exception as e:
                import traceback
                import decimal

                print(f"Error in score calculation: {e}")
                print(traceback.format_exc())

                # Set all scores to 0 if any error occurs
                self.calculated_score = 0
                self.governance_score = 0
                self.business_score = 0
                self.process_score = 0
                self.financial_score = 0
                self.governance_raw_score = 0
                self.business_raw_score = 0
                self.financial_raw_score = 0
                self.process_raw_score = 0

        super().save(*args, **kwargs)

    def _calculate_total_score(self):
        """Legacy method - kept for backward compatibility."""
        from .score_calculator_v2 import FPOScoreCalculator

        calculator = FPOScoreCalculator(self)
        return calculator.calculate_total_score()

    def _get_age_based_weights(self, age):
        """Get weight distribution based on FPO age."""
        if age < 1:
            return {"governance": 40, "business": 20, "process": 25, "financial": 15}
        elif 1 <= age < 3:
            return {"governance": 35, "business": 20, "process": 25, "financial": 20}
        elif 3 <= age < 5:
            return {"governance": 30, "business": 25, "process": 20, "financial": 25}
        else:  # 5+ years
            return {"governance": 25, "business": 30, "process": 15, "financial": 30}

    def _calculate_governance_score(self, governance, board_directors):
        """Calculate governance and management score."""
        raise "DO NOT USE"

    def _calculate_business_score(self, fpo_details):
        """Calculate business and operations score."""
        raise "DO NOT USE"

    def _calculate_process_score(self):
        raise "DO NOT USE"

    def _calculate_financial_score(self, financial_details):
        """Calculate financial performance score."""
        raise "DO NOT USE"


# Additional Choices for Submission Models
class SecondLineManagementType(models.TextChoices):
    CEO_WITH_ACCOUNTS_TWO_MANAGERS = (
        "ceo_accounts_two_managers",
        "CEO accompanied by accounts team & atleast 2 divisional manager (eg: marketing, sales, procurement)",
    )
    CEO_WITH_ACCOUNTS_ONE_MANAGER = (
        "ceo_accounts_one_manager",
        "CEO accompanied by accounts team & one divisional manager (eg: marketing, sales, procurement)",
    )
    CEO_WITH_ACCOUNTS = "ceo_with_accounts", "No second line, CEO accompanied by accounts team"
    ONLY_CEO = "only_ceo", "No second line, only CEO"
    NO_CEO = "no_ceo", "Currently no CEO"


class ActRegisteredType(models.TextChoices):
    COMPANY_ACT = "company_act", "Company Act"
    COOPERATIVE_SOCIETIES_ACT = "cooperative_societies_act", "Co-operative Societies Act"
    OTHER = "other", "Other"


# Submission Models
class FPODetailsSubmission(models.Model):
    yearly_submission = models.OneToOneField(YearlySubmission, on_delete=models.CASCADE, related_name="fpo_details")
    name_of_producer_organization = models.CharField(max_length=500)
    registered_address = models.TextField(max_length=1000)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    type_of_producer_organization = models.CharField(max_length=50, choices=ProducerOrgType.choices)
    date_of_incorporation = models.DateField()
    date_of_commencement = models.DateField()
    age_of_fpo_years = models.FloatField()
    type_of_fpo = models.CharField(max_length=50, choices=FPOType.choices)
    size_of_fpo_fy_23_24 = models.IntegerField(null=True, blank=True)
    size_of_fpo_fy_22_23 = models.IntegerField(null=True, blank=True)
    size_of_fpo_fy_21_22 = models.IntegerField(null=True, blank=True)
    farmers_transacted = models.IntegerField(null=True, blank=True)
    women_members = models.IntegerField(null=True, blank=True)
    target_size_of_fpo = models.IntegerField(null=True, blank=True)
    deals_through_pgs_figs = models.BooleanField(null=True, blank=True)
    num_pgs_figs = models.IntegerField(null=True, blank=True)
    supported_by_promoting_agency = models.BooleanField(null=True, blank=True)
    promoting_agency_name = models.CharField(max_length=200, blank=True)
    type_of_promoting_agency = models.CharField(max_length=50, choices=PromotingAgencyType.choices, blank=True)
    other_promoting_agency_type = models.CharField(max_length=200, blank=True)
    received_grants = models.BooleanField(null=True, blank=True)
    grant_making_organization = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FPO Details Submission"
        verbose_name_plural = "FPO Details Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - FPO Details - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class GovernanceSubmission(models.Model):
    yearly_submission = models.OneToOneField(YearlySubmission, on_delete=models.CASCADE, related_name="governance")
    annual_general_body_meetings = models.IntegerField()
    bod_meetings_last_financial_year = models.IntegerField()
    minutes_maintenance = models.CharField(max_length=50, choices=MinutesMaintenanceType.choices)
    num_bods = models.IntegerField()
    num_women_bods = models.IntegerField()
    second_line_management = models.CharField(max_length=50, choices=SecondLineManagementType.choices, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Governance Submission"
        verbose_name_plural = "Governance Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - Governance - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class CEOProfileSubmission(models.Model):
    yearly_submission = models.OneToOneField(YearlySubmission, on_delete=models.CASCADE, related_name="ceo_profile")
    name = models.CharField(max_length=200)
    qualification = models.CharField(max_length=500)
    type_of_experience = models.CharField(max_length=50, choices=ExperienceType.choices)
    other_experience_type = models.CharField(max_length=300, blank=True)
    total_years_of_experience = models.IntegerField()
    number_of_years_associated = models.IntegerField(help_text="Number of years associated with the FPO", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CEO Profile Submission"
        verbose_name_plural = "CEO Profile Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - CEO Profile - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class BoardDirectorProfile(models.Model):
    yearly_submission = models.ForeignKey(YearlySubmission, on_delete=models.CASCADE, related_name="board_directors")
    name = models.CharField(max_length=200)
    educational_qualification = models.CharField(max_length=500)
    type_of_experience = models.CharField(max_length=50, choices=BoardExperienceType.choices)
    other_experience = models.CharField(max_length=300, blank=True)
    total_years_of_experience = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Board Director Profile"
        verbose_name_plural = "Board Director Profiles"

    def __str__(self):
        return f"{self.name} - {self.yearly_submission.fpo.name} - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class BusinessOperationsSubmission(models.Model):
    yearly_submission = models.OneToOneField(
        YearlySubmission, on_delete=models.CASCADE, related_name="business_operations"
    )
    price_volatility_of_products = models.CharField(max_length=50, choices=PriceVolatilityType.choices)
    accessibility_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    availability_of_inputs_timeliness = models.CharField(max_length=50, choices=InputTimelinessType.choices, blank=True)
    availability_of_inputs_price_affordability = models.CharField(
        max_length=50, choices=PriceAffordabilityType.choices, blank=True
    )
    availability_of_inputs_place = models.CharField(max_length=50, choices=DistanceAvailabilityType.choices, blank=True)
    distance_of_output_collection_centres = models.CharField(max_length=50, blank=True)
    electronic_weighing_machines = models.BooleanField(null=True, blank=True)
    transportation_facility = models.BooleanField(null=True, blank=True)
    storage = models.BooleanField(null=True, blank=True)
    cleaning = models.BooleanField(null=True, blank=True)
    grading_and_sorting = models.BooleanField(null=True, blank=True)
    chilling = models.BooleanField(null=True, blank=True)
    packaging = models.BooleanField(null=True, blank=True)
    labelling = models.BooleanField(null=True, blank=True)
    processing = models.BooleanField(null=True, blank=True)
    quality_check = models.BooleanField(null=True, blank=True)
    soil_testing_facility = models.BooleanField(null=True, blank=True)
    custom_hiring_centers = models.BooleanField(null=True, blank=True)
    contract_farming = models.BooleanField(null=True, blank=True)
    advisory_services = models.BooleanField(null=True, blank=True)
    credit_facilities = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Operations Submission"
        verbose_name_plural = "Business Operations Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - Business Operations - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class ComplianceDetailsSubmission(models.Model):
    yearly_submission = models.OneToOneField(
        YearlySubmission, on_delete=models.CASCADE, related_name="compliance_details"
    )
    act_under_registered = models.CharField(max_length=50, choices=ActRegisteredType.choices)
    date_of_registration = models.DateField()
    place_of_registration = models.CharField(max_length=200)
    registration_no = models.CharField(max_length=100)
    incorporation_date = models.DateField(null=True, blank=True)
    incorporation_place = models.CharField(max_length=200, blank=True)
    incorporation_reg_no = models.CharField(max_length=100, blank=True)
    commencement_date = models.DateField(null=True, blank=True)
    commencement_place = models.CharField(max_length=200, blank=True)
    commencement_reg_no = models.CharField(max_length=100, blank=True)
    gst_date = models.DateField(null=True, blank=True)
    gst_place = models.CharField(max_length=200, blank=True)
    gst_reg_no = models.CharField(max_length=100, blank=True)
    permanent_account_number = models.CharField(max_length=10)
    tax_account_number = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Compliance Details Submission"
        verbose_name_plural = "Compliance Details Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - Compliance - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class ProcessesSystemsSubmission(models.Model):
    yearly_submission = models.OneToOneField(
        YearlySubmission, on_delete=models.CASCADE, related_name="processes_systems"
    )
    accounts_and_mis = models.CharField(max_length=50, choices=AccountsMISType.choices)
    insurance_of_stock = models.CharField(max_length=50, choices=InsuranceStockType.choices)
    credit_record_of_fpo = models.CharField(max_length=50, choices=CreditRecordType.choices)
    statutory_fillings = models.CharField(max_length=50, choices=StatutoryFillingsType.choices)
    books_and_records_up_to_date = models.CharField(max_length=50, choices=BooksRecordsType.choices)
    reconciliation_of_stocks = models.CharField(max_length=50, choices=ReconciliationStocksType.choices)
    penalties_levied_board_meeting = models.BooleanField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Processes Systems Submission"
        verbose_name_plural = "Processes Systems Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - Processes & Systems - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()


class SustainableActivitiesSubmission(models.Model):
    yearly_submission = models.OneToOneField(
        YearlySubmission, on_delete=models.CASCADE, related_name="sustainable_activities"
    )
    climate_resilient_seeds_to_farmers = models.BooleanField()
    organic_bio_manure_fertilizers_to_farmers = models.BooleanField()
    composting_units_at_fpo_level = models.BooleanField()
    drip_sprinkler_irrigation_to_farmers = models.BooleanField()
    pest_disease_alerts_to_farmers = models.BooleanField()
    weather_advisories_to_farmers = models.BooleanField()
    supplying_agricultural_residue_to_bio_cng_gas_plants = models.BooleanField()
    training_on_organic_farming_to_farmers = models.BooleanField()
    solar_panels_at_fpo_level = models.BooleanField()
    establishment_of_rainwater_harvesting_at_fpo_level = models.BooleanField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sustainable Activities Submission"
        verbose_name_plural = "Sustainable Activities Submissions"

    def __str__(self):
        return f"{self.yearly_submission.fpo.name} - Sustainable Activities - {self.yearly_submission.financial_year}"

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        super().save(*args, **kwargs)
        # Recalculate the parent submission score
        self.yearly_submission.save()


class FinancialDetailsSubmissionV2(models.Model):
    yearly_submission = models.OneToOneField(
        YearlySubmission, on_delete=models.CASCADE, related_name="financial_details_v2"
    )

    # Revenue details for last 3 financial years
    current_year_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Revenue for current financial year (INR)"
    )
    previous_year_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Revenue for previous financial year (INR)"
    )
    two_years_back_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Revenue for 2 years back financial year (INR)"
    )

    # Product names for revenue
    current_year_products = models.TextField(
        blank=True, null=True, help_text="Name of products for current year revenue"
    )
    previous_year_products = models.TextField(
        blank=True, null=True, help_text="Name of products for previous year revenue"
    )
    two_years_back_products = models.TextField(
        blank=True, null=True, help_text="Name of products for 2 years back revenue"
    )

    # Target revenue
    target_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Target revenue (INR)"
    )

    # Quantity procured (Metric tonnes)
    current_year_quantity_procured = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Quantity procured current year (Metric tonnes)"
    )
    current_year_quantity_products = models.TextField(
        blank=True, null=True, help_text="Name of products for current year quantity procured"
    )
    previous_year_quantity_procured = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Quantity procured previous year (Metric tonnes)"
    )
    previous_year_quantity_products = models.TextField(
        blank=True, null=True, help_text="Name of products for previous year quantity procured"
    )
    two_years_back_quantity_procured = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Quantity procured 2 years back (Metric tonnes)"
    )
    two_years_back_quantity_products = models.TextField(
        blank=True, null=True, help_text="Name of products for 2 years back quantity procured"
    )

    # Retail buying details
    current_year_retail_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Retail buying revenue current year (INR)"
    )
    current_year_retail_products = models.TextField(
        blank=True, null=True, help_text="Name of products for current year retail buying"
    )
    previous_year_retail_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Retail buying revenue previous year (INR)"
    )
    previous_year_retail_products = models.TextField(
        blank=True, null=True, help_text="Name of products for previous year retail buying"
    )
    two_years_back_retail_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Retail buying revenue 2 years back (INR)"
    )
    two_years_back_retail_products = models.TextField(
        blank=True, null=True, help_text="Name of products for 2 years back retail buying"
    )

    # Wholesale buying details
    current_year_wholesale_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Wholesale buying revenue current year (INR)"
    )
    current_year_wholesale_products = models.TextField(
        blank=True, null=True, help_text="Name of products for current year wholesale buying"
    )
    previous_year_wholesale_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Wholesale buying revenue previous year (INR)"
    )
    previous_year_wholesale_products = models.TextField(
        blank=True, null=True, help_text="Name of products for previous year wholesale buying"
    )
    two_years_back_wholesale_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Wholesale buying revenue 2 years back (INR)"
    )
    two_years_back_wholesale_products = models.TextField(
        blank=True, null=True, help_text="Name of products for 2 years back wholesale buying"
    )

    # Institutional buying details
    current_year_institutional_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Institutional buying revenue current year (INR)"
    )
    current_year_institutional_products = models.TextField(
        blank=True, null=True, help_text="Name of products for current year institutional buying"
    )
    previous_year_institutional_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Institutional buying revenue previous year (INR)"
    )
    previous_year_institutional_products = models.TextField(
        blank=True, null=True, help_text="Name of products for previous year institutional buying"
    )
    two_years_back_institutional_revenue = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Institutional buying revenue 2 years back (INR)"
    )
    two_years_back_institutional_products = models.TextField(
        blank=True, null=True, help_text="Name of products for 2 years back institutional buying"
    )

    # Cost of Goods Sold
    current_year_cogs = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Cost of Goods Sold current year (INR)"
    )
    previous_year_cogs = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Cost of Goods Sold previous year (INR)"
    )
    two_years_back_cogs = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Cost of Goods Sold 2 years back (INR)"
    )

    # Profit details
    current_year_gross_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Gross profit current year (INR)"
    )
    current_year_net_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Net profit current year (INR)"
    )
    previous_year_gross_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Gross profit previous year (INR)"
    )
    previous_year_net_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Net profit previous year (INR)"
    )
    two_years_back_gross_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Gross profit 2 years back (INR)"
    )
    two_years_back_net_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Net profit 2 years back (INR)"
    )

    # Operating and margin details
    operating_margin_current_year = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Operating margin current year (%)"
    )
    gross_net_profit_margin_difference = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Difference between Gross and Net Profit Margin (%)"
    )

    # Share capital and shareholders
    current_year_share_capital = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Share capital current year (INR)"
    )
    current_year_shareholders = models.IntegerField(help_text="Number of shareholders current year")
    previous_year_share_capital = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Share capital previous year (INR)"
    )
    previous_year_shareholders = models.IntegerField(help_text="Number of shareholders previous year")
    two_years_back_share_capital = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Share capital 2 years back (INR)"
    )
    two_years_back_shareholders = models.IntegerField(help_text="Number of shareholders 2 years back")

    # Accounts Payable/Receivable
    current_year_accounts_payable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Payable current year (INR)"
    )
    current_year_accounts_receivable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Receivable current year (INR)"
    )
    previous_year_accounts_payable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Payable previous year (INR)"
    )
    previous_year_accounts_receivable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Receivable previous year (INR)"
    )
    two_years_back_accounts_payable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Payable 2 years back (INR)"
    )
    two_years_back_accounts_receivable = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Accounts Receivable 2 years back (INR)"
    )

    # Inventory details
    current_year_opening_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Opening Inventory current year (INR)"
    )
    current_year_closing_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Closing Inventory current year (INR)"
    )
    previous_year_opening_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Opening Inventory previous year (INR)"
    )
    previous_year_closing_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Closing Inventory previous year (INR)"
    )
    two_years_back_opening_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Opening Inventory 2 years back (INR)"
    )
    two_years_back_closing_inventory = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Closing Inventory 2 years back (INR)"
    )

    # Grant details
    current_year_project_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Project Grant current year (INR)"
    )
    current_year_matching_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Matching Grant current year (INR)"
    )
    previous_year_project_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Project Grant previous year (INR)"
    )
    previous_year_matching_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Matching Grant previous year (INR)"
    )
    two_years_back_project_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Project Grant 2 years back (INR)"
    )
    two_years_back_matching_grant = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Matching Grant 2 years back (INR)"
    )

    # Net Worth details
    current_year_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Assets current year (INR)"
    )
    current_year_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Liabilities current year (INR)"
    )
    previous_year_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Assets previous year (INR)"
    )
    previous_year_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Liabilities previous year (INR)"
    )
    two_years_back_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Assets 2 years back (INR)"
    )
    two_years_back_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Liabilities 2 years back (INR)"
    )

    # Current ratio details
    current_year_current_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Assets current year (INR)"
    )
    current_year_current_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Liabilities current year (INR)"
    )
    previous_year_current_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Assets previous year (INR)"
    )
    previous_year_current_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Liabilities previous year (INR)"
    )
    two_years_back_current_assets = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Assets 2 years back (INR)"
    )
    two_years_back_current_liabilities = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Current Liabilities 2 years back (INR)"
    )

    # Credit history
    current_year_lender_name = models.CharField(
        max_length=255, blank=True, null=True, help_text="Name of lender current year"
    )
    current_year_loan_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Loan amount current year (INR)"
    )
    previous_year_lender_name = models.CharField(
        max_length=255, blank=True, null=True, help_text="Name of lender previous year"
    )
    previous_year_loan_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Loan amount previous year (INR)"
    )
    two_years_back_lender_name = models.CharField(
        max_length=255, blank=True, null=True, help_text="Name of lender 2 years back"
    )
    two_years_back_loan_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Loan amount 2 years back (INR)"
    )

    # Additional financial metrics
    cash_cheque_percentage = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Cash/Cheque dealing as % of total revenue"
    )
    days_payable_receivable_difference = models.IntegerField(
        default=0, help_text="Difference in Days Accounts Payable and Days Accounts Receivable"
    )
    total_debt_today = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Total debt as of today (INR)"
    )

    # History fields
    institutional_lending_history = models.TextField(
        blank=True, null=True, help_text="History of Institutional Lending in last 2 financial years"
    )
    credit_default_year = models.CharField(max_length=20, blank=True, null=True, help_text="Year of credit default")
    credit_default_lender = models.CharField(
        max_length=255, blank=True, null=True, help_text="Name of lender for credit default"
    )
    credit_default_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, help_text="Credit default loan amount (INR)"
    )

    # Loan details (JSON field for flexible loan information)
    loan_details = models.JSONField(
        default=dict, blank=True, help_text="JSON field containing detailed loan information"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Financial Details Submission V2"
        verbose_name_plural = "Financial Details Submissions V2"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Override save to recalculate parent submission score."""
        skip_calc = kwargs.pop("skip_score_calculation", False)
        super().save(*args, **kwargs)
        # Only recalculate if not skipping
        if not skip_calc:
            self.yearly_submission.save()

    def __str__(self):
        return f"Financial Details - {self.yearly_submission}"

    @property
    def current_year_net_worth(self):
        """Calculate current year net worth"""
        return self.current_year_assets - self.current_year_liabilities

    @property
    def previous_year_net_worth(self):
        """Calculate previous year net worth"""
        return self.previous_year_assets - self.previous_year_liabilities

    @property
    def two_years_back_net_worth(self):
        """Calculate 2 years back net worth"""
        return self.two_years_back_assets - self.two_years_back_liabilities

    @property
    def current_year_current_ratio(self):
        """Calculate current year current ratio"""
        from decimal import Decimal, DivisionByZero, InvalidOperation

        if self.current_year_current_liabilities and self.current_year_current_liabilities > 0:
            try:
                result = self.current_year_current_assets / self.current_year_current_liabilities
                return result.quantize(Decimal("0.00")) if result else Decimal("0.00")
            except (DivisionByZero, InvalidOperation):
                return Decimal("0.00")
        return Decimal("0.00")

    @property
    def previous_year_current_ratio(self):
        """Calculate previous year current ratio"""
        from decimal import Decimal, DivisionByZero, InvalidOperation

        if self.previous_year_current_liabilities and self.previous_year_current_liabilities > 0:
            try:
                result = self.previous_year_current_assets / self.previous_year_current_liabilities
                return result.quantize(Decimal("0.00")) if result else Decimal("0.00")
            except (DivisionByZero, InvalidOperation):
                return Decimal("0.00")
        return Decimal("0.00")

    @property
    def two_years_back_current_ratio(self):
        """Calculate 2 years back current ratio"""
        from decimal import Decimal, DivisionByZero, InvalidOperation

        if self.two_years_back_current_liabilities and self.two_years_back_current_liabilities > 0:
            try:
                result = self.two_years_back_current_assets / self.two_years_back_current_liabilities
                return result.quantize(Decimal("0.00")) if result else Decimal("0.00")
            except (DivisionByZero, InvalidOperation):
                return Decimal("0.00")
        return Decimal("0.00")

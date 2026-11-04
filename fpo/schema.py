import logging
from decimal import Decimal, InvalidOperation

import graphene
from django.contrib.auth import get_user_model
from django.db import connection, models
from django.utils import timezone
from graphene import relay
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
import django_filters
from graphql_jwt.decorators import login_required

from fpo.score_calculator_v2 import FPOScoreCalculator

from .models import (
    ProducerOrgType,
    FPOType,
    PromotingAgencyType,
    MinutesMaintenanceType,
    ExperienceType,
    BoardExperienceType,
    PriceVolatilityType,
    InputTimelinessType,
    PriceAffordabilityType,
    DistanceAvailabilityType,
    AccountsMISType,
    InsuranceStockType,
    CreditRecordType,
    StatutoryFillingsType,
    BooksRecordsType,
    ReconciliationStocksType,
    SecondLineManagementType,
    ActRegisteredType,
)

from .models import (
    FPO,
    FPOVerificationStatus,
    FPOMember,
    YearlySubmission,
    FPODetailsSubmission,
    GovernanceSubmission,
    CEOProfileSubmission,
    BoardDirectorProfile,
    BusinessOperationsSubmission,
    ComplianceDetailsSubmission,
    ProcessesSystemsSubmission,
    FinancialDetailsSubmissionV2,
    SustainableActivitiesSubmission,
)

User = get_user_model()

logger = logging.getLogger(__name__)


def _zero_for_field(field):
    if isinstance(field, models.DecimalField):
        if field.decimal_places == 0:
            return Decimal("0")
        quantizer = Decimal("1").scaleb(-field.decimal_places)
        return Decimal("0").quantize(quantizer)
    if isinstance(field, models.IntegerField):
        return 0
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.TextField):
        return ""
    if field.has_default():
        return field.get_default()
    return None


def _sanitize_decimal(field, raw_value):
    if raw_value in (None, ""):
        return None if field.null else _zero_for_field(field)

    try:
        decimal_value = Decimal(str(raw_value))
        quantizer = Decimal("1").scaleb(-field.decimal_places)
        decimal_value = decimal_value.quantize(quantizer)

        digits_tuple = decimal_value.as_tuple().digits
        exponent = decimal_value.as_tuple().exponent
        digits_count = len(digits_tuple)
        decimal_places = -exponent if exponent < 0 else 0
        whole_digits = digits_count - decimal_places if digits_count > decimal_places else 0

        if (
            digits_count > field.max_digits
            or decimal_places > field.decimal_places
            or whole_digits > (field.max_digits - field.decimal_places)
        ):
            return _zero_for_field(field)

        return decimal_value
    except (InvalidOperation, TypeError, ValueError):
        return _zero_for_field(field)


def _sanitize_field(field, raw_value):
    if isinstance(field, models.DecimalField):
        return _sanitize_decimal(field, raw_value)

    if raw_value in (None, ""):
        return None if field.null else _zero_for_field(field)

    try:
        if isinstance(field, models.IntegerField):
            return int(raw_value)
        if isinstance(field, models.BooleanField):
            return field.to_python(raw_value)
        return field.to_python(raw_value)
    except (ValueError, TypeError, InvalidOperation):
        return _zero_for_field(field)


def _prepare_financial_defaults(input_data):
    sanitized = {}

    for field in FinancialDetailsSubmissionV2._meta.concrete_fields:
        if field.primary_key or isinstance(field, models.OneToOneField):
            continue

        key = field.name
        if key not in input_data:
            continue

        sanitized[key] = _sanitize_field(field, input_data.get(key))

    return sanitized


def _get_enum_value(enum_instance, default=""):
    """Extract value from graphene Enum instance or return default."""
    if enum_instance is None:
        return default
    return getattr(enum_instance, "value", default)


class FPONode(DjangoObjectType):
    verification_status = graphene.String(required=True)
    verification_notes = graphene.String(required=True)

    class Meta:
        model = FPO
        # User links would expose account details (email, username, flags) to API callers.
        exclude = ("created_by", "reviewed_by")
        filter_fields = {
            "name": ["exact", "icontains"],
            "is_active": ["exact"],
            "district": ["exact", "icontains"],
            "state": ["exact", "icontains"],
        }
        interfaces = (relay.Node,)

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_authenticated:
            if user.is_staff or user.is_superuser or user.has_perm("fpo.verify_fpo"):
                return queryset
            return queryset.filter(
                models.Q(verification_status=FPOVerificationStatus.APPROVED, is_active=True)
                | models.Q(members__user=user, members__is_active=True)
            ).distinct()
        return queryset.publicly_visible()

    def resolve_verification_status(self, info):
        return self.verification_status

    def resolve_verification_notes(self, info):
        user = info.context.user
        can_view_notes = user.is_authenticated and (
            user.is_staff
            or user.is_superuser
            or FPOMember.objects.filter(
                fpo=self,
                user=user,
                is_active=True,
            ).exists()
        )
        return self.verification_notes if can_view_notes else ""


def _build_safe_financial_details(submission):
    """Return sanitized financial details with per-field fallbacks."""

    placeholder = FinancialDetailsSubmissionV2()
    placeholder.yearly_submission = submission
    placeholder.yearly_submission_id = getattr(submission, "id", None)

    fallback_row = {}
    db_table = FinancialDetailsSubmissionV2._meta.db_table
    submission_id = getattr(submission, "id", None)

    if submission_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {db_table} WHERE yearly_submission_id = %s LIMIT 1",
                    [submission_id],
                )
                row = cursor.fetchone()
                if row is not None:
                    columns = [col[0] for col in cursor.description]
                    fallback_row = dict(zip(columns, row))
        except Exception:  # pragma: no cover - defensive fallback
            fallback_row = {}

    placeholder.id = fallback_row.get("id") or getattr(submission, "financial_details_v2_id", 0) or 0

    for field in FinancialDetailsSubmissionV2._meta.concrete_fields:
        if isinstance(field, models.OneToOneField):
            continue

        raw_value = fallback_row.get(field.column)
        sanitized_value = _sanitize_field(field, raw_value)
        setattr(placeholder, field.attname, sanitized_value)

    return placeholder


class YearlySubmissionNode(DjangoObjectType):
    calculated_score = graphene.Float(description="Automatically calculated FPO score")
    financial_details_v2 = graphene.Field(lambda: FinancialDetailsSubmissionV2Node, required=False)

    class Meta:
        model = YearlySubmission
        exclude = ("submitted_by", "reviewed_by")
        filter_fields = {
            "financial_year": ["exact"],
            "status": ["exact"],
            "fpo__name": ["exact", "icontains"],
        }
        interfaces = (relay.Node,)

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_authenticated:
            if user.is_staff or user.is_superuser or user.has_perm("fpo.verify_fpo"):
                return queryset
            # Non-members see what the public sees; members also see their own FPO's drafts.
            return (
                queryset.reportable().exclude(status="draft")
                | queryset.filter(fpo__members__user=user, fpo__members__is_active=True)
            ).distinct()
        return queryset.reportable().exclude(status="draft")

    def resolve_calculated_score(self, info):
        """Resolve the calculated score property."""
        return self.calculated_score


class FPODetailsSubmissionNode(DjangoObjectType):
    class Meta:
        model = FPODetailsSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class GovernanceSubmissionNode(DjangoObjectType):
    class Meta:
        model = GovernanceSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class CEOProfileSubmissionNode(DjangoObjectType):
    class Meta:
        model = CEOProfileSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class BoardDirectorProfileNode(DjangoObjectType):
    class Meta:
        model = BoardDirectorProfile
        fields = "__all__"
        interfaces = (relay.Node,)


class BusinessOperationsSubmissionNode(DjangoObjectType):
    class Meta:
        model = BusinessOperationsSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class ComplianceDetailsSubmissionNode(DjangoObjectType):
    class Meta:
        model = ComplianceDetailsSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class ProcessesSystemsSubmissionNode(DjangoObjectType):
    class Meta:
        model = ProcessesSystemsSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


class FinancialDetailsSubmissionV2Node(DjangoObjectType):
    class Meta:
        model = FinancialDetailsSubmissionV2
        fields = "__all__"
        interfaces = (relay.Node,)

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_authenticated:
            if user.is_staff or user.is_superuser:
                return queryset
            return queryset.filter(
                models.Q(
                    yearly_submission__fpo__is_active=True,
                    yearly_submission__fpo__verification_status=FPOVerificationStatus.APPROVED,
                )
                & ~models.Q(yearly_submission__status="draft")
                | models.Q(
                    yearly_submission__fpo__members__user=user,
                    yearly_submission__fpo__members__is_active=True,
                )
            ).distinct()
        return queryset.filter(
            yearly_submission__fpo__is_active=True,
            yearly_submission__fpo__verification_status=FPOVerificationStatus.APPROVED,
        ).exclude(yearly_submission__status="draft")


class FinancialDetailsSubmissionV2FilterSet(django_filters.FilterSet):
    class Meta:
        model = FinancialDetailsSubmissionV2
        fields = {
            "yearly_submission__financial_year": ["exact"],
            "yearly_submission__fpo__name": ["exact", "icontains"],
        }


class SustainableActivitiesSubmissionNode(DjangoObjectType):
    class Meta:
        model = SustainableActivitiesSubmission
        fields = "__all__"
        interfaces = (relay.Node,)


# Enum Types
class ProducerOrgTypeEnum(graphene.Enum):
    CO_OPERATIVE_SOCIETY = ProducerOrgType.CO_OPERATIVE_SOCIETY
    PRODUCER_COMPANY = ProducerOrgType.PRODUCER_COMPANY
    NON_PROFIT_SOCIETY = ProducerOrgType.NON_PROFIT_SOCIETY
    TRUST = ProducerOrgType.TRUST
    SECTION_8_COMPANY = ProducerOrgType.SECTION_8_COMPANY


class FPOTypeEnum(graphene.Enum):
    HIGH_CAPACITY = FPOType.HIGH_CAPACITY
    LOW_CAPACITY = FPOType.LOW_CAPACITY
    INPUTS_OR_OUTPUT = FPOType.INPUTS_OR_OUTPUT
    INPUTS_AND_OUTPUT = FPOType.INPUTS_AND_OUTPUT


class PromotingAgencyTypeEnum(graphene.Enum):
    NGO = PromotingAgencyType.NGO
    TRUSTS = PromotingAgencyType.TRUSTS
    COOPERATIVES = PromotingAgencyType.COOPERATIVES
    CORPORATE_WINGS = PromotingAgencyType.CORPORATE_WINGS
    STATE_GOVT = PromotingAgencyType.STATE_GOVT
    KVKS = PromotingAgencyType.KVKS
    FARMER_FEDERATIONS = PromotingAgencyType.FARMER_FEDERATIONS
    COMMODITY_BOARDS = PromotingAgencyType.COMMODITY_BOARDS
    BIG_FARMER_COMPANIES = PromotingAgencyType.BIG_FARMER_COMPANIES
    OTHERS = PromotingAgencyType.OTHERS


class MinutesMaintenanceTypeEnum(graphene.Enum):
    DETAILED_COMPLIANT = MinutesMaintenanceType.DETAILED_COMPLIANT
    DETAILED_NOT_UPDATED = MinutesMaintenanceType.DETAILED_NOT_UPDATED
    SKETCHY_QUALITY = MinutesMaintenanceType.SKETCHY_QUALITY
    NOT_MAINTAINED = MinutesMaintenanceType.NOT_MAINTAINED


class ExperienceTypeEnum(graphene.Enum):
    AGRICULTURAL_COOPERATIVES = ExperienceType.AGRICULTURAL_COOPERATIVES
    FARMER_OWNED_ENTERPRISES = ExperienceType.FARMER_OWNED_ENTERPRISES
    NGO_AGRICULTURE = ExperienceType.NGO_AGRICULTURE
    FARM_MANAGEMENT = ExperienceType.FARM_MANAGEMENT
    VILLAGE_COUNCILS = ExperienceType.VILLAGE_COUNCILS
    SELF_HELP_GROUPS = ExperienceType.SELF_HELP_GROUPS
    GOVERNMENT_AGRICULTURE = ExperienceType.GOVERNMENT_AGRICULTURE
    BUSINESS_FUNCTIONS = ExperienceType.BUSINESS_FUNCTIONS
    ANY_OTHER = ExperienceType.ANY_OTHER


class BoardExperienceTypeEnum(graphene.Enum):
    FARMER_OWNED_ENTERPRISES = BoardExperienceType.FARMER_OWNED_ENTERPRISES
    AGRICULTURAL_COOPERATIVES = BoardExperienceType.AGRICULTURAL_COOPERATIVES
    NGO_AGRICULTURE = BoardExperienceType.NGO_AGRICULTURE
    FARM_MANAGEMENT = BoardExperienceType.FARM_MANAGEMENT
    VILLAGE_COUNCILS = BoardExperienceType.VILLAGE_COUNCILS
    SELF_HELP_GROUPS = BoardExperienceType.SELF_HELP_GROUPS
    GOVERNMENT_AGRICULTURE = BoardExperienceType.GOVERNMENT_AGRICULTURE
    ANY_OTHER = BoardExperienceType.ANY_OTHER


class PriceVolatilityTypeEnum(graphene.Enum):
    HIGHLY_VOLATILE_FPO_RISK = PriceVolatilityType.HIGHLY_VOLATILE_FPO_RISK
    MSP_FPO_RISK = PriceVolatilityType.MSP_FPO_RISK
    PARTIAL_HEDGE = PriceVolatilityType.PARTIAL_HEDGE
    WELL_HEDGED = PriceVolatilityType.WELL_HEDGED
    NOT_APPLICABLE = PriceVolatilityType.NOT_APPLICABLE


class InputTimelinessTypeEnum(graphene.Enum):
    THIRTY_DAYS = InputTimelinessType.THIRTY_DAYS
    TWENTY_DAYS = InputTimelinessType.TWENTY_DAYS
    FIFTEEN_DAYS = InputTimelinessType.FIFTEEN_DAYS
    SEVEN_DAYS = InputTimelinessType.SEVEN_DAYS
    NOT_APPLICABLE = InputTimelinessType.NOT_APPLICABLE


class PriceAffordabilityTypeEnum(graphene.Enum):
    TEN_TO_FIFTEEN_PERCENT = PriceAffordabilityType.TEN_TO_FIFTEEN_PERCENT
    FIVE_TO_TEN_PERCENT = PriceAffordabilityType.FIVE_TO_TEN_PERCENT
    THREE_TO_FIVE_PERCENT = PriceAffordabilityType.THREE_TO_FIVE_PERCENT
    ONE_TO_THREE_PERCENT = PriceAffordabilityType.ONE_TO_THREE_PERCENT
    NOT_APPLICABLE = PriceAffordabilityType.NOT_APPLICABLE


class DistanceAvailabilityTypeEnum(graphene.Enum):
    THREE_KM = DistanceAvailabilityType.THREE_KM
    SIX_KM = DistanceAvailabilityType.SIX_KM
    TEN_KM = DistanceAvailabilityType.TEN_KM
    NOT_WITHIN_TEN_KM = DistanceAvailabilityType.NOT_WITHIN_TEN_KM
    NOT_APPLICABLE = DistanceAvailabilityType.NOT_APPLICABLE


class AccountsMISTypeEnum(graphene.Enum):
    NO_MIS = AccountsMISType.NO_MIS
    MS_OFFICE_TOOLS = AccountsMISType.MS_OFFICE_TOOLS
    TALLY_NO_DIGITAL = AccountsMISType.TALLY_NO_DIGITAL
    SOFTWARE_DIGITAL = AccountsMISType.SOFTWARE_DIGITAL


class InsuranceStockTypeEnum(graphene.Enum):
    NO_INSURANCE = InsuranceStockType.NO_INSURANCE
    LESS_THAN_50_FIRE = InsuranceStockType.LESS_THAN_50_FIRE
    FIFTY_PERCENT_FIRE_THEFT = InsuranceStockType.FIFTY_PERCENT_FIRE_THEFT
    HUNDRED_PERCENT_FIRE_THEFT = InsuranceStockType.HUNDRED_PERCENT_FIRE_THEFT


class CreditRecordTypeEnum(graphene.Enum):
    NO_CREDIT_HISTORY = CreditRecordType.NO_CREDIT_HISTORY
    MULTIPLE_DELAYS = CreditRecordType.MULTIPLE_DELAYS
    ONE_DELAY = CreditRecordType.ONE_DELAY
    NO_DELAYS = CreditRecordType.NO_DELAYS


class StatutoryFillingsTypeEnum(graphene.Enum):
    DELAYS_NOT_FILLED = StatutoryFillingsType.DELAYS_NOT_FILLED
    MULTIPLE_DELAYS_FILLED = StatutoryFillingsType.MULTIPLE_DELAYS_FILLED
    FEW_DELAYS_FILLED = StatutoryFillingsType.FEW_DELAYS_FILLED
    NO_DELAYS = StatutoryFillingsType.NO_DELAYS


class BooksRecordsTypeEnum(graphene.Enum):
    PROCESSES_SYSTEMS = BooksRecordsType.PROCESSES_SYSTEMS
    WEEKLY_UPDATED = BooksRecordsType.WEEKLY_UPDATED
    LAG_2_3_DAYS = BooksRecordsType.LAG_2_3_DAYS
    CURRENT = BooksRecordsType.CURRENT


class ReconciliationStocksTypeEnum(graphene.Enum):
    ABSENT_ANNUAL = ReconciliationStocksType.ABSENT_ANNUAL
    TWO_TO_FOUR_TIMES = ReconciliationStocksType.TWO_TO_FOUR_TIMES
    MONTHLY = ReconciliationStocksType.MONTHLY
    EVERY_15_DAYS = ReconciliationStocksType.EVERY_15_DAYS


class SecondLineManagementTypeEnum(graphene.Enum):
    CEO_WITH_ACCOUNTS_TWO_MANAGERS = SecondLineManagementType.CEO_WITH_ACCOUNTS_TWO_MANAGERS
    CEO_WITH_ACCOUNTS_ONE_MANAGER = SecondLineManagementType.CEO_WITH_ACCOUNTS_ONE_MANAGER
    CEO_WITH_ACCOUNTS = SecondLineManagementType.CEO_WITH_ACCOUNTS
    ONLY_CEO = SecondLineManagementType.ONLY_CEO
    NO_CEO = SecondLineManagementType.NO_CEO


class ActRegisteredTypeEnum(graphene.Enum):
    COMPANY_ACT = ActRegisteredType.COMPANY_ACT
    COOPERATIVE_SOCIETIES_ACT = ActRegisteredType.COOPERATIVE_SOCIETIES_ACT
    OTHER = ActRegisteredType.OTHER


# Input Types
class FPODetailsSubmissionInput(graphene.InputObjectType):
    name_of_producer_organization = graphene.String()
    registered_address = graphene.String()
    district = graphene.String()
    state = graphene.String()
    type_of_producer_organization = ProducerOrgTypeEnum()
    date_of_incorporation = graphene.Date()
    date_of_commencement = graphene.Date()
    age_of_fpo_years = graphene.Float()
    type_of_fpo = FPOTypeEnum()
    size_of_fpo_fy_23_24 = graphene.Int()
    size_of_fpo_fy_22_23 = graphene.Int()
    size_of_fpo_fy_21_22 = graphene.Int()
    farmers_transacted = graphene.Int()
    women_members = graphene.Int()
    target_size_of_fpo = graphene.Int()
    deals_through_pgs_figs = graphene.Boolean()
    num_pgs_figs = graphene.Int()
    supported_by_promoting_agency = graphene.Boolean()
    promoting_agency_name = graphene.String()
    type_of_promoting_agency = PromotingAgencyTypeEnum()
    other_promoting_agency_type = graphene.String()
    received_grants = graphene.Boolean()
    grant_making_organization = graphene.String()


class GovernanceSubmissionInput(graphene.InputObjectType):
    annual_general_body_meetings = graphene.Int()
    bod_meetings_last_financial_year = graphene.Int()
    minutes_maintenance = MinutesMaintenanceTypeEnum()
    num_bods = graphene.Int()
    num_women_bods = graphene.Int()
    second_line_management = SecondLineManagementTypeEnum()


class GovernanceAndManagementDetailsInput(graphene.InputObjectType):
    annual_general_body_meetings = graphene.Int()
    bod_meetings_last_financial_year = graphene.Int()
    minutes_maintenance = MinutesMaintenanceTypeEnum()
    num_bods = graphene.Int()
    num_women_bods = graphene.Int()


class CEOProfileSubmissionInput(graphene.InputObjectType):
    name = graphene.String()
    qualification = graphene.String()
    type_of_experience = ExperienceTypeEnum()
    other_experience_type = graphene.String()
    total_years_of_experience = graphene.Int()
    number_of_years_associated = graphene.Int()


class ChiefExecutiveOfficerProfileInput(graphene.InputObjectType):
    name = graphene.String()
    qualification = graphene.String()
    type_of_experience = ExperienceTypeEnum()
    total_years_of_experience = graphene.Int()


class BoardDirectorProfileInput(graphene.InputObjectType):
    name = graphene.String()
    educational_qualification = graphene.String()
    type_of_experience = BoardExperienceTypeEnum()
    other_experience = graphene.String()
    total_years_of_experience = graphene.Int()


class BoardOfDirectorsProfileInput(graphene.InputObjectType):
    name = graphene.String()
    educational_qualification = graphene.String()
    type_of_experience = BoardExperienceTypeEnum()
    total_years_of_experience = graphene.Int()


class BusinessOperationsSubmissionInput(graphene.InputObjectType):
    price_volatility_of_products = PriceVolatilityTypeEnum()
    accessibility_percentage = graphene.Decimal()
    availability_of_inputs_timeliness = InputTimelinessTypeEnum()
    availability_of_inputs_price_affordability = PriceAffordabilityTypeEnum()
    availability_of_inputs_place = DistanceAvailabilityTypeEnum()
    distance_of_output_collection_centres = graphene.String()
    electronic_weighing_machines = graphene.Boolean()
    transportation_facility = graphene.Boolean()
    storage = graphene.Boolean()
    cleaning = graphene.Boolean()
    grading_and_sorting = graphene.Boolean()
    chilling = graphene.Boolean()
    packaging = graphene.Boolean()
    labelling = graphene.Boolean()
    processing = graphene.Boolean()
    quality_check = graphene.Boolean()
    soil_testing_facility = graphene.Boolean()
    custom_hiring_centers = graphene.Boolean()
    contract_farming = graphene.Boolean()
    advisory_services = graphene.Boolean()
    credit_facilities = graphene.Boolean()


class BusinessAndOperationsInput(graphene.InputObjectType):
    price_volatility_of_products = PriceVolatilityTypeEnum()


class ComplianceDetailsSubmissionInput(graphene.InputObjectType):
    act_under_registered = ActRegisteredTypeEnum()
    date_of_registration = graphene.Date()
    place_of_registration = graphene.String()
    registration_no = graphene.String()
    incorporation_date = graphene.Date()
    incorporation_place = graphene.String()
    incorporation_reg_no = graphene.String()
    commencement_date = graphene.Date()
    commencement_place = graphene.String()
    commencement_reg_no = graphene.String()
    gst_date = graphene.Date()
    gst_place = graphene.String()
    gst_reg_no = graphene.String()
    permanent_account_number = graphene.String()
    tax_account_number = graphene.String()


class ComplianceDetailsInput(graphene.InputObjectType):
    act_under_registered = ActRegisteredTypeEnum()
    date_of_registration = graphene.Date()
    place_of_registration = graphene.String()
    registration_no = graphene.String()
    permanent_account_number = graphene.String()
    tax_deduction_account_number = graphene.String()


class ProcessesSystemsSubmissionInput(graphene.InputObjectType):
    accounts_and_mis = AccountsMISTypeEnum()
    insurance_of_stock = InsuranceStockTypeEnum()
    credit_record_of_fpo = CreditRecordTypeEnum()
    statutory_fillings = StatutoryFillingsTypeEnum()
    books_and_records_up_to_date = BooksRecordsTypeEnum()
    reconciliation_of_stocks = ReconciliationStocksTypeEnum()
    penalties_levied_board_meeting = graphene.Boolean()


class ProcessesAndSystemsInput(graphene.InputObjectType):
    accounts_and_mis = AccountsMISTypeEnum()
    insurance_of_stock = InsuranceStockTypeEnum()
    credit_record_of_fpo = CreditRecordTypeEnum()
    statutory_fillings = StatutoryFillingsTypeEnum()
    books_and_records_up_to_date = BooksRecordsTypeEnum()
    reconciliation_of_stocks = ReconciliationStocksTypeEnum()
    penalties_levied_board_meeting = graphene.Boolean()


class FacilitiesToFarmersInput(graphene.InputObjectType):
    availability_of_inputs_accessibility_percent = graphene.Decimal()
    availability_of_inputs_timeliness = InputTimelinessTypeEnum()
    availability_of_inputs_price_affordability = PriceAffordabilityTypeEnum()
    availability_of_inputs_place = DistanceAvailabilityTypeEnum()
    distance_of_output_collection_centres = graphene.String()
    electronic_weighing_machines = graphene.Boolean()
    transportation_facility = graphene.Boolean()
    storage = graphene.Boolean()
    cleaning = graphene.Boolean()
    grading_and_sorting = graphene.Boolean()
    chilling = graphene.Boolean()
    packaging = graphene.Boolean()
    labelling = graphene.Boolean()
    processing = graphene.Boolean()
    quality_check = graphene.Boolean()
    soil_testing_facility = graphene.Boolean()
    custom_hiring_centers = graphene.Boolean()
    contract_farming = graphene.Boolean()
    advisory_services = graphene.Boolean()
    credit_facilities = graphene.Boolean()


class SustainableActivitiesSubmissionInput(graphene.InputObjectType):
    climate_resilient_seeds_to_farmers = graphene.Boolean()
    organic_bio_manure_fertilizers_to_farmers = graphene.Boolean()
    composting_units_at_fpo_level = graphene.Boolean()
    drip_sprinkler_irrigation_to_farmers = graphene.Boolean()
    pest_disease_alerts_to_farmers = graphene.Boolean()
    weather_advisories_to_farmers = graphene.Boolean()
    supplying_agricultural_residue_to_bio_cng_gas_plants = graphene.Boolean()
    training_on_organic_farming_to_farmers = graphene.Boolean()
    solar_panels_at_fpo_level = graphene.Boolean()
    establishment_of_rainwater_harvesting_at_fpo_level = graphene.Boolean()


class SustainableActivitiesInput(graphene.InputObjectType):
    climate_resilient_seeds_to_farmers = graphene.Boolean()
    organic_bio_manure_fertilizers_to_farmers = graphene.Boolean()
    composting_units_at_fpo_level = graphene.Boolean()
    drip_sprinkler_irrigation_to_farmers = graphene.Boolean()
    pest_disease_alerts_to_farmers = graphene.Boolean()
    weather_advisories_to_farmers = graphene.Boolean()
    supplying_agricultural_residue_to_bio_cng_gas_plants = graphene.Boolean()
    training_on_organic_farming_to_farmers = graphene.Boolean()
    solar_panels_at_fpo_level = graphene.Boolean()
    establishment_of_rainwater_harvesting_at_fpo_level = graphene.Boolean()


class FinancialDetailsSubmissionV2Input(graphene.InputObjectType):
    # Revenue details for last 3 financial years
    current_year_revenue = graphene.Decimal()
    previous_year_revenue = graphene.Decimal()
    two_years_back_revenue = graphene.Decimal()

    # Product names for revenue
    current_year_products = graphene.String()
    previous_year_products = graphene.String()
    two_years_back_products = graphene.String()

    # Target revenue
    target_revenue = graphene.Decimal()

    # Quantity procured (Metric tonnes)
    current_year_quantity_procured = graphene.Decimal()
    current_year_quantity_products = graphene.String()
    previous_year_quantity_procured = graphene.Decimal()
    previous_year_quantity_products = graphene.String()
    two_years_back_quantity_procured = graphene.Decimal()
    two_years_back_quantity_products = graphene.String()

    # Retail buying details
    current_year_retail_revenue = graphene.Decimal()
    current_year_retail_products = graphene.String()
    previous_year_retail_revenue = graphene.Decimal()
    previous_year_retail_products = graphene.String()
    two_years_back_retail_revenue = graphene.Decimal()
    two_years_back_retail_products = graphene.String()

    # Wholesale buying details
    current_year_wholesale_revenue = graphene.Decimal()
    current_year_wholesale_products = graphene.String()
    previous_year_wholesale_revenue = graphene.Decimal()
    previous_year_wholesale_products = graphene.String()
    two_years_back_wholesale_revenue = graphene.Decimal()
    two_years_back_wholesale_products = graphene.String()

    # Institutional buying details
    current_year_institutional_revenue = graphene.Decimal()
    current_year_institutional_products = graphene.String()
    previous_year_institutional_revenue = graphene.Decimal()
    previous_year_institutional_products = graphene.String()
    two_years_back_institutional_revenue = graphene.Decimal()
    two_years_back_institutional_products = graphene.String()

    # Cost of Goods Sold
    current_year_cogs = graphene.Decimal()
    previous_year_cogs = graphene.Decimal()
    two_years_back_cogs = graphene.Decimal()

    # Profit details
    current_year_gross_profit = graphene.Decimal()
    current_year_net_profit = graphene.Decimal()
    previous_year_gross_profit = graphene.Decimal()
    previous_year_net_profit = graphene.Decimal()
    two_years_back_gross_profit = graphene.Decimal()
    two_years_back_net_profit = graphene.Decimal()

    # Operating and margin details
    operating_margin_current_year = graphene.Decimal()
    gross_net_profit_margin_difference = graphene.Decimal()

    # Share capital and shareholders
    current_year_share_capital = graphene.Decimal()
    current_year_shareholders = graphene.Int()
    previous_year_share_capital = graphene.Decimal()
    previous_year_shareholders = graphene.Int()
    two_years_back_share_capital = graphene.Decimal()
    two_years_back_shareholders = graphene.Int()

    # Accounts Payable/Receivable
    current_year_accounts_payable = graphene.Decimal()
    current_year_accounts_receivable = graphene.Decimal()
    previous_year_accounts_payable = graphene.Decimal()
    previous_year_accounts_receivable = graphene.Decimal()
    two_years_back_accounts_payable = graphene.Decimal()
    two_years_back_accounts_receivable = graphene.Decimal()

    # Inventory details
    current_year_opening_inventory = graphene.Decimal()
    current_year_closing_inventory = graphene.Decimal()
    previous_year_opening_inventory = graphene.Decimal()
    previous_year_closing_inventory = graphene.Decimal()
    two_years_back_opening_inventory = graphene.Decimal()
    two_years_back_closing_inventory = graphene.Decimal()

    # Grant details
    current_year_project_grant = graphene.Decimal()
    current_year_matching_grant = graphene.Decimal()
    previous_year_project_grant = graphene.Decimal()
    previous_year_matching_grant = graphene.Decimal()
    two_years_back_project_grant = graphene.Decimal()
    two_years_back_matching_grant = graphene.Decimal()

    # Net Worth details
    current_year_assets = graphene.Decimal()
    current_year_liabilities = graphene.Decimal()
    previous_year_assets = graphene.Decimal()
    previous_year_liabilities = graphene.Decimal()
    two_years_back_assets = graphene.Decimal()
    two_years_back_liabilities = graphene.Decimal()

    # Current ratio details
    current_year_current_assets = graphene.Decimal()
    current_year_current_liabilities = graphene.Decimal()
    previous_year_current_assets = graphene.Decimal()
    previous_year_current_liabilities = graphene.Decimal()
    two_years_back_current_assets = graphene.Decimal()
    two_years_back_current_liabilities = graphene.Decimal()

    # Credit history
    current_year_lender_name = graphene.String()
    current_year_loan_amount = graphene.Decimal()
    previous_year_lender_name = graphene.String()
    previous_year_loan_amount = graphene.Decimal()
    two_years_back_lender_name = graphene.String()
    two_years_back_loan_amount = graphene.Decimal()

    # Additional financial metrics
    cash_cheque_percentage = graphene.Decimal()
    days_payable_receivable_difference = graphene.Int()
    total_debt_today = graphene.Decimal()

    # History fields
    institutional_lending_history = graphene.String()
    credit_default_year = graphene.String()
    credit_default_lender = graphene.String()
    credit_default_amount = graphene.Decimal()

    loan_details = graphene.JSONString()


# Helper function to get or create yearly submission
def get_or_create_yearly_submission(user, financial_year, fpo_id):
    """Return an editable submission for an active FPO member.

    Profile verification deliberately does not participate in this access
    check. Pending and rejected FPOs must be able to fill
    every assessment section and receive their private score immediately;
    verification only controls public visibility and admin aggregation.
    """
    # fpo_id is now required, so we always have it
    try:
        # Convert from global ID to database ID if needed
        if isinstance(fpo_id, str):
            from graphql_relay import from_global_id

            try:
                # Try to decode as Relay global ID
                node_type, fpo_db_id = from_global_id(fpo_id)
                fpo = FPO.objects.get(id=fpo_db_id)
            except:
                # If decoding fails, try to use as direct ID
                fpo = FPO.objects.get(id=fpo_id)
        else:
            # Use as direct numeric ID
            fpo = FPO.objects.get(id=fpo_id)

        # Verify user has access to this FPO
        if not FPOMember.objects.filter(user=user, fpo=fpo, is_active=True).exists():
            raise Exception("User is not associated with this FPO")
    except FPO.DoesNotExist:
        raise Exception("FPO not found")

    # Get or create the yearly submission
    submission, created = YearlySubmission.objects.get_or_create(
        fpo=fpo, financial_year=financial_year, defaults={"submitted_by": user}
    )

    return submission


class FPOReportDataType(graphene.ObjectType):
    total_score = graphene.Float()
    section_scores = graphene.types.generic.GenericScalar()
    indicators = graphene.types.generic.GenericScalar()
    fpo_details = graphene.types.generic.GenericScalar()
    submission_id = graphene.ID()
    fpo_name = graphene.String()
    location = graphene.String()
    size = graphene.String()
    category = graphene.String()
    crops = graphene.String()
    quantity_procured = graphene.Float()
    active_membership_pct = graphene.Float()


class PublicFPOCardType(graphene.ObjectType):
    id = graphene.String()
    pk = graphene.Int()
    score = graphene.Float()
    title = graphene.String()
    city = graphene.String()
    district = graphene.String()
    state = graphene.String()
    description = graphene.String()
    members = graphene.Int()
    email = graphene.String()
    phone = graphene.String()


class PublicFPOListingType(graphene.ObjectType):
    fpos = graphene.List(PublicFPOCardType)
    total = graphene.Int()
    page = graphene.Int()
    limit = graphene.Int()
    total_pages = graphene.Int()


class Query(graphene.ObjectType):
    # FPO queries
    fpo = relay.Node.Field(FPONode)
    all_fpos = DjangoFilterConnectionField(FPONode)
    my_fpo = graphene.Field(FPONode)

    # Submission queries
    yearly_submission = relay.Node.Field(YearlySubmissionNode)
    my_submissions = DjangoFilterConnectionField(YearlySubmissionNode)
    get_submission = graphene.Field(
        YearlySubmissionNode, financial_year=graphene.String(required=True), fpo_id=graphene.ID(required=True)
    )
    financial_details_submission_v2 = relay.Node.Field(FinancialDetailsSubmissionV2Node)
    all_financial_details_v2 = DjangoFilterConnectionField(
        FinancialDetailsSubmissionV2Node, filterset_class=FinancialDetailsSubmissionV2FilterSet
    )
    all_my_fpos = DjangoFilterConnectionField(FPONode)

    get_fpo_report_data = graphene.Field(FPOReportDataType, submission_id=graphene.ID(required=True))

    public_fpo_listing = graphene.Field(
        PublicFPOListingType,
        page=graphene.Int(default_value=1),
        limit=graphene.Int(default_value=12),
        search=graphene.String(required=False),
        state=graphene.String(required=False),
        district=graphene.String(required=False),
        category=graphene.String(required=False),
        description="Public paginated FPO listing for the weai-original frontend.",
    )

    def resolve_public_fpo_listing(self, info, page=1, limit=12,
                                   search=None, state=None, district=None, category=None):
        from django.db.models import OuterRef, Subquery, FloatField, IntegerField, Q, Count, Value
        from django.db.models.functions import Coalesce
        import math

        page = max(1, page)
        limit = max(1, min(100, limit))

        latest_sub = YearlySubmission.objects.reportable().filter(
            fpo=OuterRef('pk'),
            calculated_score__isnull=False,
        ).order_by('-financial_year')

        latest_details = FPODetailsSubmission.objects.filter(
            yearly_submission_id=Subquery(latest_sub.values('pk')[:1])
        )

        size_expr = Coalesce(
            Subquery(latest_details.values('size_of_fpo_fy_23_24')[:1], output_field=IntegerField()),
            Subquery(latest_details.values('size_of_fpo_fy_22_23')[:1], output_field=IntegerField()),
            Subquery(latest_details.values('size_of_fpo_fy_21_22')[:1], output_field=IntegerField()),
            Value(0),
        )

        fpos = FPO.objects.publicly_visible().annotate(
            score=Coalesce(
                Subquery(latest_sub.values('calculated_score')[:1], output_field=FloatField()),
                0.0,
            ),
            fpo_size=size_expr,
            member_count=Count('members', filter=Q(members__is_active=True), distinct=True),
        )

        if state:
            fpos = fpos.filter(state__iexact=state)
        if district:
            fpos = fpos.filter(district__iexact=district)
        if search:
            fpos = fpos.filter(name__icontains=search.strip())

        if category == 'Achiever':
            fpos = fpos.filter(score__gte=70)
        elif category == 'Performer':
            fpos = fpos.filter(score__gte=50, score__lt=70)
        elif category == 'Aspirational':
            fpos = fpos.filter(score__gt=0, score__lt=50)
        elif category == 'N/A':
            fpos = fpos.filter(score=0.0)

        fpos = fpos.order_by('-score', 'name')

        total = fpos.count()
        rows = list(
            fpos[(page - 1) * limit : page * limit].values(
                'pk', 'name', 'city', 'district', 'state',
                'email', 'phone', 'score', 'fpo_size', 'member_count',
            )
        )

        cards = []
        for r in rows:
            slug = r['name'].lower().replace(' ', '-').replace('.', '').replace(',', '')[:60]
            if r['fpo_size']:
                description = (
                    f"{r['name']} in {r['state']} empowers smallholder farmers by "
                    f"promoting collective farming with {r['fpo_size']} members."
                )
            else:
                description = (
                    f"{r['name']} in {r['state']} empowers smallholder farmers by "
                    "promoting collective farming of various crops, boosting yields and "
                    "profitability through better market access and sustainable practices."
                )
            cards.append(PublicFPOCardType(
                id=slug, pk=r['pk'], score=round(r['score'], 1),
                title=r['name'], city=r['city'], district=r['district'],
                state=r['state'], description=description,
                members=r['fpo_size'] or r['member_count'],
                email=r['email'], phone=r['phone'],
            ))

        return PublicFPOListingType(
            fpos=cards, total=total, page=page, limit=limit,
            total_pages=math.ceil(total / limit) if limit else 0,
        )

    @login_required
    def resolve_get_fpo_report_data(self, info, submission_id):
        """GraphQL equivalent of Django view get_fpo_report_data"""
        try:
            # Convert ID from global to database ID if needed
            if isinstance(submission_id, str) and submission_id.isdigit():
                submission_id = int(float(submission_id))
            else:
                submission_id = int(submission_id)

            submission = YearlySubmission.objects.get(id=submission_id)
            user = info.context.user
            can_view = (
                user.is_staff
                or user.is_superuser
                or FPOMember.objects.filter(
                    user=user,
                    fpo=submission.fpo,
                    is_active=True,
                ).exists()
            )
            if not can_view:
                return None
            calculator = FPOScoreCalculator(submission)

            total_score = float(calculator.calculate_total_score())
            section_scores = calculator.get_section_scores()
            indicators = calculator.get_detailed_indicators()
            category = calculator.get_performance_category_stored()
            active_membership_pct = calculator.get_active_membership_percentage()

            # Get FPO details
            fpo_details = {
                "name": (
                    submission.fpo_details.name_of_producer_organization
                    if hasattr(submission, "fpo_details")
                    else submission.fpo.name_of_producer_organization
                ),
                "location": submission.fpo_details.registered_address if hasattr(submission, "fpo_details") else "",
                "size": submission.fpo_details.size_of_fpo_fy_23_24 if hasattr(submission, "fpo_details") else "",
                "quantity_procured": (
                    submission.financial_details_v2.current_year_quantity_procured
                    if hasattr(submission, "financial_details_v2")
                    else None
                ),
                "crops": (
                    submission.financial_details_v2.current_year_institutional_products
                    if hasattr(submission, "financial_details_v2")
                    else None
                ),
            }

            return FPOReportDataType(
                total_score=total_score,
                section_scores=section_scores,
                indicators=indicators,
                fpo_details=fpo_details,
                submission_id=submission_id,
                fpo_name=submission.fpo.name,
                location=fpo_details["location"],
                size=fpo_details["size"],
                category=category,
                quantity_procured=fpo_details["quantity_procured"],
                crops=fpo_details["crops"],
                active_membership_pct=active_membership_pct,
            )

        except YearlySubmission.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error in getFPOReportData: {str(e)}")
            return None

    @login_required
    def resolve_my_fpo(self, info):
        user = info.context.user
        try:
            fpo_member = FPOMember.objects.get(user=user, is_active=True)
            return fpo_member.fpo
        except FPOMember.DoesNotExist:
            return None

    @login_required
    def resolve_all_my_fpos(self, info, **kwargs):
        user = info.context.user
        # Return FPOs through the FPOMember relationship as a queryset
        return FPO.objects.filter(members__user=user, members__is_active=True)

    @login_required
    def resolve_my_submissions(self, info, **kwargs):
        user = info.context.user
        try:
            fpo_member = FPOMember.objects.get(user=user, is_active=True)
            fpo = fpo_member.fpo
            return YearlySubmission.objects.filter(fpo=fpo).order_by("-financial_year", "-updated_at")
        except FPOMember.DoesNotExist:
            return YearlySubmission.objects.none()

    @login_required
    def resolve_get_submission(self, info, financial_year, fpo_id):
        user = info.context.user
        try:
            # fpo_id is now required, so we always have it
            # Convert from global ID to database ID if needed
            if isinstance(fpo_id, str):
                from graphql_relay import from_global_id

                try:
                    # Try to decode as Relay global ID
                    node_type, fpo_db_id = from_global_id(fpo_id)
                    fpo = FPO.objects.get(id=fpo_db_id)
                except:
                    # If decoding fails, try to use as direct ID
                    fpo = FPO.objects.get(id=fpo_id)
            else:
                # Use as direct numeric ID
                fpo = FPO.objects.get(id=fpo_id)

            # Verify user has access to this FPO
            if not FPOMember.objects.filter(user=user, fpo=fpo, is_active=True).exists():
                return None

            # Get the latest submission for the given financial year
            return (
                YearlySubmission.objects.filter(fpo=fpo, financial_year=financial_year).order_by("-updated_at").first()
            )
        except (FPOMember.DoesNotExist, FPO.DoesNotExist):
            return None


# FPO Creation Mutation
class CreateFPOMutation(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        email = graphene.String(required=True)
        phone = graphene.String(required=True)
        alternate_phone = graphene.String()
        address_line_1 = graphene.String(required=True)
        address_line_2 = graphene.String()
        city = graphene.String(required=True)
        district = graphene.String(required=True)
        state = graphene.String(required=True)
        pincode = graphene.String(required=True)
        logo = graphene.String()  # Base64 encoded image or URL

    success = graphene.Boolean()
    fpo = graphene.Field(FPONode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(
        self,
        info,
        name,
        email,
        phone,
        address_line_1,
        city,
        district,
        state,
        pincode,
        alternate_phone=None,
        address_line_2=None,
        logo=None,
    ):
        user = info.context.user
        errors = []

        try:
            # Check if FPO with same name already exists
            if FPO.objects.filter(name=name).exists():
                errors.append(f"FPO with name '{name}' already exists")
                return CreateFPOMutation(success=False, errors=errors)

            # Create the FPO
            fpo = FPO.objects.create(
                name=name,
                email=email,
                phone=phone,
                alternate_phone=alternate_phone or "",
                address_line_1=address_line_1,
                address_line_2=address_line_2 or "",
                city=city,
                district=district,
                state=state,
                pincode=pincode,
                created_by=user,
                is_active=True,
                verification_status=FPOVerificationStatus.PENDING,
            )

            # Handle logo if provided (you may need to implement base64 image handling)
            if logo:
                # TODO: Implement logo upload handling
                pass

            # Add the creator as an admin member of the FPO
            FPOMember.objects.create(fpo=fpo, user=user, role="admin", is_active=True)

            return CreateFPOMutation(success=True, fpo=fpo, errors=[])

        except Exception as e:
            errors.append(str(e))
            if "fpo" in locals():
                fpo.delete()  # Rollback if FPO was created
            return CreateFPOMutation(success=False, errors=errors)


# FPO Details CRUD Mutations
class CreateFPODetailsSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(FPODetailsSubmissionInput, required=True)
        fpo_id = graphene.ID(required=False)

    success = graphene.Boolean()
    submission = graphene.Field(FPODetailsSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            # Create or update FPO details submission
            fpo_details, created = FPODetailsSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "name_of_producer_organization": input.get("name_of_producer_organization", ""),
                    "registered_address": input.get("registered_address", ""),
                    "district": input.get("district", ""),
                    "state": input.get("state", ""),
                    "type_of_producer_organization": _get_enum_value(input.get("type_of_producer_organization")),
                    "date_of_incorporation": input.get("date_of_incorporation"),
                    "date_of_commencement": input.get("date_of_commencement"),
                    "age_of_fpo_years": input.get("age_of_fpo_years"),
                    "type_of_fpo": _get_enum_value(input.get("type_of_fpo")),
                    "size_of_fpo_fy_23_24": input.get("size_of_fpo_fy_23_24"),
                    "size_of_fpo_fy_22_23": input.get("size_of_fpo_fy_22_23"),
                    "size_of_fpo_fy_21_22": input.get("size_of_fpo_fy_21_22"),
                    "farmers_transacted": input.get("farmers_transacted"),
                    "women_members": input.get("women_members"),
                    "target_size_of_fpo": input.get("target_size_of_fpo"),
                    "deals_through_pgs_figs": input.get("deals_through_pgs_figs"),
                    "num_pgs_figs": input.get("num_pgs_figs"),
                    "supported_by_promoting_agency": input.get("supported_by_promoting_agency"),
                    "promoting_agency_name": input.get("promoting_agency_name", ""),
                    "type_of_promoting_agency": _get_enum_value(input.get("type_of_promoting_agency")),
                    "other_promoting_agency_type": input.get("other_promoting_agency_type", ""),
                    "received_grants": input.get("received_grants"),
                    "grant_making_organization": input.get("grant_making_organization", ""),
                },
            )

            return CreateFPODetailsSubmissionMutation(success=True, submission=fpo_details, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateFPODetailsSubmissionMutation(success=False, errors=errors)


class CreateGovernanceSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(GovernanceSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(GovernanceSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            governance, created = GovernanceSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "annual_general_body_meetings": input.get("annual_general_body_meetings", 0),
                    "bod_meetings_last_financial_year": input.get("bod_meetings_last_financial_year", 0),
                    "minutes_maintenance": _get_enum_value(input.get("minutes_maintenance")),
                    "num_bods": input.get("num_bods", 0),
                    "num_women_bods": input.get("num_women_bods", 0),
                    "second_line_management": _get_enum_value(input.get("second_line_management")),
                },
            )

            return CreateGovernanceSubmissionMutation(success=True, submission=governance, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateGovernanceSubmissionMutation(success=False, errors=errors)


class CreateCEOProfileSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(CEOProfileSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(CEOProfileSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            ceo_profile, created = CEOProfileSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "name": input.get("name", ""),
                    "qualification": input.get("qualification", ""),
                    "type_of_experience": _get_enum_value(input.get("type_of_experience")),
                    "other_experience_type": input.get("other_experience_type", ""),
                    "total_years_of_experience": input.get("total_years_of_experience", 0),
                    "number_of_years_associated": input.get("number_of_years_associated", 0),
                },
            )

            return CreateCEOProfileSubmissionMutation(success=True, submission=ceo_profile, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateCEOProfileSubmissionMutation(success=False, errors=errors)


class CreateBoardDirectorProfileMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        directors = graphene.List(BoardDirectorProfileInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    directors = graphene.List(BoardDirectorProfileNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, directors, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            # Delete existing directors for this submission
            BoardDirectorProfile.objects.filter(yearly_submission=yearly_submission).delete()

            created_directors = []
            for director_input in directors:
                director = BoardDirectorProfile.objects.create(
                    yearly_submission=yearly_submission,
                    name=director_input.get("name", ""),
                    educational_qualification=director_input.get("educational_qualification", ""),
                    type_of_experience=_get_enum_value(director_input.get("type_of_experience")),
                    other_experience=director_input.get("other_experience", ""),
                    total_years_of_experience=director_input.get("total_years_of_experience", 0),
                )
                created_directors.append(director)

            return CreateBoardDirectorProfileMutation(success=True, directors=created_directors, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateBoardDirectorProfileMutation(success=False, errors=errors)


class CreateBusinessOperationsSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(BusinessOperationsSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(BusinessOperationsSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            business_ops, created = BusinessOperationsSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "price_volatility_of_products": _get_enum_value(input.get("price_volatility_of_products")),
                    "accessibility_percentage": input.get("accessibility_percentage"),
                    "availability_of_inputs_timeliness": _get_enum_value(
                        input.get("availability_of_inputs_timeliness")
                    ),
                    "availability_of_inputs_price_affordability": _get_enum_value(
                        input.get("availability_of_inputs_price_affordability")
                    ),
                    "availability_of_inputs_place": _get_enum_value(input.get("availability_of_inputs_place")),
                    "distance_of_output_collection_centres": input.get("distance_of_output_collection_centres", ""),
                    "electronic_weighing_machines": input.get("electronic_weighing_machines"),
                    "transportation_facility": input.get("transportation_facility"),
                    "storage": input.get("storage"),
                    "cleaning": input.get("cleaning"),
                    "grading_and_sorting": input.get("grading_and_sorting"),
                    "chilling": input.get("chilling"),
                    "packaging": input.get("packaging"),
                    "labelling": input.get("labelling"),
                    "processing": input.get("processing"),
                    "quality_check": input.get("quality_check"),
                    "soil_testing_facility": input.get("soil_testing_facility"),
                    "custom_hiring_centers": input.get("custom_hiring_centers"),
                    "contract_farming": input.get("contract_farming"),
                    "advisory_services": input.get("advisory_services"),
                    "credit_facilities": input.get("credit_facilities"),
                },
            )

            return CreateBusinessOperationsSubmissionMutation(success=True, submission=business_ops, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateBusinessOperationsSubmissionMutation(success=False, errors=errors)


class CreateComplianceDetailsSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(ComplianceDetailsSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(ComplianceDetailsSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            compliance, created = ComplianceDetailsSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "act_under_registered": _get_enum_value(input.get("act_under_registered")),
                    "date_of_registration": input.get("date_of_registration"),
                    "place_of_registration": input.get("place_of_registration", ""),
                    "registration_no": input.get("registration_no", ""),
                    "incorporation_date": input.get("incorporation_date"),
                    "incorporation_place": input.get("incorporation_place", ""),
                    "incorporation_reg_no": input.get("incorporation_reg_no", ""),
                    "commencement_date": input.get("commencement_date"),
                    "commencement_place": input.get("commencement_place", ""),
                    "commencement_reg_no": input.get("commencement_reg_no", ""),
                    "gst_date": input.get("gst_date"),
                    "gst_place": input.get("gst_place", ""),
                    "gst_reg_no": input.get("gst_reg_no", ""),
                    "permanent_account_number": input.get("permanent_account_number", ""),
                    "tax_account_number": input.get("tax_account_number", ""),
                },
            )

            return CreateComplianceDetailsSubmissionMutation(success=True, submission=compliance, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateComplianceDetailsSubmissionMutation(success=False, errors=errors)


class CreateProcessesSystemsSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(ProcessesSystemsSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(ProcessesSystemsSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            processes, created = ProcessesSystemsSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "accounts_and_mis": _get_enum_value(input.get("accounts_and_mis")),
                    "insurance_of_stock": _get_enum_value(input.get("insurance_of_stock")),
                    "credit_record_of_fpo": _get_enum_value(input.get("credit_record_of_fpo")),
                    "statutory_fillings": _get_enum_value(input.get("statutory_fillings")),
                    "books_and_records_up_to_date": _get_enum_value(input.get("books_and_records_up_to_date")),
                    "reconciliation_of_stocks": _get_enum_value(input.get("reconciliation_of_stocks")),
                    "penalties_levied_board_meeting": input.get("penalties_levied_board_meeting", False),
                },
            )

            return CreateProcessesSystemsSubmissionMutation(success=True, submission=processes, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateProcessesSystemsSubmissionMutation(success=False, errors=errors)


class CreateFinancialDetailsSubmissionV2Mutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(FinancialDetailsSubmissionV2Input, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(FinancialDetailsSubmissionV2Node)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            sanitized_defaults = _prepare_financial_defaults(input)

            existing_id = (
                FinancialDetailsSubmissionV2.objects.filter(yearly_submission=yearly_submission)
                .values_list("id", flat=True)
                .first()
            )

            if existing_id:
                FinancialDetailsSubmissionV2.objects.filter(id=existing_id).update(**sanitized_defaults)
                try:
                    financial = FinancialDetailsSubmissionV2.objects.get(id=existing_id)
                except InvalidOperation:
                    financial = _build_safe_financial_details(yearly_submission)
            else:
                financial = FinancialDetailsSubmissionV2.objects.create(
                    yearly_submission=yearly_submission,
                    **sanitized_defaults,
                )

            return CreateFinancialDetailsSubmissionV2Mutation(success=True, submission=financial, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateFinancialDetailsSubmissionV2Mutation(success=False, errors=errors)


class CreateSustainableActivitiesSubmissionMutation(graphene.Mutation):
    class Arguments:
        financial_year = graphene.String(required=True)
        input = graphene.Argument(SustainableActivitiesSubmissionInput, required=True)
        fpo_id = graphene.ID(required=True)

    success = graphene.Boolean()
    submission = graphene.Field(SustainableActivitiesSubmissionNode)
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, financial_year, input, fpo_id):
        user = info.context.user
        errors = []

        try:
            yearly_submission = get_or_create_yearly_submission(user, financial_year, fpo_id)

            sustainable, created = SustainableActivitiesSubmission.objects.update_or_create(
                yearly_submission=yearly_submission,
                defaults={
                    "climate_resilient_seeds_to_farmers": input.get("climate_resilient_seeds_to_farmers", False),
                    "organic_bio_manure_fertilizers_to_farmers": input.get(
                        "organic_bio_manure_fertilizers_to_farmers", False
                    ),
                    "composting_units_at_fpo_level": input.get("composting_units_at_fpo_level", False),
                    "drip_sprinkler_irrigation_to_farmers": input.get("drip_sprinkler_irrigation_to_farmers", False),
                    "pest_disease_alerts_to_farmers": input.get("pest_disease_alerts_to_farmers", False),
                    "weather_advisories_to_farmers": input.get("weather_advisories_to_farmers", False),
                    "supplying_agricultural_residue_to_bio_cng_gas_plants": input.get(
                        "supplying_agricultural_residue_to_bio_cng_gas_plants", False
                    ),
                    "training_on_organic_farming_to_farmers": input.get(
                        "training_on_organic_farming_to_farmers", False
                    ),
                    "solar_panels_at_fpo_level": input.get("solar_panels_at_fpo_level", False),
                    "establishment_of_rainwater_harvesting_at_fpo_level": input.get(
                        "establishment_of_rainwater_harvesting_at_fpo_level", False
                    ),
                },
            )

            return CreateSustainableActivitiesSubmissionMutation(success=True, submission=sustainable, errors=[])

        except Exception as e:
            errors.append(str(e))
            return CreateSustainableActivitiesSubmissionMutation(success=False, errors=errors)


class Mutation(graphene.ObjectType):
    # FPO Management
    create_fpo = CreateFPOMutation.Field()

    # Submission Management
    create_fpo_details_submission = CreateFPODetailsSubmissionMutation.Field()
    create_governance_submission = CreateGovernanceSubmissionMutation.Field()
    create_ceo_profile_submission = CreateCEOProfileSubmissionMutation.Field()
    create_board_director_profiles = CreateBoardDirectorProfileMutation.Field()
    create_business_operations_submission = CreateBusinessOperationsSubmissionMutation.Field()
    create_compliance_details_submission = CreateComplianceDetailsSubmissionMutation.Field()
    create_processes_systems_submission = CreateProcessesSystemsSubmissionMutation.Field()
    create_financial_details_submission_v2 = CreateFinancialDetailsSubmissionV2Mutation.Field()
    create_sustainable_activities_submission = CreateSustainableActivitiesSubmissionMutation.Field()

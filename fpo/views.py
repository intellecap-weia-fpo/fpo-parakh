from . import report_access
from .store.document_access import document_access
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch, F
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.template.loader import render_to_string

# from weasyprint import HTML,CSS  # Temporarily disabled for development
from django.http import HttpResponse
from collections import defaultdict
import csv
import math
from datetime import datetime

# Lazy import WeasyPrint only when needed for PDF generation
# from weasyprint import CSS, HTML

from fpo.score_calculator_v2 import FPOScoreCalculator
from .models import (
    AccountsMISType,
    BoardExperienceType,
    BooksRecordsType,
    CreditRecordType,
    DistanceAvailabilityType,
    ExperienceType,
    FPO,
    FPOVerificationStatus,
    FPOType,
    FPOMember,
    InputTimelinessType,
    InsuranceStockType,
    InstitutionalLendingHistoryType,
    MinutesMaintenanceType,
    PriceAffordabilityType,
    PriceVolatilityType,
    PromotingAgencyType,
    ReconciliationStocksType,
    SecondLineManagementType,
    StatutoryFillingsType,
    YearlySubmission,
)


# Try to import optional models that might not exist
try:
    from .models import FPODetailsSubmission
except ImportError:
    FPODetailsSubmission = None

try:
    from .models import (
        GovernanceSubmission,
        CEOProfileSubmission,
        BoardDirectorProfile,
        BusinessOperationsSubmission,
        ComplianceDetailsSubmission,
        ProcessesSystemsSubmission,
        SustainableActivitiesSubmission,
        FinancialDetailsSubmissionV2,
    )
except ImportError:
    GovernanceSubmission = None
    CEOProfileSubmission = None
    BoardDirectorProfile = None
    BusinessOperationsSubmission = None
    ComplianceDetailsSubmission = None
    ProcessesSystemsSubmission = None
    SustainableActivitiesSubmission = None
    FinancialDetailsSubmissionV2 = None
from .ai_processor import FPODocumentProcessor


def _require_fpo_verifier(request):
    """Restrict verification decisions to trusted admin users."""
    user = request.user
    can_verify = (
        user.is_superuser
        or user.is_staff
        or user.has_perm("fpo.verify_fpo")
        or user.groups.filter(name="admin").exists()
    )
    if not can_verify:
        raise PermissionDenied("You do not have permission to review FPO registrations.")


def _require_user_admin(request):
    """Only platform admins may list, create or delete user accounts."""
    user = request.user
    if not (user.is_superuser or user.is_staff or user.groups.filter(name="admin").exists()):
        raise PermissionDenied("You do not have permission to manage users.")


def _require_fpo_view(request, fpo):
    if not report_access.can_view_fpo(request.user, fpo):
        raise PermissionDenied("You do not have permission to view this FPO.")


def _require_fpo_admin(request, fpo):
    if not report_access.can_manage_fpo(request.user, fpo):
        raise PermissionDenied("You do not have permission to manage this FPO.")


@login_required
def dashboard(request):
    """
    Main dashboard showing overview statistics and recent activity
    """
    from django.db.models import Count, Avg, Q
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Get total counts
    total_fpos = FPO.objects.publicly_visible().count()
    total_submissions = YearlySubmission.objects.reportable().count()
    total_users = User.objects.filter(is_active=True).count()

    # Get unique states and districts count
    states_count = FPO.objects.publicly_visible().values('state').distinct().count()
    districts_count = FPO.objects.publicly_visible().values('district').distinct().count()

    # Get average score from submissions
    avg_score = YearlySubmission.objects.reportable().filter(
        calculated_score__isnull=False
    ).aggregate(Avg('calculated_score'))['calculated_score__avg'] or 0

    # Get top FPOs by score (last 10 with highest scores)
    top_fpos = YearlySubmission.objects.reportable().select_related(
        'fpo'
    ).filter(
        calculated_score__isnull=False
    ).order_by('-calculated_score', '-created_at')[:10]

    # Get recent users (last 10 created)
    recent_users = User.objects.filter(is_active=True).prefetch_related(
        'fpomember_set__fpo'
    ).order_by('-date_joined')[:10]

    # Get score categories count
    achievers_count = YearlySubmission.objects.reportable().filter(calculated_score__gte=70).count()
    performers_count = YearlySubmission.objects.reportable().filter(
        calculated_score__gte=50, calculated_score__lt=70
    ).count()
    aspirational_count = YearlySubmission.objects.reportable().filter(
        calculated_score__lt=50, calculated_score__isnull=False
    ).count()

    context = {
        'page_title': 'Dashboard',
        'use_fpo_sidebar': True,
        'total_fpos': total_fpos,
        'total_submissions': total_submissions,
        'total_users': total_users,
        'states_count': states_count,
        'districts_count': districts_count,
        'avg_score': round(avg_score, 2),
        'top_fpos': top_fpos,
        'recent_users': recent_users,
        'achievers_count': achievers_count,
        'performers_count': performers_count,
        'aspirational_count': aspirational_count,
    }

    return render(request, 'fpo/dashboard.html', context)


@login_required
def fpos_list(request):
    search_query = request.GET.get("search", "")
    status_filter = request.GET.get("status", "")
    state_filter = request.GET.get("state", "")

    all_fpos = FPO.objects.all()
    total_fpos = all_fpos.count()
    total_states = all_fpos.exclude(state="").values("state").distinct().count()
    total_districts = all_fpos.exclude(district="").values("state", "district").distinct().count()
    all_states = list(
        all_fpos.exclude(state="").order_by("state").values_list("state", flat=True).distinct()
    )

    # Get all FPOs with prefetched admin members
    fpos = FPO.objects.all().prefetch_related(
        Prefetch(
            "members",
            queryset=FPOMember.objects.filter(role="admin", is_active=True).select_related("user"),
            to_attr="admin_members_cache",
        )
    )

    # Apply search filter
    if search_query:
        fpos = fpos.filter(
            Q(name__icontains=search_query)
            | Q(city__icontains=search_query)
            | Q(state__icontains=search_query)
            | Q(district__icontains=search_query)
            # Search by admin member (contact person) name/username
            | Q(
                members__role="admin",
                members__is_active=True,
                members__user__first_name__icontains=search_query,
            )
            | Q(
                members__role="admin",
                members__is_active=True,
                members__user__last_name__icontains=search_query,
            )
            | Q(
                members__role="admin",
                members__is_active=True,
                members__user__username__icontains=search_query,
            )
        ).distinct()

    if status_filter in {"pending", "approved", "rejected"}:
        fpos = fpos.filter(verification_status=status_filter)

    if state_filter:
        fpos = fpos.filter(state=state_filter)

    # Pagination
    paginator = Paginator(fpos, 10)  # Show 10 FPOs per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Calculate unique locations (state-district combinations)
    unique_locations = fpos.values("state", "district").distinct().count()

    context = {
        "page_title": "FPOs",
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "state_filter": state_filter,
        "use_fpo_sidebar": True,
        "unique_locations": unique_locations,
        "total_fpos": total_fpos,
        "total_states": total_states,
        "total_districts": total_districts,
        "all_states": all_states,
    }
    return render(request, "fpo/fpos_list.html", context)


@login_required
def quick_guide(request):
    """Explain the FPO rating model in a concise administrator reference."""
    return render(
        request,
        "fpo/quick_guide.html",
        {
            "page_title": "Quick Guide",
            "use_fpo_sidebar": True,
        },
    )


@login_required
def export_yearly_submissions(request):
    """Export YearlySubmission with all submodels flattened into a CSV.

    Optional Query params:
    - financial_year: e.g., "2024-2025". If omitted, exports all years.
    """
    _require_user_admin(request)
    from django.db import connection

    fy = request.GET.get("financial_year")

    # Fetch base submissions without eager-loading decimal-heavy submodels
    submissions_qs = YearlySubmission.objects.reportable().select_related("fpo", "submitted_by", "reviewed_by").only(
        "id",
        "fpo",
        "financial_year",
        "status",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    if fy:
        submissions_qs = submissions_qs.filter(financial_year=fy)

    # Helper to list field names for a given model class
    def model_field_names(model_class, exclude=("id", "yearly_submission", "created_at", "updated_at")):
        if model_class is None:
            return []
        names = []
        for f in model_class._meta.get_fields():
            if hasattr(f, "attname") and not f.many_to_many and not f.one_to_many:
                if f.name not in exclude:
                    names.append(f.name)
        return names

    # Base headers
    headers = [
        "fpo_id",
        "fpo_name",
        "fpo_email",
        "fpo_phone",
        "fpo_state",
        "fpo_district",
        "financial_year",
        "status",
        "calculated_score",
        "governance_score",
        "business_score",
        "process_score",
        "financial_score",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    ]

    # Submodel headers
    def prefixed(prefix, fields):
        return [f"{prefix}_{name}" for name in fields]

    # Plain field name lists for extraction
    fpo_details_cols = model_field_names(FPODetailsSubmission)
    governance_cols = model_field_names(GovernanceSubmission)
    ceo_cols = model_field_names(CEOProfileSubmission)
    biz_cols = model_field_names(BusinessOperationsSubmission)
    compliance_cols = model_field_names(ComplianceDetailsSubmission)
    process_cols = model_field_names(ProcessesSystemsSubmission)
    sustain_cols = model_field_names(SustainableActivitiesSubmission)
    fin_cols = model_field_names(FinancialDetailsSubmissionV2)

    # Header field names (prefixed)
    fpo_details_fields = prefixed("fpo_details", fpo_details_cols)
    governance_fields = prefixed("governance", governance_cols)
    ceo_fields = prefixed("ceo_profile", ceo_cols)
    biz_fields = prefixed("business_operations", biz_cols)
    compliance_fields = prefixed("compliance", compliance_cols)
    process_fields = prefixed("processes_systems", process_cols)
    sustain_fields = prefixed("sustainable_activities", sustain_cols)
    fin_fields = prefixed("financial_v2", fin_cols)

    # Board directors summary columns
    board_fields = ["board_directors_count", "board_directors_summary"]

    headers = (
        headers
        + fpo_details_fields
        + governance_fields
        + ceo_fields
        + biz_fields
        + compliance_fields
        + process_fields
        + sustain_fields
        + fin_fields
        + board_fields
    )

    # Create CSV response
    filename = f"yearly_submissions_{fy or 'all'}.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)

    # Function to extract values in the same order as header subset
    def values_for(instance, fields):
        vals = []
        if not instance:
            return ["" for _ in fields]
        for name in fields:
            # Remove prefix and fetch attr safely
            attr = name.split("_", 1)[1] if "_" in name else name
            v = getattr(instance, attr, "")
            # Convert dates/datetimes to isoformat for consistency
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            vals.append(v)
        return vals

    # Helper: fetch a single row of a one-to-one submodel as text-cast values
    def fetch_submodel_values(table_name, fields, yearly_submission_id):
        if not fields:
            return []
        if not table_name:
            return ["" for _ in fields]
        # Cast every column to TEXT to avoid Decimal conversion issues
        casted_cols = ", ".join([f"CAST({name} AS TEXT) AS {name}" for name in fields])
        sql = f"SELECT {casted_cols} FROM {table_name} WHERE yearly_submission_id = ? LIMIT 1"
        # Use raw cursor to avoid Django's debug formatting (%-style)
        if connection.connection is None:
            connection.ensure_connection()
        cursor = connection.connection.cursor()
        try:
            cursor.execute(sql, (yearly_submission_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            return ["" for _ in fields]
        return ["" if v is None else str(v) for v in row]

    # Helper: fetch YearlySubmission decimal fields as TEXT to avoid conversion
    def fetch_submission_decimal_values(submission_id):
        fields = ["calculated_score", "governance_score", "business_score", "process_score", "financial_score"]
        casted_cols = ", ".join([f"CAST({name} AS TEXT) AS {name}" for name in fields])
        table = YearlySubmission._meta.db_table
        sql = f"SELECT {casted_cols} FROM {table} WHERE id = ? LIMIT 1"
        if connection.connection is None:
            connection.ensure_connection()
        cursor = connection.connection.cursor()
        try:
            cursor.execute(sql, (submission_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            return ["" for _ in fields]
        return ["" if v is None else str(v) for v in row]

    # Iterate through submissions and write rows
    for s in submissions_qs.iterator():
        base_row = [
            s.fpo.id,
            s.fpo.name,
            s.fpo.email,
            s.fpo.phone,
            s.fpo.state,
            s.fpo.district,
            s.financial_year,
            s.get_status_display(),
        ]

        # Append decimal fields for submission as text (safe from NaN issues)
        base_row += fetch_submission_decimal_values(s.id)

        base_row += [
            (s.submitted_by.get_full_name() or s.submitted_by.username) if s.submitted_by else "",
            s.submitted_at.isoformat() if s.submitted_at else "",
            (s.reviewed_by.get_full_name() or s.reviewed_by.username) if s.reviewed_by else "",
            s.reviewed_at.isoformat() if s.reviewed_at else "",
            s.created_at.isoformat() if s.created_at else "",
            s.updated_at.isoformat() if s.updated_at else "",
        ]

        row = base_row

        # Append submodel values via raw SQL casts to TEXT
        row += fetch_submodel_values(
            FPODetailsSubmission._meta.db_table if FPODetailsSubmission else None,
            fpo_details_cols,
            s.id,
        )
        row += fetch_submodel_values(
            GovernanceSubmission._meta.db_table if GovernanceSubmission else None,
            governance_cols,
            s.id,
        )
        row += fetch_submodel_values(
            CEOProfileSubmission._meta.db_table if CEOProfileSubmission else None,
            ceo_cols,
            s.id,
        )
        row += fetch_submodel_values(
            BusinessOperationsSubmission._meta.db_table if BusinessOperationsSubmission else None,
            biz_cols,
            s.id,
        )
        row += fetch_submodel_values(
            ComplianceDetailsSubmission._meta.db_table if ComplianceDetailsSubmission else None,
            compliance_cols,
            s.id,
        )
        row += fetch_submodel_values(
            ProcessesSystemsSubmission._meta.db_table if ProcessesSystemsSubmission else None,
            process_cols,
            s.id,
        )
        row += fetch_submodel_values(
            SustainableActivitiesSubmission._meta.db_table if SustainableActivitiesSubmission else None,
            sustain_cols,
            s.id,
        )
        row += fetch_submodel_values(
            FinancialDetailsSubmissionV2._meta.db_table if FinancialDetailsSubmissionV2 else None,
            fin_cols,
            s.id,
        )

        # Board directors
        directors = list(getattr(s, "board_directors").all()) if hasattr(s, "board_directors") else []
        directors_count = len(directors)
        # Create a compact summary: Name (Qual, ExpType, Years)
        summary_parts = []
        for d in directors:
            summary_parts.append(
                f"{d.name} ({d.educational_qualification}, {d.type_of_experience}, {d.total_years_of_experience}y)"
            )
        directors_summary = "; ".join(summary_parts)
        row += [directors_count, directors_summary]

        writer.writerow(row)

    return response


@login_required
def export_fpo_details(request, pk):
    """Export YearlySubmissions for a specific FPO with all submodels flattened into a CSV."""
    from django.db import connection

    fpo = get_object_or_404(FPO, pk=pk)
    _require_fpo_view(request, fpo)

    # Fetch submissions for this specific FPO
    submissions_qs = YearlySubmission.objects.filter(fpo=fpo).select_related("fpo", "submitted_by", "reviewed_by").only(
        "id",
        "fpo",
        "financial_year",
        "status",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )

    # Helper to list field names for a given model class
    def model_field_names(model_class, exclude=("id", "yearly_submission", "created_at", "updated_at")):
        if model_class is None:
            return []
        names = []
        for f in model_class._meta.get_fields():
            if hasattr(f, "attname") and not f.many_to_many and not f.one_to_many:
                if f.name not in exclude:
                    names.append(f.name)
        return names

    # Base headers
    headers = [
        "fpo_id",
        "fpo_name",
        "fpo_email",
        "fpo_phone",
        "fpo_state",
        "fpo_district",
        "financial_year",
        "status",
        "calculated_score",
        "governance_score",
        "business_score",
        "process_score",
        "financial_score",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    ]

    # Submodel headers
    def prefixed(prefix, fields):
        return [f"{prefix}_{name}" for name in fields]

    # Plain field name lists for extraction
    fpo_details_cols = model_field_names(FPODetailsSubmission)
    governance_cols = model_field_names(GovernanceSubmission)
    ceo_cols = model_field_names(CEOProfileSubmission)
    biz_cols = model_field_names(BusinessOperationsSubmission)
    compliance_cols = model_field_names(ComplianceDetailsSubmission)
    process_cols = model_field_names(ProcessesSystemsSubmission)
    sustain_cols = model_field_names(SustainableActivitiesSubmission)
    fin_cols = model_field_names(FinancialDetailsSubmissionV2)

    # Header field names (prefixed)
    fpo_details_fields = prefixed("fpo_details", fpo_details_cols)
    governance_fields = prefixed("governance", governance_cols)
    ceo_fields = prefixed("ceo_profile", ceo_cols)
    biz_fields = prefixed("business_operations", biz_cols)
    compliance_fields = prefixed("compliance", compliance_cols)
    process_fields = prefixed("processes_systems", process_cols)
    sustain_fields = prefixed("sustainable_activities", sustain_cols)
    fin_fields = prefixed("financial_v2", fin_cols)

    # Board directors summary columns
    board_fields = ["board_directors_count", "board_directors_summary"]

    headers = (
        headers
        + fpo_details_fields
        + governance_fields
        + ceo_fields
        + biz_fields
        + compliance_fields
        + process_fields
        + sustain_fields
        + fin_fields
        + board_fields
    )

    # Create CSV response
    filename = f"{fpo.name}_yearly_submissions.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)

    # Helper: fetch a single row of a one-to-one submodel as text-cast values
    def fetch_submodel_values(table_name, fields, yearly_submission_id):
        if not fields:
            return []
        if not table_name:
            return ["" for _ in fields]
        # Cast every column to TEXT to avoid Decimal conversion issues
        casted_cols = ", ".join([f"CAST({name} AS TEXT) AS {name}" for name in fields])
        sql = f"SELECT {casted_cols} FROM {table_name} WHERE yearly_submission_id = ? LIMIT 1"
        # Use raw cursor to avoid Django's debug formatting (%-style)
        if connection.connection is None:
            connection.ensure_connection()
        cursor = connection.connection.cursor()
        try:
            cursor.execute(sql, (yearly_submission_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            return ["" for _ in fields]
        return ["" if v is None else str(v) for v in row]

    # Helper: fetch YearlySubmission decimal fields as TEXT to avoid conversion
    def fetch_submission_decimal_values(submission_id):
        fields = ["calculated_score", "governance_score", "business_score", "process_score", "financial_score"]
        casted_cols = ", ".join([f"CAST({name} AS TEXT) AS {name}" for name in fields])
        table = YearlySubmission._meta.db_table
        sql = f"SELECT {casted_cols} FROM {table} WHERE id = ? LIMIT 1"
        if connection.connection is None:
            connection.ensure_connection()
        cursor = connection.connection.cursor()
        try:
            cursor.execute(sql, (submission_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            return ["" for _ in fields]
        return ["" if v is None else str(v) for v in row]

    # Iterate through submissions and write rows
    for s in submissions_qs.iterator():
        base_row = [
            s.fpo.id,
            s.fpo.name,
            s.fpo.email,
            s.fpo.phone,
            s.fpo.state,
            s.fpo.district,
            s.financial_year,
            s.get_status_display(),
        ]

        # Append decimal fields for submission as text (safe from NaN issues)
        base_row += fetch_submission_decimal_values(s.id)

        base_row += [
            (s.submitted_by.get_full_name() or s.submitted_by.username) if s.submitted_by else "",
            s.submitted_at.isoformat() if s.submitted_at else "",
            (s.reviewed_by.get_full_name() or s.reviewed_by.username) if s.reviewed_by else "",
            s.reviewed_at.isoformat() if s.reviewed_at else "",
            s.created_at.isoformat() if s.created_at else "",
            s.updated_at.isoformat() if s.updated_at else "",
        ]

        row = base_row

        # Append submodel values via raw SQL casts to TEXT
        row += fetch_submodel_values(
            FPODetailsSubmission._meta.db_table if FPODetailsSubmission else None,
            fpo_details_cols,
            s.id,
        )
        row += fetch_submodel_values(
            GovernanceSubmission._meta.db_table if GovernanceSubmission else None,
            governance_cols,
            s.id,
        )
        row += fetch_submodel_values(
            CEOProfileSubmission._meta.db_table if CEOProfileSubmission else None,
            ceo_cols,
            s.id,
        )
        row += fetch_submodel_values(
            BusinessOperationsSubmission._meta.db_table if BusinessOperationsSubmission else None,
            biz_cols,
            s.id,
        )
        row += fetch_submodel_values(
            ComplianceDetailsSubmission._meta.db_table if ComplianceDetailsSubmission else None,
            compliance_cols,
            s.id,
        )
        row += fetch_submodel_values(
            ProcessesSystemsSubmission._meta.db_table if ProcessesSystemsSubmission else None,
            process_cols,
            s.id,
        )
        row += fetch_submodel_values(
            SustainableActivitiesSubmission._meta.db_table if SustainableActivitiesSubmission else None,
            sustain_cols,
            s.id,
        )
        row += fetch_submodel_values(
            FinancialDetailsSubmissionV2._meta.db_table if FinancialDetailsSubmissionV2 else None,
            fin_cols,
            s.id,
        )

        # Board directors
        directors = list(getattr(s, "board_directors").all()) if hasattr(s, "board_directors") else []
        directors_count = len(directors)
        # Create a compact summary: Name (Qual, ExpType, Years)
        summary_parts = []
        for d in directors:
            summary_parts.append(
                f"{d.name} ({d.educational_qualification}, {d.type_of_experience}, {d.total_years_of_experience}y)"
            )
        directors_summary = "; ".join(summary_parts)
        row += [directors_count, directors_summary]

        writer.writerow(row)

    return response


@login_required
def fpo_detail(request, pk):
    fpo = get_object_or_404(FPO, pk=pk)
    _require_fpo_view(request, fpo)
    members = fpo.members.filter(is_active=True).select_related("user")

    # Get yearly submissions for this FPO
    yearly_submissions = fpo.yearly_submissions.all().order_by("-financial_year")

    context = {
        "page_title": f"FPO - {fpo.name}",
        "fpo": fpo,
        "members": members,
        "yearly_submissions": yearly_submissions,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/fpo_detail.html", context)


@login_required
@require_http_methods(["POST"])
def fpo_delete(request, pk):
    """Delete an FPO if the user has permission.

    Allowed for:
    - Staff users, or
    - Active 'admin' members of the FPO
    """
    fpo = get_object_or_404(FPO, pk=pk)

    is_admin_member = FPOMember.objects.filter(fpo=fpo, user=request.user, role="admin", is_active=True).exists()

    if not (request.user.is_staff or is_admin_member):
        messages.error(request, "You don't have permission to delete this FPO.")
        return redirect("fpo:fpos_list")

    name = fpo.name
    try:
        fpo.delete()
        messages.success(request, f'FPO "{name}" has been deleted successfully.')
    except Exception as e:
        messages.error(request, f"Error deleting FPO: {str(e)}")

    # Redirect back to list, preserving page/search if provided via 'next'
    redirect_url = reverse("fpo:fpos_list")
    next_qs = request.POST.get("next", "").strip()
    if next_qs:
        if next_qs.startswith("?"):
            redirect_url = redirect_url + next_qs
        else:
            redirect_url = redirect_url + "?" + next_qs
    return redirect(redirect_url)


@login_required
def fpo_create(request):
    if request.method == "POST":
        # Get form data
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        alternate_phone = request.POST.get("alternate_phone")
        address_line_1 = request.POST.get("address_line_1")
        address_line_2 = request.POST.get("address_line_2")
        city = request.POST.get("city")
        district = request.POST.get("district")
        state = request.POST.get("state")
        pincode = request.POST.get("pincode")

        # Basic validation
        if not all([name, email, phone, address_line_1, city, district, state, pincode]):
            messages.error(request, "Please fill in all required fields.")
            return render(request, "fpo/fpo_create.html", {"form_data": request.POST})

        try:
            # Create FPO
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
                created_by=request.user,
            )
            messages.success(request, f'FPO "{fpo.name}" has been created successfully.')
            return redirect("fpo:fpo_detail", pk=fpo.pk)
        except Exception as e:
            messages.error(request, f"Error creating FPO: {str(e)}")
            return render(request, "fpo/fpo_create.html", {"form_data": request.POST})

    context = {
        "page_title": "Create New FPO",
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/fpo_create.html", context)


@login_required
def fpo_verification_requests(request):
    """Show FPO registrations awaiting an admin verification decision."""
    _require_fpo_verifier(request)

    selected_status = request.GET.get("status", FPOVerificationStatus.PENDING)
    valid_statuses = {value for value, _label in FPOVerificationStatus.choices}
    if selected_status not in valid_statuses:
        selected_status = FPOVerificationStatus.PENDING

    search_query = request.GET.get("search", "").strip()
    sort_field = "created_at" if selected_status == FPOVerificationStatus.PENDING else "-reviewed_at"
    fpos = (
        FPO.objects.filter(verification_status=selected_status)
        .select_related("created_by", "reviewed_by")
        .annotate(data_entries_count=Count("yearly_submissions", distinct=True))
        .order_by(sort_field)
    )
    if search_query:
        fpos = fpos.filter(
            Q(name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(district__icontains=search_query)
            | Q(state__icontains=search_query)
        )

    paginator = Paginator(fpos, 25)
    verification_counts = dict(
        FPO.objects.values("verification_status")
        .annotate(total=Count("pk"))
        .values_list("verification_status", "total")
    )
    context = {
        "page_title": "FPO Verification Requests",
        "use_fpo_sidebar": True,
        "page_obj": paginator.get_page(request.GET.get("page")),
        "selected_status": selected_status,
        "status_choices": FPOVerificationStatus.choices,
        "search_query": search_query,
        "pending_count": verification_counts.get(FPOVerificationStatus.PENDING, 0),
        "approved_count": verification_counts.get(FPOVerificationStatus.APPROVED, 0),
        "rejected_count": verification_counts.get(FPOVerificationStatus.REJECTED, 0),
    }
    return render(request, "fpo/verification_requests.html", context)


@login_required
@require_POST
def review_fpo_verification(request, pk):
    """Approve or reject an FPO profile."""
    _require_fpo_verifier(request)
    fpo = get_object_or_404(FPO, pk=pk)
    decision = request.POST.get("decision", "").strip().lower()
    notes = request.POST.get("notes", "").strip()

    if decision == "approve":
        fpo.approve_verification(request.user, notes)
        messages.success(request, f'FPO "{fpo.name}" is now verified and reportable.')
    elif decision == "reject":
        if not notes:
            messages.error(request, "Please provide a reason before rejecting an FPO.")
            return redirect(f"{reverse('fpo:verification_requests')}?status={fpo.verification_status}")
        fpo.reject_verification(request.user, notes)
        messages.success(request, f'FPO "{fpo.name}" was rejected.')
    else:
        messages.error(request, "Choose either approve or reject.")

    return redirect(f"{reverse('fpo:verification_requests')}?status={FPOVerificationStatus.PENDING}")


@login_required
def reports(request):
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Q

    # Get current month start and last month start
    now = timezone.now()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

    # Basic counts
    total_fpos = FPO.objects.publicly_visible().count()
    active_fpos = FPO.objects.publicly_visible().count()
    total_members = FPOMember.objects.filter(is_active=True, fpo__in=FPO.objects.publicly_visible()).count()

    # Activities this month
    activities_this_month = YearlySubmission.objects.reportable().filter(submitted_at__gte=this_month_start).count()

    # Registration growth (FPOs created this month vs last month)
    fpos_this_month = FPO.objects.publicly_visible().filter(created_at__gte=this_month_start).count()
    fpos_last_month = FPO.objects.publicly_visible().filter(
        created_at__gte=last_month_start,
        created_at__lt=this_month_start,
    ).count()

    # Calculate growth rate
    if fpos_last_month > 0:
        growth_rate = ((fpos_this_month - fpos_last_month) / fpos_last_month) * 100
    else:
        growth_rate = 100 if fpos_this_month > 0 else 0

    # Member distribution by FPO size
    # Get member counts for each FPO
    fpos_with_member_counts = FPO.objects.publicly_visible().annotate(
        member_count=Count("members", filter=Q(members__is_active=True))
    )

    small_fpos = fpos_with_member_counts.filter(member_count__gte=1, member_count__lte=10).count()
    medium_fpos = fpos_with_member_counts.filter(member_count__gte=11, member_count__lte=50).count()
    large_fpos = fpos_with_member_counts.filter(member_count__gt=50).count()

    # Activity summary
    total_activities = YearlySubmission.objects.reportable().count()

    # Calculate average activities per FPO
    avg_activities_per_fpo = total_activities / total_fpos if total_fpos > 0 else 0

    # Find most active FPO (by number of submissions)
    most_active_fpo = (
        YearlySubmission.objects.reportable().values("fpo__name")
        .annotate(submission_count=Count("id"))
        .order_by("-submission_count")
        .first()
    )

    most_active_fpo_name = most_active_fpo["fpo__name"] if most_active_fpo else "-"

    context = {
        "page_title": "Reports",
        "use_fpo_sidebar": True,
        # Main KPIs
        "total_fpos": total_fpos,
        "active_fpos": active_fpos,
        "total_members": total_members,
        "activities_this_month": activities_this_month,
        # Registration growth
        "fpos_this_month": fpos_this_month,
        "fpos_last_month": fpos_last_month,
        "growth_rate": round(growth_rate, 1),
        # Member distribution
        "small_fpos": small_fpos,
        "medium_fpos": medium_fpos,
        "large_fpos": large_fpos,
        # Activity summary
        "total_activities": total_activities,
        "avg_activities_per_fpo": round(avg_activities_per_fpo, 1),
        "most_active_fpo": most_active_fpo_name,
    }
    return render(request, "fpo/reports.html", context)


@login_required
def add_member(request, fpo_pk):
    if request.method == "POST":
        fpo = get_object_or_404(FPO, pk=fpo_pk)
        _require_fpo_admin(request, fpo)
        user_id = request.POST.get("user_id")
        role = request.POST.get("role", "viewer")
        if role not in ("admin", "viewer"):
            messages.error(request, "Invalid role.")
            return redirect("fpo:fpo_detail", pk=fpo_pk)

        try:
            user = User.objects.get(pk=user_id)
            member, created = FPOMember.objects.get_or_create(
                fpo=fpo, user=user, defaults={"role": role, "is_active": True}
            )

            if created:
                messages.success(request, f"{user.get_full_name() or user.username} has been added as {role}.")
            else:
                if not member.is_active:
                    member.is_active = True
                    member.role = role
                    member.save()
                    messages.success(
                        request, f"{user.get_full_name() or user.username} has been reactivated as {role}."
                    )
                else:
                    messages.warning(request, f"{user.get_full_name() or user.username} is already a member.")
        except User.DoesNotExist:
            messages.error(request, "User not found.")
        except Exception as e:
            messages.error(request, f"Error adding member: {str(e)}")

    return redirect("fpo:fpo_detail", pk=fpo_pk)


@login_required
def remove_member(request, fpo_pk, member_pk):
    if request.method == "POST":
        fpo = get_object_or_404(FPO, pk=fpo_pk)
        _require_fpo_admin(request, fpo)
        member = get_object_or_404(FPOMember, pk=member_pk, fpo=fpo)

        member.is_active = False
        member.save()
        messages.success(
            request, f"{member.user.get_full_name() or member.user.username} has been removed from the FPO."
        )

    return redirect("fpo:fpo_detail", pk=fpo_pk)


@login_required
def update_member_role(request, fpo_pk, member_pk):
    if request.method == "POST":
        fpo = get_object_or_404(FPO, pk=fpo_pk)
        _require_fpo_admin(request, fpo)
        member = get_object_or_404(FPOMember, pk=member_pk, fpo=fpo)
        new_role = request.POST.get("role")

        if new_role in ["admin", "viewer"]:
            member.role = new_role
            member.save()
            messages.success(
                request, f"{member.user.get_full_name() or member.user.username} role updated to {new_role}."
            )
        else:
            messages.error(request, "Invalid role.")

    return redirect("fpo:fpo_detail", pk=fpo_pk)


@login_required
def update_store_link(request, pk):
    if request.method == "POST":
        fpo = get_object_or_404(FPO, pk=pk)
        _require_fpo_admin(request, fpo)
        store_link = request.POST.get("store_link", "").strip()
        if store_link:
            try:
                URLValidator(schemes=["http", "https"])(store_link)
            except ValidationError:
                messages.error(request, "Enter a full web address starting with http:// or https://.")
                return redirect("fpo:fpo_detail", pk=pk)
        fpo.store_link = store_link if store_link else None
        fpo.save(update_fields=["store_link"])
        messages.success(request, "Store link updated successfully.")
    return redirect("fpo:fpo_detail", pk=pk)


@login_required
def search_users(request):
    user = request.user
    if not (
        user.is_staff
        or user.is_superuser
        or user.groups.filter(name="admin").exists()
        or FPOMember.objects.filter(user=user, is_active=True, role="admin").exists()
    ):
        raise PermissionDenied("You do not have permission to search users.")
    query = request.GET.get("q", "")
    users = []

    is_platform_admin = user.is_staff or user.is_superuser or user.groups.filter(name="admin").exists()
    if query and len(query) >= 2:
        if is_platform_admin:
            users_qs = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )[:10]
        else:
            # FPO admins can create their own FPO, so they must not be able to browse accounts:
            # only an exact email or username finds someone.
            users_qs = User.objects.filter(Q(email__iexact=query) | Q(username__iexact=query))[:1]

        users = [
            {
                "id": found.id,
                "username": found.username,
                "full_name": found.get_full_name(),
                **({"email": found.email} if is_platform_admin else {}),
            }
            for found in users_qs
        ]

    return JsonResponse({"users": users})


@login_required
def user_management(request):
    """View for managing users in the FPO system"""
    _require_user_admin(request)
    search_query = request.GET.get("search", "")
    role_filter = request.GET.get("role", "")

    # Get all users
    users = User.objects.all().prefetch_related("fpomember_set__fpo")

    # Apply search filter
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    # Apply role filter
    if role_filter:
        if role_filter == "admin":
            users = users.filter(fpomember__role="admin", fpomember__is_active=True)
        elif role_filter == "viewer":
            users = users.filter(fpomember__role="viewer", fpomember__is_active=True)
        elif role_filter == "no_role":
            users = users.exclude(fpomember__is_active=True)

    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "User Management",
        "page_obj": page_obj,
        "search_query": search_query,
        "role_filter": role_filter,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/user_management.html", context)


@login_required
def user_detail(request, user_id):
    """Detailed view for a single user and their FPO memberships"""
    _require_user_admin(request)
    user_obj = get_object_or_404(User.objects.prefetch_related("fpomember_set__fpo"), id=user_id)

    memberships = list(user_obj.fpomember_set.select_related("fpo").all())
    active_memberships = [m for m in memberships if m.is_active]

    context = {
        "page_title": f"User - {user_obj.get_full_name() or user_obj.username}",
        "user_obj": user_obj,
        "memberships": memberships,
        "active_memberships": active_memberships,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/user_detail.html", context)


@csrf_exempt
@require_http_methods(["POST"])
@document_access
def process_fpo_document(request):
    """
    API endpoint to process FPO documents (PDF/images) using OpenAI
    and extract structured FPO information
    """
    try:
        # Get FPO ID
        fpo_id = request.POST.get("fpo_id")
        if not fpo_id:
            return JsonResponse({"error": "FPO ID is required"}, status=400)

        # Check if FPO exists
        try:
            fpo = FPO.objects.get(id=fpo_id)
        except FPO.DoesNotExist:
            return JsonResponse({"error": "FPO not found"}, status=404)

        # Get uploaded file
        if "document" not in request.FILES:
            return JsonResponse({"error": "No document uploaded"}, status=400)

        uploaded_file = request.FILES["document"]
        file_bytes = uploaded_file.read()
        submission_year = request.POST.get("financial_year")

        print(f"Submission year {submission_year}")

        # Determine file type
        file_extension = uploaded_file.name.split(".")[-1].lower()
        if file_extension == "pdf":
            file_type = "pdf"
        elif file_extension in ["jpg", "jpeg", "png", "gif", "bmp"]:
            file_type = "image"
        else:
            return JsonResponse({"error": "Unsupported file type. Please upload PDF or image files."}, status=400)

        # Initialize processor
        processor = FPODocumentProcessor()

        # Extract text content (same as test script)
        if file_type == "pdf":
            pdf_analysis = processor.extract_text_from_pdf(file_bytes)
            if pdf_analysis.get("has_text", False):
                text_content = pdf_analysis["text_content"]
            else:
                text_content = processor.ocr_with_qwen(file_bytes)
        elif file_type == "image":
            # Add image OCR method to your processor
            text_content = processor.ocr_with_qwen(file_bytes)  # Adapt for images

        if not text_content.strip():
            return JsonResponse({"error": "No text could be extracted from document"}, status=400)

        # Process all models sequentially (same as test script)
        models_to_test = [
            ("Basic Details", processor.extract_basic_details_only, processor.save_basic_details),
            ("Financial Details", processor.extract_financial_details, processor.save_financial_details),
            ("Board Directors", processor.extract_board_director_details, processor.save_board_director_details),
            ("FPO Details", processor.extract_fpo_details, processor.save_fpo_details),
            ("Governance", processor.extract_governance_details, processor.save_governance_details),
            ("CEO Profile", processor.extract_ceo_profile_details, processor.save_ceo_profile_details),
            (
                "Business Operations",
                processor.extract_business_operations_details,
                processor.save_business_operations_details,
            ),
            ("Compliance Details", processor.extract_compliance_details, processor.save_compliance_details),
            (
                "Sustainable Activities",
                processor.extract_sustainable_activities_details,
                processor.save_sustainable_activities_details,
            ),
            (
                "Processes Systems",
                processor.extract_processes_systems_details,
                processor.save_processes_systems_details,
            ),
        ]

        results = {}
        extracted_fields = {}
        submission_id = None
        for model_name, extract_func, save_func in models_to_test:
            try:
                extracted_data = extract_func(text_content)
                if extracted_data:
                    # Store the extracted fields and values for the summary
                    extracted_fields[model_name] = extracted_data

                    # The save functions should return the submission object
                    submission = save_func(int(fpo_id), extracted_data, submission_year, text_content)
                    if submission and hasattr(submission, "id"):
                        submission_id = submission.id
                    results[model_name] = "success"
                else:
                    results[model_name] = "no_data"
                    extracted_fields[model_name] = {}
            except Exception as e:
                results[model_name] = f"error: {str(e)}"
                extracted_fields[model_name] = {"error": str(e)}

        # Create a summary of what was changed with detailed field information
        successful_extractions = [model_name for model_name, result in results.items() if result == "success"]
        no_data_extractions = [model_name for model_name, result in results.items() if result == "no_data"]
        error_extractions = [model_name for model_name, result in results.items() if result.startswith("error:")]

        # Create a plain text summary of extracted fields
        text_summary = []
        text_summary.append("DOCUMENT PROCESSING SUMMARY")
        text_summary.append("=" * 50)
        text_summary.append(f"Successful extractions: {len(successful_extractions)}")
        text_summary.append(f"No data extractions: {len(no_data_extractions)}")
        text_summary.append(f"Error extractions: {len(error_extractions)}")
        text_summary.append("")

        # Add details for each successful extraction
        for model_name in successful_extractions:
            text_summary.append(f"{model_name.upper()}:")
            model_data = extracted_fields.get(model_name, {})

            # Handle different data types (dict vs list)
            if isinstance(model_data, dict):
                for field_name, field_value in model_data.items():
                    if field_value is not None and field_value != "":
                        text_summary.append(f"  • {field_name}: {field_value}")
            elif isinstance(model_data, list):
                for item in model_data:
                    if isinstance(item, dict):
                        for field_name, field_value in item.items():
                            if field_value is not None and field_value != "":
                                text_summary.append(f"  • {field_name}: {field_value}")
                        text_summary.append("  ---")  # Separator between list items
                    else:
                        text_summary.append(f"  • {item}")
            text_summary.append("")

        # Add no data models
        if no_data_extractions:
            text_summary.append("NO DATA EXTRACTED FOR:")
            for model_name in no_data_extractions:
                text_summary.append(f"  • {model_name}")
            text_summary.append("")

        # Add error models
        if error_extractions:
            text_summary.append("ERRORS ENCOUNTERED:")
            for model_name in error_extractions:
                error_msg = results[model_name].replace("error: ", "")
                text_summary.append(f"  • {model_name}: {error_msg}")
            text_summary.append("")

        summary = {
            "successful_extractions": successful_extractions,
            "no_data_extractions": no_data_extractions,
            "error_extractions": error_extractions,
            "total_successful": len(successful_extractions),
            "total_no_data": len(no_data_extractions),
            "total_errors": len(error_extractions),
            "extracted_fields": extracted_fields,
            "text_summary": "\n".join(text_summary),
        }

        return JsonResponse(
            {
                "success": True,
                "results": results,
                "submission_id": submission_id,
                "summary": summary,
                "message": "Document processed successfully",
            }
        )

    except Exception as e:
        import traceback

        print(f"API Error: {traceback.format_exc()}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def fpo_document_upload(request, pk):
    """
    View for the document upload interface
    """
    fpo = get_object_or_404(FPO, pk=pk)
    _require_fpo_admin(request, fpo)

    context = {
        "page_title": f"Upload Document - {fpo.name}",
        "fpo": fpo,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/document_upload.html", context)


@login_required
def submission_detail(request, fpo_pk, submission_pk):
    """
    View to display detailed information about a specific yearly submission
    """
    fpo = get_object_or_404(FPO, pk=fpo_pk)
    _require_fpo_view(request, fpo)
    submission = get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)

    # Get all related submission data
    submission_data = {
        "fpo_details": getattr(submission, "fpo_details", None),
        "governance": getattr(submission, "governance", None),
        "ceo_profile": getattr(submission, "ceo_profile", None),
        "board_directors": submission.board_directors.all() if hasattr(submission, "board_directors") else [],
        "business_operations": getattr(submission, "business_operations", None),
        "compliance_details": getattr(submission, "compliance_details", None),
        "processes_systems": getattr(submission, "processes_systems", None),
        "sustainable_activities": getattr(submission, "sustainable_activities", None),
        "financial_details": getattr(submission, "financial_details_v2", None),
    }

    # Prepare template-friendly data for each section
    template_data = {}
    for section_name, section_obj in submission_data.items():
        if section_obj:
            if section_name == "board_directors":
                # Board directors are already a list, just pass through
                template_data[section_name] = {
                    "type": "list",
                    "data": section_obj,
                    "fields": ["name", "educational_qualification", "total_years_of_experience", "type_of_experience"],
                }
            else:
                # Convert model instance to dict of public fields
                field_data = {}
                for field in section_obj._meta.fields:
                    field_name = field.name
                    if not field_name.startswith("_") and field_name not in [
                        "id",
                        "yearly_submission_id",
                        "created_at",
                        "updated_at",
                    ]:
                        value = getattr(section_obj, field_name)
                        # Use display value for fields with choices (enums)
                        if getattr(field, "choices", None):
                            display_getter = getattr(section_obj, f"get_{field_name}_display", None)
                            if callable(display_getter):
                                try:
                                    value = display_getter()
                                except Exception:
                                    # Fallback to raw value if display method fails
                                    pass
                        if value is not None and value != "":
                            field_data[field_name] = value

                template_data[section_name] = {"type": "fields", "data": field_data}

    context = {
        "page_title": f"Submission - {submission.financial_year} - {fpo.name}",
        "fpo": fpo,
        "submission": submission,
        "submission_data": template_data,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/submission_detail.html", context)


@login_required
def submission_edit(request, fpo_pk, submission_pk):
    """
    View to edit a specific yearly submission with full form handling
    """
    from django.forms import modelform_factory, inlineformset_factory

    fpo = get_object_or_404(FPO, pk=fpo_pk)
    submission = get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)

    # Check if user has permission to edit this submission
    # Allow FPO members and staff users to edit submissions
    is_fpo_member = FPOMember.objects.filter(fpo=fpo, user=request.user, is_active=True).exists()
    is_staff_user = request.user.is_staff

    if not (is_fpo_member or is_staff_user):
        messages.error(request, "You don't have permission to edit this submission.")
        return redirect("fpo:submission_detail", fpo_pk=fpo_pk, submission_pk=submission_pk)

    # Check if submission can be edited based on status
    if not submission.can_edit():
        messages.error(request, f"This submission cannot be edited. Current status: {submission.get_status_display()}.")
        return redirect("fpo:submission_detail", fpo_pk=fpo_pk, submission_pk=submission_pk)

    # Define form classes for each submission type
    form_classes = {}

    # FPO Details Form
    if FPODetailsSubmission:
        form_classes["fpo_details"] = modelform_factory(
            FPODetailsSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Governance Form
    if GovernanceSubmission:
        form_classes["governance"] = modelform_factory(
            GovernanceSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # CEO Profile Form
    if CEOProfileSubmission:
        form_classes["ceo_profile"] = modelform_factory(
            CEOProfileSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Board Directors Formset
    if BoardDirectorProfile:
        BoardDirectorFormset = inlineformset_factory(
            YearlySubmission,
            BoardDirectorProfile,
            fields=[
                "name",
                "educational_qualification",
                "type_of_experience",
                "other_experience",
                "total_years_of_experience",
            ],
            extra=1,
            can_delete=True,
        )
        form_classes["board_directors"] = BoardDirectorFormset

    # Business Operations Form
    if BusinessOperationsSubmission:
        form_classes["business_operations"] = modelform_factory(
            BusinessOperationsSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Compliance Details Form
    if ComplianceDetailsSubmission:
        form_classes["compliance_details"] = modelform_factory(
            ComplianceDetailsSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Processes & Systems Form
    if ProcessesSystemsSubmission:
        form_classes["processes_systems"] = modelform_factory(
            ProcessesSystemsSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Sustainable Activities Form
    if SustainableActivitiesSubmission:
        form_classes["sustainable_activities"] = modelform_factory(
            SustainableActivitiesSubmission, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    # Financial Details Form
    if FinancialDetailsSubmissionV2:
        form_classes["financial_details"] = modelform_factory(
            FinancialDetailsSubmissionV2, fields="__all__", exclude=["yearly_submission", "created_at", "updated_at"]
        )

    forms = {}
    form_instances = {}

    # Initialize forms with existing data if available
    for model_name, form_class in form_classes.items():
        if model_name == "board_directors":
            # Handle formset for board directors
            if request.method == "POST":
                forms[model_name] = form_class(request.POST, instance=submission, prefix=model_name)
            else:
                forms[model_name] = form_class(instance=submission, prefix=model_name)
        else:
            # Handle regular forms
            instance = getattr(submission, model_name, None)
            if request.method == "POST":
                forms[model_name] = form_class(request.POST, instance=instance, prefix=model_name)
            else:
                forms[model_name] = form_class(instance=instance, prefix=model_name)
            form_instances[model_name] = instance

    if request.method == "POST":
        # Check which forms are valid
        all_valid = True
        for form_name, form in forms.items():
            if not form.is_valid():
                all_valid = False
                break

        if all_valid:
            # Save all forms
            for form_name, form in forms.items():
                if form_name == "board_directors":
                    # Save formset
                    form.save()
                else:
                    # Save regular form
                    instance = form.save(commit=False)
                    instance.yearly_submission = submission
                    instance.save()

            # Handle submission action
            action = request.POST.get("action")
            if action == "submit":
                if submission.submit_for_review(request.user):
                    messages.success(
                        request, f"Submission for {submission.financial_year} has been submitted for review."
                    )
                else:
                    messages.error(
                        request, f"Cannot submit submission. Current status: {submission.get_status_display()}."
                    )
            else:
                messages.success(request, f"Changes to {submission.financial_year} submission have been saved.")

            return redirect("fpo:submission_detail", fpo_pk=fpo_pk, submission_pk=submission_pk)
        else:
            messages.error(request, "Please correct the errors below.")

    context = {
        "page_title": f"Edit Submission - {submission.financial_year} - {fpo.name}",
        "fpo": fpo,
        "submission": submission,
        "use_fpo_sidebar": True,
    }

    # Add forms to context
    for form_name, form in forms.items():
        context[f"{form_name}_form"] = form

    return render(request, "fpo/submission_edit.html", context)


# @login_required
# def submission_pdf_report(request, fpo_pk, submission_pk):
#     """
#     Generate a comprehensive PDF report using the new dynamic template
#     """
#     fpo = get_object_or_404(FPO, pk=fpo_pk)
#     submission = get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)

#     # Get selected sections from query parameters
#     sections = request.GET.getlist('sections')
#     if not sections:
#         # Default to the 4 sections your API returns
#         sections = ['governance', 'business', 'process', 'financial']

#     # Calculate all the report data
#     calculator = FPOScoreCalculator(submission)
#     total_score = calculator.calculate_total_score()
#     section_scores = calculator.get_section_scores()
#     indicators = calculator.get_detailed_indicators()
#     category = calculator.get_performance_category_stored()
#     active_membership_pct = calculator.get_active_membership_percentage()

#     context = {
#         "fpo": fpo,
#         "submission": submission,
#         "submission_id": submission_pk,
#         "selected_sections": sections,
#         "current_date": timezone.now(),
#         # Add all the calculated data
#         "total_score": float(total_score),
#         "section_scores": {k: float(v) for k, v in section_scores.items()},
#         "indicators": indicators,
#         "category": category,
#         "active_membership_pct": active_membership_pct,
#         "fpo_details": {
#             'name': submission.fpo_details.name_of_producer_organization,
#             'promoting_agency_name': submission.fpo_details.promoting_agency_name,
#             'location': submission.fpo_details.registered_address,
#             'size': submission.fpo_details.size_of_fpo_fy_23_24,
#             'quantity_procured': submission.financial_details_v2.current_year_quantity_procured if hasattr(submission, 'financial_details_v2') else None,
#             'crops': submission.financial_details_v2.current_year_institutional_products if hasattr(submission, 'financial_details_v2') else None,
#             'total_revenue': submission.financial_details_v2.current_year_revenue if hasattr(submission, 'financial_details_v2') else None,

#         }
#     }

#     return render(request, "fpo/fpo_report.html", context)


def _build_submission_report_context(submission):
    calculator = FPOScoreCalculator(submission)
    total_score = submission.calculated_score
    if total_score is None:
        total_score = calculator.calculate_total_score()

    section_scores = {
        "governance": submission.governance_score or 0,
        "business": submission.business_score or 0,
        "process": submission.process_score or 0,
        "financial": submission.financial_score or 0,
    }
    indicators = calculator.get_detailed_indicators()
    category = calculator.get_performance_category_stored()
    active_membership_pct = calculator.get_active_membership_percentage()
    fpo_details = getattr(submission, "fpo_details", None)
    financial_details = getattr(submission, "financial_details_v2", None)

    return {
        "fpo": submission.fpo,
        "submission": submission,
        "total_score": float(total_score),
        "section_scores": {k: float(v) for k, v in section_scores.items()},
        "indicators": indicators,
        "category": category,
        "active_membership_pct": active_membership_pct,
        "fpo_details": {
            "name": (
                fpo_details.name_of_producer_organization
                if fpo_details and fpo_details.name_of_producer_organization
                else submission.fpo.name
            ),
            "financial_year": submission.financial_year,
            "promoting_agency_name": fpo_details.promoting_agency_name if fpo_details else None,
            "location": fpo_details.registered_address if fpo_details else None,
            "size": fpo_details.size_of_fpo_fy_23_24 if fpo_details else None,
            "quantity_procured": (
                financial_details.current_year_quantity_procured if financial_details else None
            ),
            "crops": financial_details.current_year_institutional_products if financial_details else None,
            "total_revenue": financial_details.current_year_revenue if financial_details else None,
        },
    }


@login_required
@xframe_options_sameorigin
def submission_report_view(request, fpo_pk, submission_pk):
    fpo = get_object_or_404(FPO, pk=fpo_pk)
    _require_fpo_view(request, fpo)
    submission = get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)
    context = _build_submission_report_context(submission)
    return render(request, "fpo/fpo_report.html", context)


@require_GET
def submission_pdf_link(request, fpo_pk, submission_pk):
    """Return a short-lived signed URL for the PDF report (used by the mobile app, which opens it in a browser)."""
    user = report_access.user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Please sign in to download this report."}, status=401)
    fpo = get_object_or_404(FPO, pk=fpo_pk)
    get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)
    if not report_access.can_view_fpo(user, fpo):
        return JsonResponse({"error": "You do not have permission to view this report."}, status=403)
    url = reverse("fpo:submission_pdf_report", args=[fpo_pk, submission_pk])
    sig = report_access.sign_pdf_link(fpo_pk, submission_pk)
    return JsonResponse(
        {"url": request.build_absolute_uri(f"{url}?sig={sig}"), "expires_in": report_access.PDF_LINK_MAX_AGE}
    )


@require_GET
def submission_pdf_report(request, fpo_pk, submission_pk):
    # Import WeasyPrint here to avoid startup errors if dependencies aren't configured
    from weasyprint import CSS, HTML

    fpo = get_object_or_404(FPO, pk=fpo_pk)
    sig = request.GET.get("sig")
    if sig:
        if not report_access.pdf_link_is_valid(sig, fpo_pk, submission_pk):
            raise PermissionDenied("This download link is invalid or has expired.")
    elif not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    elif not report_access.can_view_fpo(request.user, fpo):
        raise PermissionDenied("You do not have permission to view this report.")
    submission = get_object_or_404(YearlySubmission, pk=submission_pk, fpo=fpo)
    context = _build_submission_report_context(submission)

    html_string = render_to_string("fpo/fpo_report.html", context)
    html = HTML(string=html_string)

    # Set all margins to 0 to remove white borders
    pdf = html.write_pdf(
        stylesheets=[
            CSS(
                string="""
        @page {
            margin: 0;
            padding: 0;
        }
    """
            )
        ]
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{fpo.name}_report.pdf"'
    return response


@login_required
def fpo_pdf_report(request, pk):
    """
    Generate a comprehensive PDF report for an FPO with all submissions
    """
    fpo = get_object_or_404(FPO, pk=pk)

    # Get all submissions for this FPO
    submissions = fpo.yearly_submissions.all().order_by("-financial_year")

    # Get FPO members
    members = fpo.members.filter(is_active=True)

    context = {
        "fpo": fpo,
        "submissions": submissions,
        "members": members,
        "report_type": request.GET.get("type", "detailed"),
    }

    return render(request, "fpo/fpo_pdf_report.html", context)


REPORT_SECTIONS = {"overview", "governance", "operations", "systems", "finance"}
REPORT_TABS = {"size", "gender", "agency", "state", "performance", "lending"}
GOVERNANCE_FOCUS_OPTIONS = {"second_line_management", "minutes_fpo_meetings", "promoting_agencies"}
GOVERNANCE_METRIC_OPTIONS = {
    "governance_score",
    "active_membership",
    "quality_bod",
    "quality_ceo",
    "mobilization_achievement",
    "optimal_bod_percent",
}
OPERATIONS_FOCUS_OPTIONS = {
    "type_of_fpo",
    "price_volatility",
    "input_timeliness",
    "input_affordability",
    "input_place",
    "output_distance",
    "credit_history",
}
OPERATIONS_METRIC_OPTIONS = OPERATIONS_FOCUS_OPTIONS
FINANCE_FOCUS_OPTIONS = {
    "net_profit",
    "revenue_per_member",
    "inventory_period",
    "asset_turnover_ratio",
    "accounts_payable",
    "accounts_receivable",
}
FINANCE_METRIC_OPTIONS = FINANCE_FOCUS_OPTIONS
SYSTEMS_FOCUS_OPTIONS = {
    "accounts_mis",
    "insurance_stock",
    "credit_record",
    "statutory_filings",
    "books_records",
    "stock_reconciliation",
    "penalties_levied",
}
SYSTEMS_METRIC_OPTIONS = SYSTEMS_FOCUS_OPTIONS

SECTION_SCORE_FIELDS = {
    "overview": "calculated_score",
    "governance": "governance_score",
    "operations": "business_score",
    "systems": "process_score",
    "finance": "financial_score",
}

DIMENSION_ORDER = {
    "size": ["Large FPO", "Small FPO"],
    "gender": ["Mixed", "Women Only"],
    "performance": ["Achievers", "Performers", "Aspirational", "N/A"],
    "lending": [
        "No history of institutional lending",
        "At least 1 institutional lending in last 2 financial year",
        "History Repeated lending from any institutional lenders in last 2 financial years",
    ],
}


def _normalize_report_section(section):
    return section if section in REPORT_SECTIONS else "overview"


def _normalize_chart_tab(tab):
    return tab if tab in REPORT_TABS else "size"


def _normalize_governance_focus(focus):
    return focus if focus in GOVERNANCE_FOCUS_OPTIONS else "second_line_management"


def _normalize_governance_metric(metric):
    return metric if metric in GOVERNANCE_METRIC_OPTIONS else "governance_score"


def _normalize_operations_focus(focus):
    return focus if focus in OPERATIONS_FOCUS_OPTIONS else "price_volatility"


def _normalize_operations_metric(metric):
    return metric if metric in OPERATIONS_METRIC_OPTIONS else "price_volatility"


def _normalize_finance_focus(focus):
    return focus if focus in FINANCE_FOCUS_OPTIONS else "net_profit"


def _normalize_finance_metric(metric):
    return metric if metric in FINANCE_METRIC_OPTIONS else "net_profit"


def _normalize_systems_focus(focus):
    return focus if focus in SYSTEMS_FOCUS_OPTIONS else "accounts_mis"


def _normalize_systems_metric(metric):
    return metric if metric in SYSTEMS_METRIC_OPTIONS else "accounts_mis"


def _parse_report_datetime(value):
    if not value:
        return None

    parsed = parse_datetime(value)
    if parsed is None:
        fallback_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %I:%M %p",
            "%Y-%m-%dT%I:%M %p",
        ]
        for fmt in fallback_formats:
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())

    return parsed


def _apply_submission_datetime_filters(queryset, start_datetime=None, end_datetime=None):
    if start_datetime:
        queryset = queryset.filter(created_at__gte=start_datetime)
    if end_datetime:
        queryset = queryset.filter(created_at__lte=end_datetime)
    return queryset


def _safe_related(instance, attr):
    try:
        return getattr(instance, attr)
    except Exception:
        return None


def _choice_label(choices, value, default=None):
    if not value:
        return default
    return dict(choices).get(value, default or value)


def _build_latest_report_rows(
    filtered_fpo_ids,
    selected_financial_year="",
    selected_start_datetime=None,
    selected_end_datetime=None,
):
    if not filtered_fpo_ids:
        return []

    submission_query = YearlySubmission.objects.reportable().filter(fpo_id__in=filtered_fpo_ids)
    if selected_financial_year:
        submission_query = submission_query.filter(financial_year=selected_financial_year)
    submission_query = _apply_submission_datetime_filters(
        submission_query,
        selected_start_datetime,
        selected_end_datetime,
    )

    submissions = (
        submission_query.select_related(
            "fpo",
            "fpo_details",
            "governance",
            "ceo_profile",
            "business_operations",
            "processes_systems",
            "financial_details_v2",
        )
        .prefetch_related("board_directors")
        .order_by("fpo_id", "-financial_year", "-id")
    )

    rows = []
    seen_fpo_ids = set()
    for submission in submissions:
        if submission.fpo_id in seen_fpo_ids:
            continue

        seen_fpo_ids.add(submission.fpo_id)
        rows.append(
            {
                "submission": submission,
                "fpo": submission.fpo,
                "details": _safe_related(submission, "fpo_details"),
                "governance": _safe_related(submission, "governance"),
                "ceo_profile": _safe_related(submission, "ceo_profile"),
                "business_operations": _safe_related(submission, "business_operations"),
                "processes_systems": _safe_related(submission, "processes_systems"),
                "financial_details": _safe_related(submission, "financial_details_v2"),
                "board_directors": list(submission.board_directors.all()),
            }
        )

    return rows


def _get_dimension_value(row, dimension):
    details = row["details"]
    submission = row["submission"]
    financial_details = row["financial_details"]

    if dimension == "size":
        if not details or details.size_of_fpo_fy_23_24 is None:
            return None
        return "Small FPO" if details.size_of_fpo_fy_23_24 <= 1000 else "Large FPO"

    if dimension == "gender":
        if not details or not details.size_of_fpo_fy_23_24 or details.women_members is None:
            return None
        return "Women Only" if details.women_members >= details.size_of_fpo_fy_23_24 else "Mixed"

    if dimension == "agency":
        if not details or not details.promoting_agency_name:
            return None
        return details.promoting_agency_name.strip() or None

    if dimension == "state":
        state_name = getattr(row["fpo"], "state", "") or getattr(details, "state", "")
        return state_name or None

    if dimension == "performance":
        if submission.calculated_score is None:
            return "N/A"
        if submission.calculated_score >= 70:
            return "Achievers"
        if submission.calculated_score >= 50:
            return "Performers"
        return "Aspirational"

    if dimension == "lending":
        if not financial_details or not financial_details.institutional_lending_history:
            return None
        return _choice_label(
            InstitutionalLendingHistoryType.choices,
            financial_details.institutional_lending_history,
            default=None,
        )

    return None


def _ordered_labels_from_counts(counts, dimension):
    if not counts:
        return []

    if dimension == "state":
        return [label for label, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]]

    if dimension == "agency":
        return sorted(counts)

    preferred_order = DIMENSION_ORDER.get(dimension, [])
    ordered_labels = [label for label in preferred_order if counts.get(label)]
    remaining_labels = sorted(label for label in counts if label not in ordered_labels)
    return ordered_labels + remaining_labels


def _get_governance_focus_value(row, focus):
    governance = row["governance"]
    details = row["details"]

    if focus == "second_line_management":
        if not governance or not governance.second_line_management:
            return None
        return _choice_label(SecondLineManagementType.choices, governance.second_line_management, default=None)

    if focus == "minutes_fpo_meetings":
        if not governance or not governance.minutes_maintenance:
            return None
        return _choice_label(MinutesMaintenanceType.choices, governance.minutes_maintenance, default=None)

    if focus == "promoting_agencies":
        if not details or not details.promoting_agency_name:
            return None
        return details.promoting_agency_name.strip() or None

    return None


def _ordered_governance_focus_labels(counts, focus):
    if not counts:
        return []

    if focus == "second_line_management":
        preferred = [label for _, label in SecondLineManagementType.choices]
    elif focus == "minutes_fpo_meetings":
        preferred = [label for _, label in MinutesMaintenanceType.choices]
    else:
        preferred = []

    ordered = [label for label in preferred if counts.get(label)]
    remaining = sorted(label for label in counts if label not in ordered)
    return ordered + remaining


def _get_operations_focus_value(row, focus):
    details = row["details"]
    business_operations = row["business_operations"]
    financial_details = row["financial_details"]

    if focus == "type_of_fpo":
        if not details or not details.type_of_fpo:
            return None
        return _choice_label(FPOType.choices, details.type_of_fpo, default=None)

    if focus == "price_volatility":
        if not business_operations or not business_operations.price_volatility_of_products:
            return None
        return _choice_label(
            PriceVolatilityType.choices,
            business_operations.price_volatility_of_products,
            default=None,
        )

    if focus == "input_timeliness":
        if not business_operations or not business_operations.availability_of_inputs_timeliness:
            return None
        return _choice_label(
            InputTimelinessType.choices,
            business_operations.availability_of_inputs_timeliness,
            default=None,
        )

    if focus == "input_affordability":
        if not business_operations or not business_operations.availability_of_inputs_price_affordability:
            return None
        return _choice_label(
            PriceAffordabilityType.choices,
            business_operations.availability_of_inputs_price_affordability,
            default=None,
        )

    if focus == "input_place":
        if not business_operations or not business_operations.availability_of_inputs_place:
            return None
        return _choice_label(
            DistanceAvailabilityType.choices,
            business_operations.availability_of_inputs_place,
            default=None,
        )

    if focus == "output_distance":
        if not business_operations or not business_operations.distance_of_output_collection_centres:
            return None

        output_distance = business_operations.distance_of_output_collection_centres
        return _choice_label(
            DistanceAvailabilityType.choices,
            output_distance,
            default=output_distance,
        )

    if focus == "credit_history":
        if not financial_details or not financial_details.institutional_lending_history:
            return None
        return _choice_label(
            InstitutionalLendingHistoryType.choices,
            financial_details.institutional_lending_history,
            default=None,
        )

    return None


def _ordered_operations_focus_labels(counts, focus):
    if not counts:
        return []

    if focus == "type_of_fpo":
        preferred = [label for _, label in FPOType.choices]
    elif focus == "price_volatility":
        preferred = [label for _, label in PriceVolatilityType.choices]
    elif focus == "input_timeliness":
        preferred = [label for _, label in InputTimelinessType.choices]
    elif focus == "input_affordability":
        preferred = [label for _, label in PriceAffordabilityType.choices]
    elif focus in {"input_place", "output_distance"}:
        preferred = [label for _, label in DistanceAvailabilityType.choices]
    elif focus == "credit_history":
        preferred = [label for _, label in InstitutionalLendingHistoryType.choices]
    else:
        preferred = []

    ordered = [label for label in preferred if counts.get(label)]
    remaining = sorted(label for label in counts if label not in ordered)
    return ordered + remaining


def _get_systems_focus_value(row, focus):
    processes_systems = row["processes_systems"]
    if not processes_systems:
        return None

    if focus == "accounts_mis":
        return _choice_label(AccountsMISType.choices, processes_systems.accounts_and_mis, default=None)

    if focus == "insurance_stock":
        return _choice_label(InsuranceStockType.choices, processes_systems.insurance_of_stock, default=None)

    if focus == "credit_record":
        return _choice_label(CreditRecordType.choices, processes_systems.credit_record_of_fpo, default=None)

    if focus == "statutory_filings":
        return _choice_label(StatutoryFillingsType.choices, processes_systems.statutory_fillings, default=None)

    if focus == "books_records":
        return _choice_label(
            BooksRecordsType.choices,
            processes_systems.books_and_records_up_to_date,
            default=None,
        )

    if focus == "stock_reconciliation":
        return _choice_label(
            ReconciliationStocksType.choices,
            processes_systems.reconciliation_of_stocks,
            default=None,
        )

    if focus == "penalties_levied":
        penalties_value = processes_systems.penalties_levied_board_meeting
        if penalties_value is None:
            return None
        return "Penalties levied" if penalties_value else "No penalties levied"

    return None


def _ordered_systems_focus_labels(counts, focus):
    if not counts:
        return []

    if focus == "accounts_mis":
        preferred = [label for _, label in AccountsMISType.choices]
    elif focus == "insurance_stock":
        preferred = [label for _, label in InsuranceStockType.choices]
    elif focus == "credit_record":
        preferred = [label for _, label in CreditRecordType.choices]
    elif focus == "statutory_filings":
        preferred = [label for _, label in StatutoryFillingsType.choices]
    elif focus == "books_records":
        preferred = [label for _, label in BooksRecordsType.choices]
    elif focus == "stock_reconciliation":
        preferred = [label for _, label in ReconciliationStocksType.choices]
    elif focus == "penalties_levied":
        preferred = ["No penalties levied", "Penalties levied"]
    else:
        preferred = []

    ordered = [label for label in preferred if counts.get(label)]
    remaining = sorted(label for label in counts if label not in ordered)
    return ordered + remaining


def _get_finance_indicator_details(row, indicator):
    details = row["details"]
    financial_details = row["financial_details"]
    if not financial_details:
        return None, None

    if indicator == "revenue_per_member":
        if not details or details.farmers_transacted is None or details.farmers_transacted <= 0:
            return None, None
        if financial_details.current_year_revenue is None:
            return None, None

        rpm = float(financial_details.current_year_revenue) / float(details.farmers_transacted)
        if rpm >= 100000:
            return 3, ">= 1,00,000"
        if rpm >= 75000:
            return 2, "75,000 - 99,999"
        if rpm >= 50000:
            return 1, "50,000 - 74,999"
        return 0, "< 50,000"

    if indicator == "net_profit":
        if (
            financial_details.current_year_revenue is None
            or float(financial_details.current_year_revenue) <= 0
            or financial_details.current_year_net_profit is None
        ):
            return None, None

        net_profit_margin = (
            float(financial_details.current_year_net_profit) / float(financial_details.current_year_revenue)
        ) * 100
        if net_profit_margin >= 10:
            return 3, ">= 10%"
        if net_profit_margin >= 5:
            return 2, "5% - 9.99%"
        if net_profit_margin >= 0:
            return 1, "0% - 4.99%"
        return 0, "< 0%"

    if indicator == "inventory_period":
        if (
            financial_details.current_year_opening_inventory is None
            or financial_details.previous_year_opening_inventory is None
            or financial_details.current_year_cogs is None
            or float(financial_details.current_year_cogs) <= 0
        ):
            return None, None

        average_inventory = (
            float(financial_details.current_year_opening_inventory)
            + float(financial_details.previous_year_opening_inventory)
        ) / 2
        inventory_days = average_inventory / (float(financial_details.current_year_cogs) / 365)
        if inventory_days < 30:
            return 3, "< 30 days"
        if inventory_days < 60:
            return 2, "30 - 59 days"
        if inventory_days < 90:
            return 1, "60 - 89 days"
        return 0, ">= 90 days"

    if indicator == "accounts_payable":
        if (
            financial_details.current_year_accounts_payable is None
            or financial_details.previous_year_accounts_payable is None
            or financial_details.current_year_cogs is None
            or float(financial_details.current_year_cogs) <= 0
        ):
            return None, None

        average_payable = (
            float(financial_details.current_year_accounts_payable)
            + float(financial_details.previous_year_accounts_payable)
        ) / 2
        payable_days = average_payable / (float(financial_details.current_year_cogs) / 365)
        if payable_days < 30:
            return 3, "< 30 days"
        if payable_days < 60:
            return 2, "30 - 59 days"
        if payable_days < 90:
            return 1, "60 - 89 days"
        return 0, ">= 90 days"

    if indicator == "accounts_receivable":
        if (
            financial_details.current_year_accounts_receivable is None
            or financial_details.previous_year_accounts_receivable is None
            or financial_details.current_year_cogs is None
            or float(financial_details.current_year_cogs) <= 0
        ):
            return None, None

        average_receivable = (
            float(financial_details.current_year_accounts_receivable)
            + float(financial_details.previous_year_accounts_receivable)
        ) / 2
        receivable_days = average_receivable / (float(financial_details.current_year_cogs) / 365)
        if receivable_days < 30:
            return 3, "< 30 days"
        if receivable_days < 60:
            return 2, "30 - 59 days"
        if receivable_days < 90:
            return 1, "60 - 89 days"
        return 0, ">= 90 days"

    if indicator == "asset_turnover_ratio":
        if (
            financial_details.current_year_assets is None
            or financial_details.previous_year_assets is None
            or financial_details.current_year_revenue is None
            or float(financial_details.current_year_revenue) <= 0
        ):
            return None, None

        average_assets = (float(financial_details.current_year_assets) + float(financial_details.previous_year_assets)) / 2
        if average_assets <= 0:
            return None, None

        asset_turnover = float(financial_details.current_year_revenue) / average_assets
        if asset_turnover >= 2:
            return 4, ">= 2.0"
        if asset_turnover >= 1.5:
            return 3, "1.5 - 1.99"
        if asset_turnover >= 1:
            return 2, "1.0 - 1.49"
        if asset_turnover >= 0.5:
            return 1, "0.5 - 0.99"
        return 0, "< 0.5"

    return None, None


def _get_finance_focus_value(row, focus):
    _, label = _get_finance_indicator_details(row, focus)
    return label


def _get_finance_metric_value(row, metric):
    score, _ = _get_finance_indicator_details(row, metric)
    return score


def _ordered_finance_focus_labels(counts, focus):
    if not counts:
        return []

    if focus == "revenue_per_member":
        preferred = [">= 1,00,000", "75,000 - 99,999", "50,000 - 74,999", "< 50,000"]
    elif focus == "net_profit":
        preferred = [">= 10%", "5% - 9.99%", "0% - 4.99%", "< 0%"]
    elif focus in {"inventory_period", "accounts_payable", "accounts_receivable"}:
        preferred = ["< 30 days", "30 - 59 days", "60 - 89 days", ">= 90 days"]
    elif focus == "asset_turnover_ratio":
        preferred = [">= 2.0", "1.5 - 1.99", "1.0 - 1.49", "0.5 - 0.99", "< 0.5"]
    else:
        preferred = []

    ordered = [label for label in preferred if counts.get(label)]
    remaining = sorted(label for label in counts if label not in ordered)
    return ordered + remaining


def _calculate_board_quality_score(board_directors):
    scores = []
    for director in board_directors:
        years = director.total_years_of_experience or 0
        if years >= 12:
            score = 4
        elif years >= 10:
            score = 3
        elif years >= 8:
            score = 2
        elif years >= 5:
            score = 1
        else:
            score = 0

        if director.type_of_experience == BoardExperienceType.ANY_OTHER:
            score *= 0.5

        scores.append(score)

    if not scores:
        return None

    return sum(scores) / len(scores)


def _calculate_ceo_quality_score(ceo_profile):
    if not ceo_profile:
        return None

    years = ceo_profile.total_years_of_experience or 0
    if years >= 12:
        score = 4
    elif years >= 10:
        score = 3
    elif years >= 8:
        score = 2
    elif years >= 5:
        score = 1
    else:
        score = 0

    if ceo_profile.type_of_experience == ExperienceType.ANY_OTHER:
        score *= 0.5

    return score


def _calculate_mobilization_achievement(details):
    if not details or not details.target_size_of_fpo or not details.size_of_fpo_fy_23_24:
        return None
    return (details.size_of_fpo_fy_23_24 / details.target_size_of_fpo) * 100


def _calculate_optimal_bod_percent(details, board_directors):
    if not details or details.size_of_fpo_fy_23_24 is None:
        return None

    size_of_fpo = details.size_of_fpo_fy_23_24 or 0
    if size_of_fpo <= 1000:
        optimal_bod = 5
    else:
        optimal_bod = min(5 + math.ceil((size_of_fpo - 1000) / 1000), 15)

    if optimal_bod <= 0:
        return None

    actual_bod = len(board_directors)
    return (actual_bod / optimal_bod) * 100


def _calculate_active_membership(details):
    if not details or not details.size_of_fpo_fy_23_24 or details.farmers_transacted is None:
        return None
    return (details.farmers_transacted / details.size_of_fpo_fy_23_24) * 100


def _get_governance_metric_value(row, metric):
    submission = row["submission"]
    details = row["details"]

    if metric == "governance_score":
        return float(submission.governance_score) if submission.governance_score is not None else None
    if metric == "active_membership":
        return _calculate_active_membership(details)
    if metric == "quality_bod":
        return _calculate_board_quality_score(row["board_directors"])
    if metric == "quality_ceo":
        return _calculate_ceo_quality_score(row["ceo_profile"])
    if metric == "mobilization_achievement":
        return _calculate_mobilization_achievement(details)
    if metric == "optimal_bod_percent":
        return _calculate_optimal_bod_percent(details, row["board_directors"])
    return None


def _get_operations_metric_value(row, metric):
    details = row["details"]
    business_operations = row["business_operations"]
    financial_details = row["financial_details"]

    if metric == "type_of_fpo":
        if not details or not details.type_of_fpo:
            return None

        fpo_type_scores = {
            FPOType.INPUTS_OR_OUTPUT: 0,
            FPOType.INPUTS_AND_OUTPUT: 1,
            FPOType.LOW_CAPACITY: 2,
            FPOType.HIGH_CAPACITY: 3,
        }
        return fpo_type_scores.get(details.type_of_fpo)

    if metric == "price_volatility":
        if not business_operations or not business_operations.price_volatility_of_products:
            return None

        volatility_scores = {
            PriceVolatilityType.HIGHLY_VOLATILE_FPO_RISK: 0,
            PriceVolatilityType.MSP_FPO_RISK: 1,
            PriceVolatilityType.PARTIAL_HEDGE: 2,
            PriceVolatilityType.WELL_HEDGED: 3,
            PriceVolatilityType.NOT_APPLICABLE: 3,
        }
        return volatility_scores.get(business_operations.price_volatility_of_products)

    if metric == "input_timeliness":
        if not business_operations or not business_operations.availability_of_inputs_timeliness:
            return None

        timeliness_scores = {
            InputTimelinessType.THIRTY_DAYS: 4,
            InputTimelinessType.TWENTY_DAYS: 3,
            InputTimelinessType.FIFTEEN_DAYS: 2,
            InputTimelinessType.SEVEN_DAYS: 1,
            InputTimelinessType.NOT_APPLICABLE: 0,
        }
        return timeliness_scores.get(business_operations.availability_of_inputs_timeliness)

    if metric == "input_affordability":
        if not business_operations or not business_operations.availability_of_inputs_price_affordability:
            return None

        affordability_scores = {
            PriceAffordabilityType.TEN_TO_FIFTEEN_PERCENT: 4,
            PriceAffordabilityType.FIVE_TO_TEN_PERCENT: 3,
            PriceAffordabilityType.THREE_TO_FIVE_PERCENT: 2,
            PriceAffordabilityType.ONE_TO_THREE_PERCENT: 1,
            PriceAffordabilityType.NOT_APPLICABLE: 0,
        }
        return affordability_scores.get(business_operations.availability_of_inputs_price_affordability)

    if metric in {"input_place", "output_distance"}:
        if not business_operations:
            return None

        distance_value = (
            business_operations.availability_of_inputs_place
            if metric == "input_place"
            else business_operations.distance_of_output_collection_centres
        )
        if not distance_value:
            return None

        distance_scores = {
            DistanceAvailabilityType.THREE_KM: 4,
            DistanceAvailabilityType.SIX_KM: 3,
            DistanceAvailabilityType.TEN_KM: 2,
            DistanceAvailabilityType.NOT_WITHIN_TEN_KM: 1,
            DistanceAvailabilityType.NOT_APPLICABLE: 0,
        }
        return distance_scores.get(distance_value)

    if metric == "credit_history":
        if not financial_details or not financial_details.institutional_lending_history:
            return None

        credit_history_scores = {
            InstitutionalLendingHistoryType.NO_HISTORY: 0,
            InstitutionalLendingHistoryType.AT_LEAST_ONE: 1,
            InstitutionalLendingHistoryType.REPEATED_LENDING: 2,
        }
        return credit_history_scores.get(financial_details.institutional_lending_history)

    return None


def _get_systems_metric_value(row, metric):
    processes_systems = row["processes_systems"]
    if not processes_systems:
        return None

    if metric == "accounts_mis":
        accounts_mapping = {
            AccountsMISType.SOFTWARE_DIGITAL: 3,
            AccountsMISType.TALLY_NO_DIGITAL: 2,
            AccountsMISType.MS_OFFICE_TOOLS: 1,
            AccountsMISType.NO_MIS: 0,
        }
        return accounts_mapping.get(processes_systems.accounts_and_mis)

    if metric == "insurance_stock":
        insurance_mapping = {
            InsuranceStockType.HUNDRED_PERCENT_FIRE_THEFT: 3,
            InsuranceStockType.FIFTY_PERCENT_FIRE_THEFT: 2,
            InsuranceStockType.LESS_THAN_50_FIRE: 1,
            InsuranceStockType.NO_INSURANCE: 0,
        }
        return insurance_mapping.get(processes_systems.insurance_of_stock)

    if metric == "credit_record":
        credit_mapping = {
            CreditRecordType.NO_DELAYS: 3,
            CreditRecordType.ONE_DELAY: 2,
            CreditRecordType.MULTIPLE_DELAYS: 1,
            CreditRecordType.NO_CREDIT_HISTORY: 0,
        }
        return credit_mapping.get(processes_systems.credit_record_of_fpo)

    if metric == "statutory_filings":
        filings_mapping = {
            StatutoryFillingsType.NO_DELAYS: 3,
            StatutoryFillingsType.FEW_DELAYS_FILLED: 2,
            StatutoryFillingsType.MULTIPLE_DELAYS_FILLED: 1,
            StatutoryFillingsType.DELAYS_NOT_FILLED: 0,
        }
        return filings_mapping.get(processes_systems.statutory_fillings)

    if metric == "books_records":
        books_mapping = {
            BooksRecordsType.CURRENT: 3,
            BooksRecordsType.LAG_2_3_DAYS: 2,
            BooksRecordsType.WEEKLY_UPDATED: 1,
            BooksRecordsType.MONTHLY_OR_MORE: 0,
            BooksRecordsType.PROCESSES_SYSTEMS: 0,
        }
        return books_mapping.get(processes_systems.books_and_records_up_to_date)

    if metric == "stock_reconciliation":
        reconciliation_mapping = {
            ReconciliationStocksType.EVERY_15_DAYS: 3,
            ReconciliationStocksType.MONTHLY: 2,
            ReconciliationStocksType.TWO_TO_FOUR_TIMES: 1,
            ReconciliationStocksType.ABSENT_ANNUAL: 0,
        }
        return reconciliation_mapping.get(processes_systems.reconciliation_of_stocks)

    if metric == "penalties_levied":
        penalties_value = processes_systems.penalties_levied_board_meeting
        if penalties_value is None:
            return None
        return 0 if penalties_value else 1

    return None


def _get_section_score_value(row, section):
    field_name = SECTION_SCORE_FIELDS.get(section)
    if not field_name:
        return None

    value = getattr(row["submission"], field_name, None)
    return float(value) if value is not None else None


def _group_agency_chart_rows(rows):
    """Use the same count-ranked agencies for count and score charts."""
    agencies = defaultdict(list)
    for row in rows:
        agency = _get_dimension_value(row, "agency")
        if agency:
            agencies[agency].append(row)

    ranked = sorted(agencies, key=lambda name: (-len(agencies[name]), name.casefold(), name))
    groups = {name: agencies[name] for name in ranked[:5]}
    if len(ranked) > 5:
        # Do not merge a top-five agency actually named "Others" into the catch-all.
        others_label = "Others" if "Others" not in groups else "Others (combined)"
        groups[others_label] = [row for name in ranked[5:] for row in agencies[name]]
    return groups


def _build_count_chart(rows, dimension):
    if dimension == "agency":
        groups = _group_agency_chart_rows(rows)
        return {
            "categories": list(groups),
            "data": [len(group) for group in groups.values()],
            "labels": [f"{len(group)} FPOs" for group in groups.values()],
        }

    counts = defaultdict(int)
    for row in rows:
        label = _get_dimension_value(row, dimension)
        if label:
            counts[label] += 1

    categories = _ordered_labels_from_counts(counts, dimension)
    return {
        "categories": categories,
        "data": [counts[label] for label in categories],
        "labels": [f"{counts[label]} FPOs" for label in categories],
    }


def _build_average_chart(rows, dimension, value_getter):
    if dimension == "agency":
        groups = _group_agency_chart_rows(rows)
        data = []
        labels = []
        for group in groups.values():
            values = [float(value) for row in group if (value := value_getter(row)) is not None]
            # Average FPO scores, not agency averages; missing scores are not zero.
            data.append(round(sum(values) / len(values), 2) if values else None)
            labels.append(f"{len(values)} scored FPOs")
        return {"categories": list(groups), "data": data, "labels": labels}

    grouped_values = defaultdict(list)
    grouped_counts = defaultdict(int)

    for row in rows:
        label = _get_dimension_value(row, dimension)
        value = value_getter(row)
        if label and value is not None:
            grouped_values[label].append(float(value))
            grouped_counts[label] += 1

    categories = _ordered_labels_from_counts(grouped_counts, dimension)
    data = []
    labels = []
    for label in categories:
        values = grouped_values[label]
        average = sum(values) / len(values) if values else 0
        data.append(round(average, 2))
        labels.append(f"{grouped_counts[label]} FPOs")

    return {"categories": categories, "data": data, "labels": labels}


def _build_governance_focus_chart(rows, dimension, focus):
    focus_counts = defaultdict(lambda: defaultdict(int))
    dimension_counts = defaultdict(int)

    for row in rows:
        focus_label = _get_governance_focus_value(row, focus)
        dimension_label = _get_dimension_value(row, dimension)
        if not focus_label or not dimension_label:
            continue

        focus_counts[focus_label][dimension_label] += 1
        dimension_counts[dimension_label] += 1

    categories = _ordered_governance_focus_labels(focus_counts, focus)
    dimensions = _ordered_labels_from_counts(dimension_counts, dimension)
    datasets = []
    for label in dimensions:
        datasets.append(
            {
                "label": label,
                "data": [focus_counts[category].get(label, 0) for category in categories],
            }
        )

    return {
        "categories": categories,
        "datasets": datasets,
        "stacked": True,
        "labels": [str(sum(focus_counts[category].values())) for category in categories],
    }


def _build_operations_focus_chart(rows, dimension, focus):
    focus_counts = defaultdict(lambda: defaultdict(int))
    dimension_counts = defaultdict(int)

    for row in rows:
        focus_label = _get_operations_focus_value(row, focus)
        dimension_label = _get_dimension_value(row, dimension)
        if not focus_label or not dimension_label:
            continue

        focus_counts[focus_label][dimension_label] += 1
        dimension_counts[dimension_label] += 1

    categories = _ordered_operations_focus_labels(focus_counts, focus)
    dimensions = _ordered_labels_from_counts(dimension_counts, dimension)
    datasets = []
    for label in dimensions:
        datasets.append(
            {
                "label": label,
                "data": [focus_counts[category].get(label, 0) for category in categories],
            }
        )

    return {
        "categories": categories,
        "datasets": datasets,
        "stacked": True,
        "labels": [str(sum(focus_counts[category].values())) for category in categories],
    }


def _build_finance_focus_chart(rows, dimension, focus):
    focus_counts = defaultdict(lambda: defaultdict(int))
    dimension_counts = defaultdict(int)

    for row in rows:
        focus_label = _get_finance_focus_value(row, focus)
        dimension_label = _get_dimension_value(row, dimension)
        if not focus_label or not dimension_label:
            continue

        focus_counts[focus_label][dimension_label] += 1
        dimension_counts[dimension_label] += 1

    categories = _ordered_finance_focus_labels(focus_counts, focus)
    dimensions = _ordered_labels_from_counts(dimension_counts, dimension)
    datasets = []
    for label in dimensions:
        datasets.append(
            {
                "label": label,
                "data": [focus_counts[category].get(label, 0) for category in categories],
            }
        )

    return {
        "categories": categories,
        "datasets": datasets,
        "stacked": True,
        "labels": [str(sum(focus_counts[category].values())) for category in categories],
    }


def _build_systems_focus_chart(rows, dimension, focus):
    focus_counts = defaultdict(lambda: defaultdict(int))
    dimension_counts = defaultdict(int)

    for row in rows:
        focus_label = _get_systems_focus_value(row, focus)
        dimension_label = _get_dimension_value(row, dimension)
        if not focus_label or not dimension_label:
            continue

        focus_counts[focus_label][dimension_label] += 1
        dimension_counts[dimension_label] += 1

    categories = _ordered_systems_focus_labels(focus_counts, focus)
    dimensions = _ordered_labels_from_counts(dimension_counts, dimension)
    datasets = []
    for label in dimensions:
        datasets.append(
            {
                "label": label,
                "data": [focus_counts[category].get(label, 0) for category in categories],
            }
        )

    return {
        "categories": categories,
        "datasets": datasets,
        "stacked": True,
        "labels": [str(sum(focus_counts[category].values())) for category in categories],
    }


@login_required
@require_http_methods(["GET"])
def api_chart_data(request):
    """
    API endpoint to provide chart data for the reports dashboard
    """
    from django.db.models import Avg, Count
    from django.db import connection

    # Get filter parameters from request
    selected_state = request.GET.get("state", "")
    selected_promoting_agency = request.GET.get("promoting_agency", "")
    selected_score_category = request.GET.get("score_category", "")
    selected_fpo_name = request.GET.get("fpo_name", "")
    selected_financial_year = request.GET.get("financial_year", "")
    selected_start_datetime_raw = request.GET.get("start_datetime", "")
    selected_end_datetime_raw = request.GET.get("end_datetime", "")
    selected_start_datetime = _parse_report_datetime(selected_start_datetime_raw)
    selected_end_datetime = _parse_report_datetime(selected_end_datetime_raw)
    if selected_start_datetime and selected_end_datetime and selected_start_datetime > selected_end_datetime:
        selected_start_datetime, selected_end_datetime = selected_end_datetime, selected_start_datetime
    selected_report_section = _normalize_report_section(request.GET.get("report_section", "overview"))
    selected_governance_focus = _normalize_governance_focus(request.GET.get("governance_focus", "second_line_management"))
    selected_governance_metric = _normalize_governance_metric(request.GET.get("governance_metric", "governance_score"))
    selected_operations_focus = _normalize_operations_focus(request.GET.get("operations_focus", "price_volatility"))
    selected_operations_metric = _normalize_operations_metric(request.GET.get("operations_metric", "price_volatility"))
    selected_finance_focus = _normalize_finance_focus(request.GET.get("finance_focus", "net_profit"))
    selected_finance_metric = _normalize_finance_metric(request.GET.get("finance_metric", "net_profit"))
    selected_systems_focus = _normalize_systems_focus(request.GET.get("systems_focus", "accounts_mis"))
    selected_systems_metric = _normalize_systems_metric(request.GET.get("systems_metric", "accounts_mis"))
    selected_chart_tab = _normalize_chart_tab(request.GET.get("chart1_category", "size"))

    # Build base queryset for FPOs (same logic as reports_v2)
    try:
        base_fpo_queryset = FPO.objects.publicly_visible()

        # Apply filters
        if selected_state:
            base_fpo_queryset = base_fpo_queryset.filter(state=selected_state)

        if selected_fpo_name:
            base_fpo_queryset = base_fpo_queryset.filter(name=selected_fpo_name)

        # Filter by promoting agency
        if selected_promoting_agency and FPODetailsSubmission:
            try:
                fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                    promoting_agency_name__icontains=selected_promoting_agency
                ).values_list("yearly_submission__fpo_id", flat=True)
                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_agency)
            except Exception:
                pass

        # Filter by score category
        if selected_score_category:
            try:
                if selected_score_category == "achievers":  # ≥70%
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__gte=70)
                elif selected_score_category == "performers":  # 50-69%
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__gte=50, calculated_score__lt=70
                    )
                elif selected_score_category == "aspirational":  # <50%
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__isnull=False, calculated_score__lt=50
                    )
                elif selected_score_category == "blank":
                    # Show only N/A (null) scores
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=True)
                else:
                    submissions = YearlySubmission.objects.none()

                if selected_financial_year:
                    submissions = submissions.filter(financial_year=selected_financial_year)
                submissions = _apply_submission_datetime_filters(
                    submissions,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_score:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_score)
                elif selected_score_category:
                    # If a score category is selected but no FPOs match, return empty queryset
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

    except Exception:
        base_fpo_queryset = FPO.objects.none()

    # Apply financial year filter to FPO IDs
    if selected_financial_year:
        # Get FPO IDs that have submissions for the selected financial year
        fpo_ids_with_year = (
            YearlySubmission.objects.reportable().filter(financial_year=selected_financial_year)
            .values_list("fpo_id", flat=True)
            .distinct()
        )

        # Intersect with our filtered FPO queryset
        if fpo_ids_with_year:
            base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_year)
        else:
            # If no FPOs have submissions for this year, return empty set
            base_fpo_queryset = base_fpo_queryset.none()

    if selected_start_datetime or selected_end_datetime:
        date_filtered_submissions = YearlySubmission.objects.reportable()
        if selected_financial_year:
            date_filtered_submissions = date_filtered_submissions.filter(financial_year=selected_financial_year)
        date_filtered_submissions = _apply_submission_datetime_filters(
            date_filtered_submissions,
            selected_start_datetime,
            selected_end_datetime,
        )

        fpo_ids_with_date = date_filtered_submissions.values_list("fpo_id", flat=True).distinct()
        if fpo_ids_with_date:
            base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_date)
        else:
            base_fpo_queryset = base_fpo_queryset.none()

    filtered_fpo_ids = list(base_fpo_queryset.values_list("id", flat=True))
    report_rows = _build_latest_report_rows(
        filtered_fpo_ids,
        selected_financial_year,
        selected_start_datetime,
        selected_end_datetime,
    )

    chart1_data = {}
    chart2_data = {}

    if selected_report_section == "governance":
        chart1_data[selected_chart_tab] = _build_governance_focus_chart(
            report_rows,
            selected_chart_tab,
            selected_governance_focus,
        )
    elif selected_report_section == "operations":
        chart1_data[selected_chart_tab] = _build_operations_focus_chart(
            report_rows,
            selected_chart_tab,
            selected_operations_focus,
        )
    elif selected_report_section == "finance":
        chart1_data[selected_chart_tab] = _build_finance_focus_chart(
            report_rows,
            selected_chart_tab,
            selected_finance_focus,
        )
    elif selected_report_section == "systems":
        chart1_data[selected_chart_tab] = _build_systems_focus_chart(
            report_rows,
            selected_chart_tab,
            selected_systems_focus,
        )
    else:
        chart1_data[selected_chart_tab] = _build_count_chart(report_rows, selected_chart_tab)

    chart2_data["final"] = _build_average_chart(
        report_rows,
        selected_chart_tab,
        lambda row: _get_section_score_value(row, "overview"),
    )
    chart2_data["governance"] = _build_average_chart(
        report_rows,
        selected_chart_tab,
        lambda row: _get_governance_metric_value(row, selected_governance_metric)
        if selected_report_section == "governance"
        else _get_section_score_value(row, "governance"),
    )
    chart2_data["operations"] = _build_average_chart(
        report_rows,
        selected_chart_tab,
        lambda row: _get_operations_metric_value(row, selected_operations_metric)
        if selected_report_section == "operations"
        else _get_section_score_value(row, "operations"),
    )
    chart2_data["systems"] = _build_average_chart(
        report_rows,
        selected_chart_tab,
        lambda row: _get_systems_metric_value(row, selected_systems_metric)
        if selected_report_section == "systems"
        else _get_section_score_value(row, "systems"),
    )
    chart2_data["finance"] = _build_average_chart(
        report_rows,
        selected_chart_tab,
        lambda row: _get_finance_metric_value(row, selected_finance_metric)
        if selected_report_section == "finance"
        else _get_section_score_value(row, "finance"),
    )

    # Trend data: Year-over-year average scores
    trend_data = {"years": [], "avg_score": [], "governance": [], "operations": [], "systems": [], "financial": []}
    try:
        trend_base_query = YearlySubmission.objects.reportable().filter(
            fpo_id__in=filtered_fpo_ids,
            calculated_score__isnull=False,
        )
        trend_base_query = _apply_submission_datetime_filters(
            trend_base_query,
            selected_start_datetime,
            selected_end_datetime,
        )

        trend_query = (
            trend_base_query
            .values("financial_year")
            .annotate(
                avg_total=Avg("calculated_score"),
                avg_governance=Avg("governance_score"),
                avg_operations=Avg("business_score"),
                avg_systems=Avg("process_score"),
                avg_financial=Avg("financial_score"),
                fpo_count=Count("fpo_id", distinct=True),
            )
            .order_by("financial_year")
        )

        for item in trend_query:
            trend_data["years"].append(item["financial_year"])
            trend_data["avg_score"].append(round(float(item["avg_total"] or 0), 1))
            trend_data["governance"].append(round(float(item["avg_governance"] or 0), 1))
            trend_data["operations"].append(round(float(item["avg_operations"] or 0), 1))
            trend_data["systems"].append(round(float(item["avg_systems"] or 0), 1))
            trend_data["financial"].append(round(float(item["avg_financial"] or 0), 1))
    except Exception:
        pass

    response_data = {
        "success": True,
        "chart1": chart1_data,
        "chart2": chart2_data,
        "trend": trend_data,
        "filters": {
            "state": selected_state,
            "promoting_agency": selected_promoting_agency,
            "score_category": selected_score_category,
            "fpo_name": selected_fpo_name,
            "financial_year": selected_financial_year,
            "start_datetime": selected_start_datetime_raw,
            "end_datetime": selected_end_datetime_raw,
            "report_section": selected_report_section,
            "chart1_category": selected_chart_tab,
            "governance_focus": selected_governance_focus,
            "governance_metric": selected_governance_metric,
            "operations_focus": selected_operations_focus,
            "operations_metric": selected_operations_metric,
            "finance_focus": selected_finance_focus,
            "finance_metric": selected_finance_metric,
            "systems_focus": selected_systems_focus,
            "systems_metric": selected_systems_metric,
        },
    }

    return JsonResponse(response_data)


@login_required
@require_http_methods(["GET"])
def api_stats_data(request):
    """
    API endpoint to provide filtered statistics data for the reports dashboard
    """
    from django.db.models import Count, Avg, Q, Case, When, Value, IntegerField
    from django.db import connection
    import json

    # Get filter parameters from request
    selected_state = request.GET.get("state", "")
    selected_promoting_agency = request.GET.get("promoting_agency", "")
    selected_score_category = request.GET.get("score_category", "")
    selected_fpo_name = request.GET.get("fpo_name", "")
    selected_financial_year = request.GET.get("financial_year", "")
    selected_start_datetime_raw = request.GET.get("start_datetime", "")
    selected_end_datetime_raw = request.GET.get("end_datetime", "")
    selected_start_datetime = _parse_report_datetime(selected_start_datetime_raw)
    selected_end_datetime = _parse_report_datetime(selected_end_datetime_raw)
    if selected_start_datetime and selected_end_datetime and selected_start_datetime > selected_end_datetime:
        selected_start_datetime, selected_end_datetime = selected_end_datetime, selected_start_datetime
    selected_report_section = _normalize_report_section(request.GET.get("report_section", "overview"))
    selected_governance_focus = _normalize_governance_focus(request.GET.get("governance_focus", "second_line_management"))
    selected_governance_metric = _normalize_governance_metric(request.GET.get("governance_metric", "governance_score"))

    # Build base queryset for FPOs
    try:
        base_fpo_queryset = FPO.objects.publicly_visible()

        # Apply filters
        if selected_state:
            base_fpo_queryset = base_fpo_queryset.filter(state=selected_state)

        if selected_fpo_name:
            base_fpo_queryset = base_fpo_queryset.filter(name__icontains=selected_fpo_name)

        # Filter by promoting agency (requires FPODetailsSubmission)
        if selected_promoting_agency and FPODetailsSubmission:
            try:
                fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                    promoting_agency_name__icontains=selected_promoting_agency
                ).values_list("yearly_submission__fpo_id", flat=True)
                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_agency)
            except Exception:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                        if cursor.fetchone():
                            cursor.execute(
                                "SELECT DISTINCT fpo_id FROM fpo_basicdetails WHERE promoting_agency_name LIKE %s",
                                [f"%{selected_promoting_agency}%"],
                            )
                            fpo_ids = [row[0] for row in cursor.fetchall()]
                            if fpo_ids:
                                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids)
                except Exception:
                    pass

        # Filter by financial year (requires YearlySubmission)
        if selected_financial_year:
            try:
                fpo_ids_with_year = (
                    YearlySubmission.objects.reportable().filter(financial_year=selected_financial_year)
                    .values_list("fpo_id", flat=True)
                    .distinct()
                )

                if fpo_ids_with_year:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_year)
                else:
                    # If no FPOs have submissions for this year, return empty set
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

        if selected_start_datetime or selected_end_datetime:
            try:
                submissions_with_date = YearlySubmission.objects.reportable()
                if selected_financial_year:
                    submissions_with_date = submissions_with_date.filter(financial_year=selected_financial_year)
                submissions_with_date = _apply_submission_datetime_filters(
                    submissions_with_date,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_date = submissions_with_date.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_date:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_date)
                else:
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

        # Filter by score category (requires YearlySubmission)
        if selected_score_category:
            try:
                if selected_score_category == "achievers":
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__gte=70)
                elif selected_score_category == "performers":
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__gte=50, calculated_score__lt=70
                    )
                elif selected_score_category == "aspirational":
                    # Show only scores < 50 (exclude N/A)
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__isnull=False, calculated_score__lt=50
                    )
                elif selected_score_category == "blank":
                    # Show only N/A (null) scores
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=True)
                else:
                    submissions = YearlySubmission.objects.none()

                # Apply financial year filter to submissions if needed
                if selected_financial_year:
                    submissions = submissions.filter(financial_year=selected_financial_year)
                submissions = _apply_submission_datetime_filters(
                    submissions,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
                print("123333==================", fpo_ids_with_score, selected_score_category, submissions)

                if fpo_ids_with_score:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_score)
                elif selected_score_category:
                    # If a score category is selected but no FPOs match, return empty queryset
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

    except Exception:
        base_fpo_queryset = FPO.objects.none()

    # Get filtered FPO IDs for use in calculations
    filtered_fpo_ids = list(base_fpo_queryset.values_list("id", flat=True))

    # Calculate statistics (filtered)
    try:
        total_fpos = base_fpo_queryset.count()
        # Get actual name lists for tooltip updates
        state_names = list(base_fpo_queryset.values_list("state", flat=True).distinct().order_by("state"))
        district_names = list(base_fpo_queryset.values_list("district", flat=True).distinct().order_by("district"))
        unique_states = len(state_names)
        unique_districts = len(district_names)
    except Exception:
        total_fpos = 0
        unique_states = 0
        unique_districts = 0
        state_names = []
        district_names = []

    # Calculate total promoting agencies (filtered)
    promoting_agency_names = []
    try:
        total_promoting_agencies = 0
        if FPODetailsSubmission and filtered_fpo_ids:
            # Build query to count promoting agencies
            agency_query = FPODetailsSubmission.objects.filter(
                yearly_submission__fpo_id__in=filtered_fpo_ids, promoting_agency_name__isnull=False
            )

            # If a specific promoting agency is selected, filter by it
            if selected_promoting_agency:
                agency_query = agency_query.filter(promoting_agency_name__icontains=selected_promoting_agency)

            promoting_agency_names = list(
                agency_query
                .values_list("promoting_agency_name", flat=True)
                .distinct()
                .order_by("promoting_agency_name")
            )
            total_promoting_agencies = len(promoting_agency_names)
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                if cursor.fetchone() and filtered_fpo_ids:
                    fpo_ids_str = ",".join(map(str, filtered_fpo_ids))

                    # If a specific promoting agency is selected, filter by it
                    if selected_promoting_agency:
                        cursor.execute(
                            f"SELECT COUNT(DISTINCT promoting_agency_name) FROM fpo_basicdetails WHERE fpo_id IN ({fpo_ids_str}) AND promoting_agency_name IS NOT NULL AND promoting_agency_name LIKE %s",
                            [f"%{selected_promoting_agency}%"]
                        )
                    else:
                        cursor.execute(
                            f"SELECT COUNT(DISTINCT promoting_agency_name) FROM fpo_basicdetails WHERE fpo_id IN ({fpo_ids_str}) AND promoting_agency_name IS NOT NULL"
                        )
                    result = cursor.fetchone()
                    total_promoting_agencies = result[0] if result else 0
    except Exception:
        total_promoting_agencies = 0

    # Calculate average score from yearly submissions (filtered)
    try:
        # Build base query for score calculations
        score_query = YearlySubmission.objects.reportable().filter(
            fpo_id__in=filtered_fpo_ids,
            calculated_score__isnull=False,
        )

        # If financial year is selected, also filter scores by year
        if selected_financial_year:
            score_query = score_query.filter(financial_year=selected_financial_year)
        score_query = _apply_submission_datetime_filters(
            score_query,
            selected_start_datetime,
            selected_end_datetime,
        )

        avg_score = score_query.aggregate(avg_score=Avg("calculated_score"))["avg_score"]
        avg_score = float(avg_score) if avg_score else 0

        # Calculate average scores for each category
        avg_total_score = round(avg_score, 1) if avg_score else 0
        avg_governance_score = score_query.filter(governance_score__isnull=False).aggregate(
            avg_score=Avg("governance_score")
        )["avg_score"]
        avg_governance_score = round(float(avg_governance_score), 1) if avg_governance_score else 0

        avg_operations_score = score_query.filter(business_score__isnull=False).aggregate(
            avg_score=Avg("business_score")
        )["avg_score"]
        avg_operations_score = round(float(avg_operations_score), 1) if avg_operations_score else 0

        avg_systems_score = score_query.filter(process_score__isnull=False).aggregate(avg_score=Avg("process_score"))[
            "avg_score"
        ]
        avg_systems_score = round(float(avg_systems_score), 1) if avg_systems_score else 0

        avg_financial_score = score_query.filter(financial_score__isnull=False).aggregate(
            avg_score=Avg("financial_score")
        )["avg_score"]
        avg_financial_score = round(float(avg_financial_score), 1) if avg_financial_score else 0

    except Exception:
        avg_score = 0
        avg_total_score = 0
        avg_governance_score = 0
        avg_operations_score = 0
        avg_systems_score = 0
        avg_financial_score = 0

    # Build response data
    stats_data = {
        "success": True,
        "stats": {
            "total_fpos_count": total_fpos,
            "total_promoting_agencies": total_promoting_agencies,
            "total_states_count": unique_states,
            "total_districts_count": unique_districts,
            "avg_total_score": avg_total_score,
            "avg_governance_score": avg_governance_score,
            "avg_operations_score": avg_operations_score,
            "avg_systems_score": avg_systems_score,
            "avg_financial_score": avg_financial_score,
            "average_score": avg_total_score,
            # Name lists for tooltip updates
            "state_names": state_names,
            "district_names": district_names,
            "promoting_agency_names": promoting_agency_names,
        },
        "filters_applied": {
            "state": selected_state,
            "promoting_agency": selected_promoting_agency,
            "score_category": selected_score_category,
            "financial_year": selected_financial_year,
            "start_datetime": selected_start_datetime_raw,
            "end_datetime": selected_end_datetime_raw,
        },
    }

    return JsonResponse(stats_data)


@login_required
@require_http_methods(["GET"])
def api_fpo_table_data(request):
    """
    API endpoint to provide filtered FPOs data for the FPOs table
    """
    from django.db.models import Q
    from django.db import connection
    import json

    # Get filter parameters from request
    selected_state = request.GET.get("state", "")
    selected_promoting_agency = request.GET.get("promoting_agency", "")
    selected_score_category = request.GET.get("score_category", "")
    selected_fpo_name = request.GET.get("fpo_name", "")
    selected_financial_year = request.GET.get("financial_year", "")
    selected_start_datetime_raw = request.GET.get("start_datetime", "")
    selected_end_datetime_raw = request.GET.get("end_datetime", "")
    selected_start_datetime = _parse_report_datetime(selected_start_datetime_raw)
    selected_end_datetime = _parse_report_datetime(selected_end_datetime_raw)
    if selected_start_datetime and selected_end_datetime and selected_start_datetime > selected_end_datetime:
        selected_start_datetime, selected_end_datetime = selected_end_datetime, selected_start_datetime
    search_term = request.GET.get("search", "")

    # Pagination parameters
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 10))  # Fixed to 10 records per page
    offset = (page - 1) * page_size

    # Build base queryset for FPOs
    try:
        base_fpo_queryset = FPO.objects.publicly_visible()

        # Apply filters
        if selected_state:
            base_fpo_queryset = base_fpo_queryset.filter(state=selected_state)

        if selected_fpo_name:
            base_fpo_queryset = base_fpo_queryset.filter(name__icontains=selected_fpo_name)

        # Apply search term to FPO name
        if search_term:
            base_fpo_queryset = base_fpo_queryset.filter(name__icontains=search_term)

        # Filter by promoting agency (requires FPODetailsSubmission)
        if selected_promoting_agency and FPODetailsSubmission:
            try:
                fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                    promoting_agency_name__icontains=selected_promoting_agency
                ).values_list("yearly_submission__fpo_id", flat=True)
                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_agency)
            except Exception:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                        if cursor.fetchone():
                            cursor.execute(
                                "SELECT DISTINCT fpo_id FROM fpo_basicdetails WHERE promoting_agency_name LIKE %s",
                                [f"%{selected_promoting_agency}%"],
                            )
                            fpo_ids = [row[0] for row in cursor.fetchall()]
                            if fpo_ids:
                                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids)
                except Exception:
                    pass

        # Filter by financial year (requires YearlySubmission)
        if selected_financial_year:
            try:
                fpo_ids_with_year = (
                    YearlySubmission.objects.reportable().filter(financial_year=selected_financial_year)
                    .values_list("fpo_id", flat=True)
                    .distinct()
                )

                if fpo_ids_with_year:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_year)
                else:
                    # If no FPOs have submissions for this year, return empty set
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

        if selected_start_datetime or selected_end_datetime:
            try:
                submissions_with_date = YearlySubmission.objects.reportable()
                if selected_financial_year:
                    submissions_with_date = submissions_with_date.filter(financial_year=selected_financial_year)
                submissions_with_date = _apply_submission_datetime_filters(
                    submissions_with_date,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_date = submissions_with_date.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_date:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_date)
                else:
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

        # Filter by score category (requires YearlySubmission)
        if selected_score_category:
            try:
                if selected_score_category == "achievers":
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__gte=70)
                elif selected_score_category == "performers":
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__gte=50, calculated_score__lt=70
                    )
                elif selected_score_category == "aspirational":
                    # Show only scores < 50 (exclude N/A)
                    submissions = YearlySubmission.objects.reportable().filter(
                        calculated_score__isnull=False, calculated_score__lt=50
                    )
                elif selected_score_category == "blank":
                    # Show only N/A (null) scores
                    submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=True)
                else:
                    submissions = YearlySubmission.objects.none()

                # Apply financial year filter to submissions if needed
                if selected_financial_year:
                    submissions = submissions.filter(financial_year=selected_financial_year)
                submissions = _apply_submission_datetime_filters(
                    submissions,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_score:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_score)
                elif selected_score_category:
                    # If a score category is selected but no FPOs match, return empty queryset
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass

    except Exception:
        base_fpo_queryset = FPO.objects.none()

    # Get total count for pagination
    total_count = base_fpo_queryset.count()

    # Apply pagination
    paginated_queryset = base_fpo_queryset[offset : offset + page_size]

    # Get FPO data with scores and promoting agencies
    fpos_data = []

    try:
        for fpo in paginated_queryset:
            # Get latest submission data
            latest_submission = None
            final_score = None

            try:
                # Try to get the most recent yearly submission
                submission_query = YearlySubmission.objects.reportable().filter(fpo_id=fpo.id)
                if selected_financial_year:
                    submission_query = submission_query.filter(financial_year=selected_financial_year)
                submission_query = _apply_submission_datetime_filters(
                    submission_query,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                # Get the most recent submission with valid scores (prefer non-zero scores over empty recent ones)
                submissions = list(submission_query.order_by("-financial_year"))
                latest_submission = None

                # First try to find a submission with non-zero calculated score
                for sub in submissions:
                    if sub.calculated_score is not None and sub.calculated_score > 0:
                        latest_submission = sub
                        break

                # If no submission with non-zero calculated score, use the most recent one
                if not latest_submission and submissions:
                    latest_submission = submissions[0]

                if latest_submission and latest_submission.calculated_score is not None:
                    final_score = float(latest_submission.calculated_score)
                elif latest_submission and selected_score_category != "blank":
                    # For blank option, keep final_score as None
                    # Try using governance_score as fallback if calculated_score is null
                    if (
                        hasattr(latest_submission, "governance_score")
                        and latest_submission.governance_score is not None
                    ):
                        final_score = float(latest_submission.governance_score)
                    elif hasattr(latest_submission, "final_score") and latest_submission.final_score is not None:
                        final_score = float(latest_submission.final_score)
                    else:
                        # Try to calculate from available score fields
                        score_fields = ["governance_score", "business_score", "process_score", "financial_score"]
                        scores = []
                        for field in score_fields:
                            if hasattr(latest_submission, field) and getattr(latest_submission, field) is not None:
                                try:
                                    scores.append(float(getattr(latest_submission, field)))
                                except (ValueError, TypeError):
                                    pass
                        if scores:
                            final_score = sum(scores) / len(scores)
            except Exception as e:
                print(f"Error getting score for FPO {fpo.id}: {e}")
                pass

            # Get promoting agency
            promoting_agency = ""
            try:
                if FPODetailsSubmission:
                    # Build query to get promoting agency
                    agency_query = FPODetailsSubmission.objects.filter(yearly_submission__fpo_id=fpo.id)

                    # If a specific promoting agency is selected, filter by it
                    if selected_promoting_agency:
                        agency_query = agency_query.filter(promoting_agency_name__icontains=selected_promoting_agency)

                    # If financial year is selected, also filter by that
                    if selected_financial_year:
                        agency_query = agency_query.filter(yearly_submission__financial_year=selected_financial_year)

                    agency_submission = agency_query.first()
                    if agency_submission and agency_submission.promoting_agency_name:
                        promoting_agency = agency_submission.promoting_agency_name
                else:
                    # Fallback to raw SQL query
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                        if cursor.fetchone():
                            # Build SQL query with optional filter
                            if selected_promoting_agency:
                                cursor.execute(
                                    "SELECT promoting_agency_name FROM fpo_basicdetails WHERE fpo_id = %s AND promoting_agency_name LIKE %s LIMIT 1",
                                    [fpo.id, f"%{selected_promoting_agency}%"]
                                )
                            else:
                                cursor.execute(
                                    "SELECT promoting_agency_name FROM fpo_basicdetails WHERE fpo_id = %s LIMIT 1", [fpo.id]
                                )
                            result = cursor.fetchone()
                            if result and result[0]:
                                promoting_agency = result[0]
            except Exception:
                pass

            # Get individual scores
            governance_score = None
            operations_score = None
            systems_score = None
            finance_score = None
            age = None

            if latest_submission:
                governance_score = (
                    float(latest_submission.governance_score)
                    if latest_submission.governance_score is not None
                    else None
                )
                operations_score = (
                    float(latest_submission.business_score) if latest_submission.business_score is not None else None
                )
                systems_score = (
                    float(latest_submission.process_score) if latest_submission.process_score is not None else None
                )
                finance_score = (
                    float(latest_submission.financial_score) if latest_submission.financial_score is not None else None
                )

            # Get FPO age from FPODetailsSubmission
            try:
                if FPODetailsSubmission:
                    fpo_details = FPODetailsSubmission.objects.filter(yearly_submission__fpo_id=fpo.id).first()
                    if fpo_details and fpo_details.age_of_fpo_years:
                        age = float(fpo_details.age_of_fpo_years)
            except Exception:
                pass

            fpos_data.append(
                {
                    "id": fpo.id,
                    "fpo_name": fpo.name,
                    "promoting_agency": promoting_agency,
                    "final_score": final_score,
                    "governance_score": governance_score,
                    "operations_score": operations_score,
                    "systems_score": systems_score,
                    "finance_score": finance_score,
                    "age": age,
                    "state": fpo.state,
                    "district": fpo.district,
                }
            )

        # Sort by final score (descending) if available, then by name
        fpos_data.sort(key=lambda x: (-(x["final_score"] or 0), x["fpo_name"]))

    except Exception as e:
        # Return error data if something goes wrong
        fpos_data = []

    # Calculate pagination info
    total_pages = (total_count + page_size - 1) // page_size
    has_next = page < total_pages
    has_prev = page > 1

    response_data = {
        "success": True,
        "fpos": fpos_data,
        "count": len(fpos_data),
        "total_count": total_count,
        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_count": total_count,
            "has_next": has_next,
            "has_prev": has_prev,
            "next_page": page + 1 if has_next else None,
            "prev_page": page - 1 if has_prev else None,
        },
        "filters": {
            "state": selected_state,
            "promoting_agency": selected_promoting_agency,
            "score_category": selected_score_category,
            "financial_year": selected_financial_year,
            "start_datetime": selected_start_datetime_raw,
            "end_datetime": selected_end_datetime_raw,
            "search": search_term,
        },
    }

    return JsonResponse(response_data)


@login_required
def recalculate_scores(request, pk):
    """
    View to recalculate scores for all yearly submissions of an FPO
    """
    fpo = get_object_or_404(FPO, pk=pk)
    _require_fpo_admin(request, fpo)

    # Get all yearly submissions for this FPO
    submissions = fpo.yearly_submissions.all()

    recalculated_count = 0
    for submission in submissions:
        try:
            # Simply save the submission, which triggers the score calculation
            submission.save()
            recalculated_count += 1
        except Exception as e:
            messages.warning(request, f"Error recalculating scores for {submission.financial_year}: {str(e)}")

    if recalculated_count > 0:
        messages.success(request, f"Successfully recalculated scores for {recalculated_count} submission(s).")
    else:
        messages.info(request, "No submissions were recalculated.")

    return redirect("fpo:fpo_detail", pk=pk)


@login_required
def reports_v2(request):
    """
    Enhanced reports view with statistical dashboards, charts, and tables
    """
    from django.db.models import Count, Avg, Q, Case, When, Value, IntegerField
    from django.db import connection

    # Get filter parameters
    selected_state = request.GET.get("state", "")
    selected_promoting_agency = request.GET.get("promoting_agency", "")
    selected_score_category = request.GET.get("score_category", "")
    selected_fpo_name = request.GET.get("fpo_name", "")
    selected_financial_year = request.GET.get("financial_year", "")
    selected_start_datetime_raw = request.GET.get("start_datetime", "")
    selected_end_datetime_raw = request.GET.get("end_datetime", "")
    selected_start_datetime = _parse_report_datetime(selected_start_datetime_raw)
    selected_end_datetime = _parse_report_datetime(selected_end_datetime_raw)
    if selected_start_datetime and selected_end_datetime and selected_start_datetime > selected_end_datetime:
        selected_start_datetime, selected_end_datetime = selected_end_datetime, selected_start_datetime
    selected_report_section = _normalize_report_section(request.GET.get("report_section", "overview"))
    selected_governance_focus = _normalize_governance_focus(request.GET.get("governance_focus", "second_line_management"))
    selected_governance_metric = _normalize_governance_metric(request.GET.get("governance_metric", "governance_score"))
    selected_operations_focus = _normalize_operations_focus(request.GET.get("operations_focus", "price_volatility"))
    selected_operations_metric = _normalize_operations_metric(request.GET.get("operations_metric", "price_volatility"))
    selected_finance_focus = _normalize_finance_focus(request.GET.get("finance_focus", "net_profit"))
    selected_finance_metric = _normalize_finance_metric(request.GET.get("finance_metric", "net_profit"))
    selected_systems_focus = _normalize_systems_focus(request.GET.get("systems_focus", "accounts_mis"))
    selected_systems_metric = _normalize_systems_metric(request.GET.get("systems_metric", "accounts_mis"))

    # Build base queryset for FPOs
    try:
        base_fpo_queryset = FPO.objects.publicly_visible()

        # Apply filters
        if selected_state:
            base_fpo_queryset = base_fpo_queryset.filter(state=selected_state)

        if selected_fpo_name:
            base_fpo_queryset = base_fpo_queryset.filter(name=selected_fpo_name)

        # Filter by promoting agency (requires FPODetailsSubmission)
        if selected_promoting_agency and FPODetailsSubmission:
            try:
                fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                    promoting_agency_name__icontains=selected_promoting_agency
                ).values_list("yearly_submission__fpo_id", flat=True)
                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_agency)
            except Exception:
                # Try alternative table if available
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                        if cursor.fetchone():
                            cursor.execute(
                                "SELECT DISTINCT fpo_id FROM fpo_basicdetails WHERE promoting_agency_name LIKE %s",
                                [f"%{selected_promoting_agency}%"],
                            )
                            fpo_ids = [row[0] for row in cursor.fetchall()]
                            if fpo_ids:
                                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids)
                except Exception:
                    pass  # Ignore if no alternative table

        # Filter by financial year (requires YearlySubmission)
        if selected_financial_year:
            try:
                # Parse financial year string like "2023-24" to get year range
                if "-" in selected_financial_year:
                    year_part = selected_financial_year.split("-")[0]
                    try:
                        year_int = int(year_part)
                        submissions = YearlySubmission.objects.reportable().filter(
                            financial_year=selected_financial_year
                        )
                        fpo_ids_with_year = submissions.values_list("fpo_id", flat=True).distinct()
                        if fpo_ids_with_year:
                            base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_year)
                    except ValueError:
                        pass  # Invalid year format
            except Exception:
                pass  # Ignore if no year data

        if selected_start_datetime or selected_end_datetime:
            try:
                submissions_with_date = YearlySubmission.objects.reportable()
                if selected_financial_year:
                    submissions_with_date = submissions_with_date.filter(financial_year=selected_financial_year)
                submissions_with_date = _apply_submission_datetime_filters(
                    submissions_with_date,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                fpo_ids_with_date = submissions_with_date.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_date:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_date)
                else:
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass  # Ignore date filter errors
        # Filter by score category (requires YearlySubmission)

        if selected_score_category:
            try:
                submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)
                if selected_financial_year and "-" in selected_financial_year:
                    # If financial year is selected, also filter scores by year
                    year_part = selected_financial_year.split("-")[0]
                    try:
                        year_int = int(year_part)
                        submissions = submissions.filter(financial_year=selected_financial_year)
                    except ValueError:
                        pass

                submissions = _apply_submission_datetime_filters(
                    submissions,
                    selected_start_datetime,
                    selected_end_datetime,
                )

                if selected_score_category == "achievers":  # ≥70%
                    submissions = submissions.filter(calculated_score__gte=70)
                elif selected_score_category == "performers":  # 50-69%
                    submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
                elif selected_score_category == "aspirational":  # <50%
                    submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
                elif selected_score_category == "blank":
                    # Show only N/A (null) scores
                    submissions = submissions.filter(calculated_score__isnull=True)

                fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
                if fpo_ids_with_score:
                    base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_score)
                elif selected_score_category:
                    # If a score category is selected but no FPOs match, return empty queryset
                    base_fpo_queryset = base_fpo_queryset.none()
            except Exception:
                pass  # Ignore if no score data

    except Exception:
        # Fallback to empty queryset if FPO table has issues
        base_fpo_queryset = FPO.objects.none()

    # Get filtered FPO IDs for use in calculations
    filtered_fpo_ids = list(base_fpo_queryset.values_list("id", flat=True))

    # Basic statistics (filtered)
    try:
        total_fpos = base_fpo_queryset.count()
        unique_states = base_fpo_queryset.values("state").distinct().count()
        unique_districts = base_fpo_queryset.values("district").distinct().count()
        # Get actual state and district names for tooltip display
        state_names_list = list(
            base_fpo_queryset.values_list("state", flat=True).distinct().order_by("state")
        )
        district_names_list = list(
            base_fpo_queryset.values_list("district", flat=True).distinct().order_by("district")
        )
    except Exception:
        total_fpos = 0
        unique_states = 0
        unique_districts = 0
        state_names_list = []
        district_names_list = []

    # Calculate total promoting agencies (filtered)
    promoting_agency_names_list = []
    try:
        total_promoting_agencies = 0
        if FPODetailsSubmission and filtered_fpo_ids:
            promoting_agency_qs = (
                FPODetailsSubmission.objects.filter(
                    yearly_submission__fpo_id__in=filtered_fpo_ids, promoting_agency_name__isnull=False
                )
                .exclude(promoting_agency_name="")
                .values_list("promoting_agency_name", flat=True)
                .distinct()
                .order_by("promoting_agency_name")
            )
            promoting_agency_names_list = list(promoting_agency_qs)
            total_promoting_agencies = len(promoting_agency_names_list)
        else:
            # Fallback: try to use raw SQL query
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                if cursor.fetchone() and filtered_fpo_ids:
                    fpo_ids_str = ",".join(map(str, filtered_fpo_ids))
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT promoting_agency_name) FROM fpo_basicdetails WHERE fpo_id IN ({fpo_ids_str}) AND promoting_agency_name IS NOT NULL"
                    )
                    result = cursor.fetchone()
                    total_promoting_agencies = result[0] if result else 0
    except Exception:
        total_promoting_agencies = 0

    # Calculate average score from yearly submissions (filtered)
    try:
        # Build base query for score calculations
        score_query = YearlySubmission.objects.reportable().filter(
            fpo_id__in=filtered_fpo_ids,
            calculated_score__isnull=False,
        )

        # If financial year is selected, also filter scores by year
        if selected_financial_year:
            score_query = score_query.filter(financial_year=selected_financial_year)
        score_query = _apply_submission_datetime_filters(
            score_query,
            selected_start_datetime,
            selected_end_datetime,
        )

        avg_score = score_query.aggregate(avg_score=Avg("calculated_score"))["avg_score"]
        avg_score = float(avg_score) if avg_score else 0

        # Calculate average scores for each category
        avg_total_score = round(avg_score, 1) if avg_score else 0
        avg_governance_score = score_query.filter(governance_score__isnull=False).aggregate(
            avg_score=Avg("governance_score")
        )["avg_score"]
        avg_governance_score = round(float(avg_governance_score), 1) if avg_governance_score else 0

        avg_operations_score = score_query.filter(business_score__isnull=False).aggregate(
            avg_score=Avg("business_score")
        )["avg_score"]
        avg_operations_score = round(float(avg_operations_score), 1) if avg_operations_score else 0

        avg_systems_score = score_query.filter(process_score__isnull=False).aggregate(avg_score=Avg("process_score"))[
            "avg_score"
        ]
        avg_systems_score = round(float(avg_systems_score), 1) if avg_systems_score else 0

        avg_financial_score = score_query.filter(financial_score__isnull=False).aggregate(
            avg_score=Avg("financial_score")
        )["avg_score"]
        avg_financial_score = round(float(avg_financial_score), 1) if avg_financial_score else 0

    except Exception:
        filtered_fpo_ids = []
        avg_score = 0
        avg_total_score = 0
        avg_governance_score = 0
        avg_operations_score = 0
        avg_systems_score = 0
        avg_financial_score = 0

    # FPO size classification (filtered) - handle missing tables gracefully
    small_fpos = 0
    large_fpos = 0

    try:
        # Try to use FPODetailsSubmission first
        if FPODetailsSubmission:
            fpo_details_with_size = FPODetailsSubmission.objects.filter(
                size_of_fpo_fy_23_24__isnull=False, yearly_submission__fpo_id__in=filtered_fpo_ids
            ).select_related("yearly_submission__fpo")

            small_fpos = fpo_details_with_size.filter(size_of_fpo_fy_23_24__lte=1000).count()
            large_fpos = fpo_details_with_size.filter(size_of_fpo_fy_23_24__gt=1000).count()
        else:
            raise Exception("FPODetailsSubmission model not available")
    except Exception:
        # Fallback: check if we have basic details or use dummy data
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                if cursor.fetchone():
                    fpo_ids_str = ",".join(map(str, filtered_fpo_ids)) if filtered_fpo_ids else "0"
                    cursor.execute(
                        f"SELECT COUNT(*) FROM fpo_basicdetails WHERE fpo_id IN ({fpo_ids_str}) AND size_of_fpo_fy_23_24 IS NOT NULL AND size_of_fpo_fy_23_24 <= 1000"
                    )
                    small_fpos = cursor.fetchone()[0] if cursor.fetchone() else 0
                    cursor.execute(
                        f"SELECT COUNT(*) FROM fpo_basicdetails WHERE fpo_id IN ({fpo_ids_str}) AND size_of_fpo_fy_23_24 IS NOT NULL AND size_of_fpo_fy_23_24 > 1000"
                    )
                    large_fpos = cursor.fetchone()[0] if cursor.fetchone() else 0
                else:
                    # Use dummy data based on total FPOs for demo purposes
                    small_fpos = int(total_fpos * 0.7)  # 70% small FPOs
                    large_fpos = int(total_fpos * 0.3)  # 30% large FPOs
        except Exception:
            # Final fallback: dummy data
            small_fpos = int(total_fpos * 0.7) if total_fpos > 0 else 2
            large_fpos = int(total_fpos * 0.3) if total_fpos > 0 else 1

    # State-wise data for table (filtered)
    try:
        state_data = list(
            base_fpo_queryset.values("state")
            .annotate(fpo_count=Count("id"), districts=Count("district", distinct=True))
            .order_by("-fpo_count")
        )
    except Exception:
        state_data = []

    # FPO table removed - no longer needed for reports page

    # Get filter options for dropdowns
    try:
        all_states = list(
            FPO.objects.publicly_visible().values_list("state", flat=True).distinct().order_by("state")
        )
    except Exception:
        all_states = []

    # Get promoting agencies from FPODetailsSubmission if available
    promoting_agencies = []
    try:
        if FPODetailsSubmission:
            promoting_agencies = list(
                FPODetailsSubmission.objects.filter(
                    yearly_submission__fpo__in=FPO.objects.publicly_visible(),
                    promoting_agency_name__isnull=False,
                )
                .exclude(promoting_agency_name="")
                .values_list("promoting_agency_name", flat=True)
                .distinct()
                .order_by("promoting_agency_name")
            )
        else:
            raise Exception("FPODetailsSubmission model not available")
    except Exception:
        # If FPODetailsSubmission doesn't exist, try to get from basic details table
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                if cursor.fetchone():
                    cursor.execute(
                        "SELECT DISTINCT promoting_agency_name FROM fpo_basicdetails WHERE promoting_agency_name IS NOT NULL AND promoting_agency_name != '' ORDER BY promoting_agency_name"
                    )
                    promoting_agencies = [row[0] for row in cursor.fetchall()]
        except Exception:
            promoting_agencies = []

    # Get FPO names for autocomplete
    try:
        all_fpo_names = list(FPO.objects.publicly_visible().values_list("name", flat=True).order_by("name"))
    except Exception:
        all_fpo_names = []

    # Get financial years for filter dropdown
    try:
        financial_years = list(
            YearlySubmission.objects.reportable()
            .values_list("financial_year", flat=True)
            .distinct()
            .order_by("-financial_year")
        )
    except Exception:
        financial_years = []

    # Score categories
    score_categories = [
        ("", "All Scores"),
        ("blank", "N/A (No Score)"),
        ("achievers", "Achievers (≥70%)"),
        ("performers", "Performers (50-69%)"),
        ("aspirational", "Aspirational (<50%)"),
    ]

    # REAL DATA FOR CHARTS - Replace mock data with actual database queries

    # Chart 1: FPO Count Analysis data
    chart1_data = {}

    # Size category (Small vs Large)
    try:
        if FPODetailsSubmission:
            size_data = (
                FPODetailsSubmission.objects.filter(
                    size_of_fpo_fy_23_24__isnull=False, yearly_submission__fpo_id__in=filtered_fpo_ids
                )
                .annotate(
                    size_category=Case(
                        When(size_of_fpo_fy_23_24__lte=1000, then=Value("Small")),
                        When(size_of_fpo_fy_23_24__gt=1000, then=Value("Large")),
                        default=Value("Unknown"),
                        output_field=models.CharField(),
                    )
                )
                .values("size_category")
                .annotate(count=Count("id"))
            )

            size_categories = ["Small", "Large"]
            size_counts = {item["size_category"]: item["count"] for item in size_data}

            chart1_data["size"] = {
                "categories": size_categories,
                "data": [size_counts.get("Small", 0), size_counts.get("Large", 0)],
                "labels": ["≤1000 members", ">1000 members"],
            }
        else:
            # Fallback to existing data
            chart1_data["size"] = {
                "categories": ["Small", "Large"],
                "data": [small_fpos, large_fpos],
                "labels": ["≤1000 members", ">1000 members"],
            }
    except Exception:
        chart1_data["size"] = {
            "categories": ["Small", "Large"],
            "data": [small_fpos, large_fpos],
            "labels": ["≤1000 members", ">1000 members"],
        }

    # Gender category (Mixed vs Women Only)
    try:
        if FPODetailsSubmission:
            gender_data = (
                FPODetailsSubmission.objects.filter(
                    yearly_submission__fpo_id__in=filtered_fpo_ids,
                    size_of_fpo_fy_23_24__isnull=False,
                    women_members__isnull=False,
                )
                .annotate(
                    is_women_only=Case(
                        When(women_members=F("size_of_fpo_fy_23_24"), then=Value("Women Only")),
                        default=Value("Mixed"),
                        output_field=models.CharField(),
                    )
                )
                .values("is_women_only")
                .annotate(count=Count("id"))
            )

            gender_categories = ["Mixed", "Women Only"]
            gender_counts = {item["is_women_only"]: item["count"] for item in gender_data}

            chart1_data["gender"] = {
                "categories": gender_categories,
                "data": [gender_counts.get("Mixed", 0), gender_counts.get("Women Only", 0)],
                "labels": ["Mixed gender", "Women only"],
            }
        else:
            # Fallback to percentage-based data
            chart1_data["gender"] = {
                "categories": ["Mixed", "Women Only"],
                "data": [int(total_fpos * 0.6), int(total_fpos * 0.4)],
                "labels": ["Mixed gender", "Women only"],
            }
    except Exception:
        chart1_data["gender"] = {
            "categories": ["Mixed", "Women Only"],
            "data": [int(total_fpos * 0.6), int(total_fpos * 0.4)],
            "labels": ["Mixed gender", "Women only"],
        }

    # Agency category
    try:
        if FPODetailsSubmission:
            agency_data = (
                FPODetailsSubmission.objects.filter(
                    promoting_agency_name__isnull=False, yearly_submission__fpo_id__in=filtered_fpo_ids
                )
                .exclude(promoting_agency_name="")
                .values("promoting_agency_name")
                .annotate(count=Count("id"))
                .order_by("promoting_agency_name")
            )

            agency_categories = [item["promoting_agency_name"] for item in agency_data]
            agency_counts = [item["count"] for item in agency_data]
            agency_labels = [f"{item['promoting_agency_name']} promoted" for item in agency_data]

            chart1_data["agency"] = {"categories": agency_categories, "data": agency_counts, "labels": agency_labels}
        else:
            # Fallback to common agency types
            chart1_data["agency"] = {
                "categories": ["NABARD", "SFAC", "State Govt. Departments", "NGO", "Others"],
                "data": [
                    int(total_fpos * 0.4),
                    int(total_fpos * 0.25),
                    int(total_fpos * 0.2),
                    int(total_fpos * 0.1),
                    int(total_fpos * 0.05),
                ],
                "labels": ["NABARD promoted", "SFAC promoted", "State promoted", "NGO promoted", "Other agencies"],
            }
    except Exception:
        chart1_data["agency"] = {
            "categories": ["NABARD", "SFAC", "State Govt. Departments", "NGO", "Others"],
            "data": [
                int(total_fpos * 0.4),
                int(total_fpos * 0.25),
                int(total_fpos * 0.2),
                int(total_fpos * 0.1),
                int(total_fpos * 0.05),
            ],
            "labels": ["NABARD promoted", "SFAC promoted", "State promoted", "NGO promoted", "Other agencies"],
        }

    # Performance category (Achievers, Performers, Aspirational, Blank)
    try:
        performance_base_query = _apply_submission_datetime_filters(
            YearlySubmission.objects.reportable().filter(fpo_id__in=filtered_fpo_ids),
            selected_start_datetime,
            selected_end_datetime,
        )
        performance_data = (
            performance_base_query
            .annotate(
                performance_category=Case(
                    When(calculated_score__gte=70, then=Value("Achievers")),
                    When(calculated_score__gte=50, calculated_score__lt=70, then=Value("Performers")),
                    When(calculated_score__lt=50, then=Value("Aspirational")),
                    When(calculated_score__isnull=True, then=Value("Blank")),
                    default=Value("Unknown"),
                    output_field=models.CharField(),
                )
            )
            .values("performance_category")
            .annotate(count=Count("id"))
        )

        # Create a mapping and ensure correct order
        performance_counts = {item["performance_category"]: item["count"] for item in performance_data}

        # Define the desired order - now includes Blank
        desired_order = ["Achievers", "Performers", "Aspirational", "Blank"]
        categories = []
        data = []
        labels = []

        for category in desired_order:
            categories.append(category)
            data.append(performance_counts.get(category, 0))
            if category == "Blank":
                labels.append("N/A")
            else:
                labels.append(
                    f"Score {'≥70%' if category == 'Achievers' else '50-69%' if category == 'Performers' else '<50%'}"
                )

        chart1_data["performance"] = {"categories": categories, "data": data, "labels": labels}
    except Exception:
        chart1_data["performance"] = {
            "categories": ["Achievers", "Performers", "Aspirational", "Blank"],
            "data": [int(total_fpos * 0.3), int(total_fpos * 0.5), int(total_fpos * 0.2), int(total_fpos * 0.0)],
            "labels": ["Score ≥70%", "Score 50-69%", "Score <50%", "N/A"],
        }

    # State category (top 5 states)
    try:
        state_chart_data = base_fpo_queryset.values("state").annotate(count=Count("id")).order_by("-count")[:5]

        state_categories = [item["state"] for item in state_chart_data]
        state_counts = [item["count"] for item in state_chart_data]
        state_labels = [f"{item['count']} FPOs" for item in state_chart_data]

        chart1_data["state"] = {"categories": state_categories, "data": state_counts, "labels": state_labels}
    except Exception:
        # Fallback to state_data if available
        if state_data and len(state_data) > 0:
            top_states = state_data[:5]
            chart1_data["state"] = {
                "categories": [item["state"] for item in top_states],
                "data": [item["fpo_count"] for item in top_states],
                "labels": [f"{item['districts']} districts" for item in top_states],
            }
        else:
            chart1_data["state"] = {
                "categories": ["State1", "State2", "State3", "State4", "State5"],
                "data": [10, 8, 6, 4, 2],
                "labels": ["5 districts", "3 districts", "2 districts", "1 district", "1 district"],
            }

    # Chart 2: Score Analysis data
    chart2_data = {}

    # Final score distribution - count of FPOs in each score category
    try:
        final_score_base_query = _apply_submission_datetime_filters(
            YearlySubmission.objects.reportable().filter(
                fpo_id__in=filtered_fpo_ids,
                calculated_score__isnull=False,
            ),
            selected_start_datetime,
            selected_end_datetime,
        )
        final_score_data = (
            final_score_base_query
            .annotate(
                score_category=Case(
                    When(calculated_score__gte=80, then=Value("Excellent")),
                    When(calculated_score__gte=70, calculated_score__lt=80, then=Value("Good")),
                    When(calculated_score__gte=50, calculated_score__lt=70, then=Value("Average")),
                    When(calculated_score__lt=50, then=Value("Poor")),
                    default=Value("Unknown"),
                    output_field=models.CharField(),
                )
            )
            .values("score_category")
            .annotate(count=Count("id"))
            .order_by("score_category")
        )

        score_categories_map = {"Excellent": 0, "Good": 0, "Average": 0, "Poor": 0}
        for item in final_score_data:
            if item["score_category"] in score_categories_map:
                score_categories_map[item["score_category"]] = item["count"]

        chart2_data["final"] = {
            "categories": ["Excellent", "Good", "Average", "Poor"],
            "data": [
                score_categories_map["Excellent"],
                score_categories_map["Good"],
                score_categories_map["Average"],
                score_categories_map["Poor"],
            ],
            "labels": ["Score ≥80", "Score 70-79", "Score 50-69", "Score <50"],
        }
    except Exception:
        chart2_data["final"] = {
            "categories": ["Excellent", "Good", "Average", "Poor"],
            "data": [0, 0, 0, 0],
            "labels": ["Score ≥80", "Score 70-79", "Score 50-69", "Score <50"],
        }

    # Section scores (governance, operations, systems, finance)
    section_score_fields = ["governance_score", "business_score", "process_score", "financial_score"]
    section_names = ["governance", "operations", "systems", "finance"]
    section_labels = ["Governance Score", "Operations Score", "Systems Score", "Finance Score"]

    for i, field_name in enumerate(section_score_fields):
        try:
            section_data_query = YearlySubmission.objects.reportable().filter(
                fpo_id__in=filtered_fpo_ids, **{f"{field_name}__isnull": False}
            )
            section_data_query = _apply_submission_datetime_filters(
                section_data_query,
                selected_start_datetime,
                selected_end_datetime,
            )
            section_data = section_data_query.aggregate(avg_score=Avg(field_name))

            avg_section_score = float(section_data["avg_score"]) if section_data["avg_score"] else 0

            # Show actual average scores for each section
            chart2_data[section_names[i]] = {
                "categories": ["Average Score"],
                "data": [avg_section_score],
                "labels": [f"Avg: {avg_section_score:.1f}"],
            }
        except Exception:
            # Fallback data
            chart2_data[section_names[i]] = {"categories": ["No Data"], "data": [0], "labels": ["No data available"]}

    context = {
        "page_title": "FPO Reports",
        "total_fpos": total_fpos,
        "total_states": unique_states,
        "total_districts": unique_districts,
        "total_promoting_agencies": total_promoting_agencies,
        "average_score": round(avg_score, 2),
        # Dashboard card variables - First line
        "total_fpos_count": total_fpos,
        "total_states_count": unique_states,
        "total_districts_count": unique_districts,
        # Names lists for stat card tooltips
        "state_names_list": state_names_list,
        "district_names_list": district_names_list,
        "promoting_agency_names_list": promoting_agency_names_list,
        # Dashboard card variables - Second line
        "avg_total_score": avg_total_score,
        "avg_governance_score": avg_governance_score,
        "avg_operations_score": avg_operations_score,
        "avg_systems_score": avg_systems_score,
        "avg_financial_score": avg_financial_score,
        "small_fpos": small_fpos,
        "large_fpos": large_fpos,
        "state_data": state_data,
        "use_fpo_sidebar": True,
        # Chart data
        "chart1_data": chart1_data,
        "chart2_data": chart2_data,
        # Filter options
        "all_states": all_states,
        "promoting_agencies": promoting_agencies,
        "all_fpo_names": all_fpo_names,
        "score_categories": score_categories,
        # Selected filters
        "selected_state": selected_state,
        "selected_promoting_agency": selected_promoting_agency,
        "selected_score_category": selected_score_category,
        "selected_fpo_name": selected_fpo_name,
        "selected_financial_year": selected_financial_year,
        "selected_start_datetime": selected_start_datetime_raw,
        "selected_end_datetime": selected_end_datetime_raw,
        "selected_report_section": selected_report_section,
        "selected_governance_focus": selected_governance_focus,
        "selected_governance_metric": selected_governance_metric,
        "selected_operations_focus": selected_operations_focus,
        "selected_operations_metric": selected_operations_metric,
        "selected_finance_focus": selected_finance_focus,
        "selected_finance_metric": selected_finance_metric,
        "selected_systems_focus": selected_systems_focus,
        "selected_systems_metric": selected_systems_metric,
        "financial_years": financial_years,
    }

    return render(request, "fpo/reports_v2_new.html", context)


@login_required
def user_management(request):
    """View for managing users in the FPO system"""
    _require_user_admin(request)
    search_query = request.GET.get("search", "")
    role_filter = request.GET.get("role", "")

    # Get all users
    users = User.objects.all().prefetch_related("fpomember_set__fpo")

    # Apply search filter
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    # Apply role filter
    if role_filter:
        if role_filter == "admin":
            users = users.filter(fpomember__role="admin", fpomember__is_active=True)
        elif role_filter == "viewer":
            users = users.filter(fpomember__role="viewer", fpomember__is_active=True)
        elif role_filter == "no_role":
            users = users.exclude(fpomember__is_active=True)

    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "User Management",
        "page_obj": page_obj,
        "search_query": search_query,
        "role_filter": role_filter,
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/user_management.html", context)


@login_required
def create_user(request):
    """View for creating new users"""
    _require_user_admin(request)
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # Basic validation
        if not all([username, email, password, confirm_password]):
            messages.error(request, "Please fill in all required fields.")
            return render(request, "fpo/create_user.html", {"form_data": request.POST})

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "fpo/create_user.html", {"form_data": request.POST})

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "fpo/create_user.html", {"form_data": request.POST})

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return render(request, "fpo/create_user.html", {"form_data": request.POST})

        try:
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name or "",
                last_name=last_name or "",
            )
            messages.success(request, f'User "{user.username}" has been created successfully.')
            return redirect("fpo:user_management")
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")
            return render(request, "fpo/create_user.html", {"form_data": request.POST})

    context = {
        "page_title": "Create User",
        "use_fpo_sidebar": True,
    }
    return render(request, "fpo/create_user.html", context)


@login_required
@require_POST
def delete_user(request, user_id):
    """View for deleting users from the system"""
    _require_user_admin(request)
    from django.db import transaction
    from neo.models import RecentActivity
    from guardian.models import UserObjectPermission

    user_to_delete = get_object_or_404(User, id=user_id)
    if user_to_delete.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Only a superuser can delete a superuser.")

    # Prevent users from deleting themselves
    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect("fpo:user_management")

    try:
        username = user_to_delete.username

        # Use transaction to ensure atomic deletion
        with transaction.atomic():
            print(f"Starting deletion of user: {username} (ID: {user_id})")

            # 1. Remove all Guardian object permissions for this user
            permissions_count = UserObjectPermission.objects.filter(user=user_to_delete).count()
            print(f"Guardian user permissions to delete: {permissions_count}")
            if permissions_count > 0:
                deleted = UserObjectPermission.objects.filter(user=user_to_delete).delete()
                print(f"Deleted guardian permissions: {deleted}")

            # 2. Remove all FPO memberships (CASCADE)
            memberships_count = user_to_delete.fpomember_set.all().count()
            print(f"FPO memberships to delete: {memberships_count}")
            if memberships_count > 0:
                deleted = user_to_delete.fpomember_set.all().delete()
                print(f"Deleted FPO memberships: {deleted}")

            # 3. Update created_by field to NULL for FPOs created by this user (SET_NULL)
            created_fpos_count = user_to_delete.fpos_created.all().count()
            print(f"FPOs created by user: {created_fpos_count}")
            if created_fpos_count > 0:
                updated = user_to_delete.fpos_created.all().update(created_by=None)
                print(f"Updated FPOs created_by: {updated}")

            # 4. Update submitted_by field to NULL for submissions made by this user (SET_NULL)
            submissions_count = user_to_delete.submissions_made.all().count()
            print(f"Submissions made by user: {submissions_count}")
            if submissions_count > 0:
                updated = user_to_delete.submissions_made.all().update(submitted_by=None)
                print(f"Updated submissions submitted_by: {updated}")

            # 5. Update reviewed_by field to NULL for submissions reviewed by this user (SET_NULL)
            reviews_count = user_to_delete.submissions_reviewed.all().count()
            print(f"Submissions reviewed by user: {reviews_count}")
            if reviews_count > 0:
                updated = user_to_delete.submissions_reviewed.all().update(reviewed_by=None)
                print(f"Updated submissions reviewed_by: {updated}")

            # 6. Delete recent activities explicitly (CASCADE)
            activities_count = RecentActivity.objects.filter(user=user_to_delete).count()
            print(f"Recent activities to delete: {activities_count}")
            if activities_count > 0:
                deleted = RecentActivity.objects.filter(user=user_to_delete).delete()
                print(f"Deleted recent activities: {deleted}")

            # 7. Delete user profile (CASCADE) - handled automatically by Django
            if hasattr(user_to_delete, 'profile'):
                print(f"User has profile, will be deleted by CASCADE")

            # 8. Delete the user
            print(f"Deleting user: {username}")
            user_to_delete.delete()
            print(f"User deleted successfully")

        success_message = f'User "{username}" has been deleted successfully.'
        if memberships_count > 0:
            success_message += f' Removed {memberships_count} FPO membership(s).'
        if created_fpos_count > 0:
            success_message += f' Unlinked {created_fpos_count} FPO(s) created by this user.'

        messages.success(request, success_message)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error deleting user: {error_details}")  # Log full error for debugging
        messages.error(request, f"Error deleting user: {str(e)}")

    return redirect("fpo:user_management")


def api_fpo_listing(request):
    """
    Public API endpoint returning FPO card listing data for the weai-original frontend.
    Returns FPOs with their latest score, member count, location, and description.

    Single-pass query: filter + annotate (score, fpo_size, member_count) + paginate.
    Total DB hits per request: 2 (COUNT + page SELECT) regardless of page size.
    """
    from django.db.models import OuterRef, Subquery, FloatField, IntegerField, Q, Count, Value
    from django.db.models.functions import Coalesce
    import math

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

    state = request.GET.get('state', '')
    if state:
        fpos = fpos.filter(state__iexact=state)
    district = request.GET.get('district', '')
    if district:
        fpos = fpos.filter(district__iexact=district)
    search = request.GET.get('search', '').strip()
    if search:
        fpos = fpos.filter(name__icontains=search)

    category = request.GET.get('category', '')
    if category == 'Achiever':
        fpos = fpos.filter(score__gte=70)
    elif category == 'Performer':
        fpos = fpos.filter(score__gte=50, score__lt=70)
    elif category == 'Aspirational':
        fpos = fpos.filter(score__gt=0, score__lt=50)
    elif category == 'N/A':
        fpos = fpos.filter(score=0.0)

    fpos = fpos.order_by('-score', 'name')

    try:
        page = max(1, int(request.GET.get('page', 1)))
        limit = max(1, min(100, int(request.GET.get('limit', 12))))
    except (ValueError, TypeError):
        page, limit = 1, 12

    total = fpos.count()
    rows = list(
        fpos[(page - 1) * limit : page * limit].values(
            'pk', 'name', 'city', 'district', 'state',
            'score', 'fpo_size', 'member_count',
            'verification_status',
        )
    )

    fpo_list = []
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
        fpo_list.append({
            'id': slug,
            'pk': r['pk'],
            'score': round(r['score'], 1),
            'title': r['name'],
            'city': r['city'],
            'district': r['district'],
            'state': r['state'],
            'description': description,
            'members': r['fpo_size'] or r['member_count'],
            'verification_status': r['verification_status'],
        })

    return JsonResponse({
        'fpos': fpo_list,
        'total': total,
        'page': page,
        'limit': limit,
        'totalPages': math.ceil(total / limit) if limit else 0,
    })


def api_fpo_detail(request):
    """
    Public API endpoint returning detailed FPO data for a single FPO.
    Accepts ?slug=xxx or ?pk=xxx to identify the FPO.
    """
    slug = request.GET.get('slug', '')
    pk = request.GET.get('pk', '')

    fpo = None
    if pk:
        try:
            fpo = FPO.objects.publicly_visible().filter(pk=int(pk)).first()
        except (ValueError, TypeError):
            pass

    if not fpo and slug:
        # Try matching slug to FPO name
        for f in FPO.objects.publicly_visible():
            candidate = f.name.lower().replace(' ', '-').replace('.', '').replace(',', '')[:60]
            if candidate == slug:
                fpo = f
                break

    if not fpo:
        return JsonResponse({'error': 'FPO not found'}, status=404)

    # Get latest submission
    latest_sub = YearlySubmission.objects.reportable().filter(
        fpo=fpo, calculated_score__isnull=False
    ).order_by('-financial_year').first()

    score = float(latest_sub.calculated_score) if latest_sub and latest_sub.calculated_score else 0
    member_count = fpo.members.filter(is_active=True).count()

    # Get description and extra details
    description = ''
    revenue = 'N/A'
    commodities = []
    fpo_size = 0
    fpo_age = 0
    promoting_agency = ''

    try:
        if latest_sub:
            details = FPODetailsSubmission.objects.filter(yearly_submission=latest_sub).first()
            if details:
                fpo_size = details.size_of_fpo_fy_23_24 or details.size_of_fpo_fy_22_23 or details.size_of_fpo_fy_21_22 or 0
                promoting_agency = details.promoting_agency_name or ''
                fpo_age = details.age_of_fpo_years or 0

                parts = [f"{fpo.name} in {fpo.state}"]
                parts.append("empowers smallholder farmers by promoting collective farming")
                if fpo_size:
                    parts.append(f"with {fpo_size} members")
                description = ' '.join(parts) + '.'

            # Get financial details for revenue
            try:
                fin = latest_sub.financial_details_v2
                if fin:
                    rev = float(fin.current_year_revenue or 0)
                    if rev >= 10000000:
                        revenue = f"Rs. {rev / 10000000:.1f} Crores"
                    elif rev >= 100000:
                        revenue = f"Rs. {rev / 100000:.1f} Lakhs"
                    elif rev > 0:
                        revenue = f"Rs. {rev:,.0f}"

                    # Get products as commodities
                    if fin.current_year_products:
                        for prod in fin.current_year_products.split(','):
                            prod = prod.strip()
                            if prod:
                                commodities.append(prod)
            except Exception:
                pass
    except Exception:
        pass

    if not description:
        description = f"{fpo.name} in {fpo.state} empowers smallholder farmers by promoting collective farming of various crops, boosting yields and profitability through better market access and sustainable practices."

    slug_id = fpo.name.lower().replace(' ', '-').replace('.', '').replace(',', '')[:60]

    return JsonResponse({
        'id': slug_id,
        'pk': fpo.pk,
        'score': round(score, 1),
        'title': fpo.name,
        'city': fpo.city,
        'district': fpo.district,
        'state': fpo.state,
        'description': description,
        'members': fpo_size if fpo_size > 0 else member_count,
        'revenue': revenue,
        'fpo_age': round(fpo_age, 1),
        'promoting_agency': promoting_agency,
        'commodities': commodities,
        'store_link': fpo.store_link or '',
        'verification_status': fpo.verification_status,
    })


def api_filter_options(request):
    """
    Public API endpoint returning available filter options for the map.
    Returns lists of states, FPO names, and promoting agencies from the database.

    Accepts an optional ?state= query param. When provided, the `districts`
    list is scoped to that state. The `districts_by_state` map is always
    included so clients can scope districts without an extra round-trip.
    """
    selected_state = request.GET.get('state', '')

    # All active states
    all_states = list(
        FPO.objects.publicly_visible()
        .values_list('state', flat=True)
        .distinct()
        .order_by('state')
    )

    # Districts — scoped to selected_state when provided, otherwise global.
    districts_qs = FPO.objects.publicly_visible().exclude(district="")
    if selected_state:
        districts_qs = districts_qs.filter(state=selected_state)
    all_districts = list(
        districts_qs.values_list('district', flat=True).distinct().order_by('district')
    )

    # State -> sorted list of districts that actually have FPOs.
    districts_by_state: dict[str, list[str]] = {}
    for state, district in (
        FPO.objects.publicly_visible()
        .exclude(district="")
        .values_list('state', 'district')
        .distinct()
    ):
        districts_by_state.setdefault(state, []).append(district)
    for state in districts_by_state:
        districts_by_state[state] = sorted(set(districts_by_state[state]))

    # All active FPO names
    all_fpo_names = list(
        FPO.objects.publicly_visible()
        .values_list('name', flat=True)
        .distinct()
        .order_by('name')
    )

    # Promoting agencies
    promoting_agencies = []
    try:
        promoting_agencies = list(
            FPODetailsSubmission.objects.filter(
                yearly_submission__fpo__in=FPO.objects.publicly_visible(),
                promoting_agency_name__isnull=False,
            )
            .exclude(promoting_agency_name="")
            .values_list('promoting_agency_name', flat=True)
            .distinct()
            .order_by('promoting_agency_name')
        )
    except Exception:
        pass

    # Score categories (static)
    score_categories = [
        {'value': '', 'label': 'All Categories'},
        {'value': 'achievers', 'label': 'Achievers (≥70%)'},
        {'value': 'performers', 'label': 'Performers (50-69%)'},
        {'value': 'aspirational', 'label': 'Aspirational (<50%)'},
        {'value': 'blank', 'label': 'N/A'},
    ]

    return JsonResponse({
        'states': all_states,
        'districts': all_districts,
        'districts_by_state': districts_by_state,
        'fpo_names': all_fpo_names,
        'promoting_agencies': promoting_agencies,
        'score_categories': score_categories,
    })


@login_required
def reports_map(request):
    """
    Map view for FPO locations
    """
    import os
    from django.db import connection

    # Get filter parameters (matching reports_v2)
    selected_state = request.GET.get("state", "")
    selected_promoting_agency = request.GET.get("promoting_agency", "")
    selected_score_category = request.GET.get("score_category", "")
    selected_fpo_name = request.GET.get("fpo_name", "")

    # Build base queryset
    base_fpo_queryset = FPO.objects.publicly_visible()

    # Apply filters
    if selected_state:
        base_fpo_queryset = base_fpo_queryset.filter(state=selected_state)

    if selected_fpo_name:
        base_fpo_queryset = base_fpo_queryset.filter(name=selected_fpo_name)

    # Filter by promoting agency (using agency name)
    if selected_promoting_agency and FPODetailsSubmission:
        try:
            fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                promoting_agency_name__icontains=selected_promoting_agency
            ).values_list("yearly_submission__fpo_id", flat=True)
            base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_agency)
        except Exception:
            # Try alternative table if available
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                    if cursor.fetchone():
                        cursor.execute(
                            "SELECT DISTINCT fpo_id FROM fpo_basicdetails WHERE promoting_agency_name LIKE %s",
                            [f"%{selected_promoting_agency}%"],
                        )
                        fpo_ids = [row[0] for row in cursor.fetchall()]
                        if fpo_ids:
                            base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids)
            except Exception:
                pass

    # Filter by score category
    if selected_score_category:
        try:
            submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)

            if selected_score_category == "achievers":  # ≥70%
                submissions = submissions.filter(calculated_score__gte=70)
            elif selected_score_category == "performers":  # 50-69%
                submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
            elif selected_score_category == "aspirational":  # <50%
                submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
            elif selected_score_category == "blank":
                submissions = submissions.filter(calculated_score__isnull=True)

            fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
            if fpo_ids_with_score:
                base_fpo_queryset = base_fpo_queryset.filter(id__in=fpo_ids_with_score)
            elif selected_score_category:
                base_fpo_queryset = base_fpo_queryset.none()
        except Exception:
            pass

    # Get all states for filter
    all_states = FPO.objects.publicly_visible().values_list('state', flat=True).distinct().order_by('state')

    # Get all FPO names for filter
    all_fpo_names = FPO.objects.publicly_visible().values_list('name', flat=True).distinct().order_by('name')

    # Get promoting agencies (using distinct names from FPODetailsSubmission)
    promoting_agencies = []
    if FPODetailsSubmission:
        try:
            promoting_agencies = list(
                FPODetailsSubmission.objects.filter(
                    yearly_submission__fpo__in=FPO.objects.publicly_visible(),
                    promoting_agency_name__isnull=False,
                )
                .exclude(promoting_agency_name="")
                .values_list('promoting_agency_name', flat=True)
                .distinct()
                .order_by('promoting_agency_name')
            )
        except Exception:
            pass

    # Score categories matching reports_v2
    score_categories = [
        ('', 'All Categories'),
        ('achievers', 'Achievers (≥70%)'),
        ('performers', 'Performers (50-69%)'),
        ('aspirational', 'Aspirational (<50%)'),
        ('blank', 'N/A'),
    ]

    # Calculate statistics
    total_fpos = base_fpo_queryset.count()

    # Calculate average score from YearlySubmissions
    avg_score = 0
    try:
        submissions = YearlySubmission.objects.reportable().filter(
            fpo__in=base_fpo_queryset,
            calculated_score__isnull=False
        )
        if submissions.exists():
            from django.db.models import Avg
            avg_score = submissions.aggregate(avg=Avg('calculated_score'))['avg'] or 0
    except:
        pass

    # Get Mapbox token from environment
    map_style_url = os.environ.get('MAP_STYLE_URL', "")

    context = {
        'all_states': all_states,
        'all_fpo_names': all_fpo_names,
        'promoting_agencies': promoting_agencies,
        'score_categories': score_categories,
        'selected_state': selected_state,
        'selected_promoting_agency': selected_promoting_agency,
        'selected_score_category': selected_score_category,
        'selected_fpo_name': selected_fpo_name,
        'total_fpos': total_fpos,
        'avg_score': avg_score,
        'map_style_url': map_style_url,
    }

    return render(request, "fpo/reports_map.html", context)


def api_fpo_locations(request):
    """
    API endpoint to return FPO locations as GeoJSON
    """
    import random
    import json
    import os
    from django.conf import settings

    # Load city/district coordinates from GeoJSON file
    def load_geojson_coordinates():
        """Load coordinates from indian-cities.geojson"""
        geojson_path = os.path.join(settings.BASE_DIR, 'static', 'maps', 'geojson', 'indian-cities.geojson')
        city_coords = {}

        try:
            with open(geojson_path, 'r') as f:
                data = json.load(f)

            for feature in data.get('features', []):
                name = feature.get('properties', {}).get('name')
                geometry = feature.get('geometry', {})

                if name and geometry.get('type') == 'Polygon':
                    # Calculate centroid of polygon
                    coords = geometry.get('coordinates', [[]])[0]
                    if coords:
                        # Calculate average of all coordinates for centroid
                        lngs = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        centroid_lng = sum(lngs) / len(lngs)
                        centroid_lat = sum(lats) / len(lats)
                        city_coords[name] = [centroid_lng, centroid_lat]
        except Exception as e:
            print(f"Error loading GeoJSON: {e}")

        return city_coords

    # Load city coordinates from GeoJSON
    CITY_COORDINATES = load_geojson_coordinates()

    # State coordinates mapping (approximate center of each state in India)
    STATE_COORDINATES = {
        'Andhra Pradesh': [79.7400, 15.9129],
        'Arunachal Pradesh': [94.7278, 28.2180],
        'Assam': [92.9376, 26.2006],
        'Bihar': [85.3131, 25.0961],
        'Chhattisgarh': [81.8661, 21.2787],
        'Goa': [74.1240, 15.2993],
        'Gujarat': [71.1924, 22.2587],
        'Haryana': [76.0856, 29.0588],
        'Himachal Pradesh': [77.1734, 31.1048],
        'Jharkhand': [85.2799, 23.6102],
        'Karnataka': [75.7139, 15.3173],
        'Kerala': [76.2711, 10.8505],
        'Madhya Pradesh': [78.6569, 22.9734],
        'Maharashtra': [75.7139, 19.7515],
        'Manipur': [93.9063, 24.6637],
        'Meghalaya': [91.3662, 25.4670],
        'Mizoram': [92.9376, 23.1645],
        'Nagaland': [94.5624, 26.1584],
        'Odisha': [85.0985, 20.9517],
        'Punjab': [74.9115, 31.1471],
        'Rajasthan': [74.2179, 27.0238],
        'Sikkim': [88.5122, 27.5330],
        'Tamil Nadu': [78.6569, 11.1271],
        'Telangana': [79.0193, 18.1124],
        'Tripura': [91.9882, 23.9408],
        'Uttar Pradesh': [80.9462, 26.8467],
        'Uttarakhand': [79.0193, 30.0668],
        'West Bengal': [87.8550, 22.9868],
        'Andaman and Nicobar Islands': [92.6586, 11.7401],
        'Chandigarh': [76.7794, 30.7333],
        'Dadra and Nagar Haveli and Daman and Diu': [73.0169, 20.1809],
        'Delhi': [77.1025, 28.7041],
        'Jammu and Kashmir': [74.7973, 33.7782],
        'Ladakh': [78.2932, 34.1526],
        'Lakshadweep': [72.6369, 10.5667],
        'Puducherry': [79.8083, 11.9416]
    }

    def get_coordinates(city, district, state):
        """Get coordinates with fallback: city/district from GeoJSON -> state center"""
        # Create a case-insensitive lookup
        city_coords_lower = {k.lower(): v for k, v in CITY_COORDINATES.items()}

        # Try city first from GeoJSON (case-insensitive)
        if city:
            city_lower = city.lower()
            if city_lower in city_coords_lower:
                coords = city_coords_lower[city_lower]
                return [coords[0] + random.uniform(-0.01, 0.01), coords[1] + random.uniform(-0.01, 0.01)]

        # Try district from GeoJSON (case-insensitive)
        if district:
            district_lower = district.lower()
            if district_lower in city_coords_lower:
                coords = city_coords_lower[district_lower]
                return [coords[0] + random.uniform(-0.02, 0.02), coords[1] + random.uniform(-0.02, 0.02)]

        # Fallback to state center
        if state and state in STATE_COORDINATES:
            coords = STATE_COORDINATES[state]
            return [coords[0] + random.uniform(-0.5, 0.5), coords[1] + random.uniform(-0.5, 0.5)]

        return None

    # Get filter parameters (matching reports_map filters)
    state = request.GET.get("state", "")
    promoting_agency = request.GET.get("promoting_agency", "")
    score_category = request.GET.get("score_category", "")
    fpo_name = request.GET.get("fpo_name", "")

    # Build queryset
    fpos = FPO.objects.publicly_visible()

    # Apply filters
    if state:
        fpos = fpos.filter(state=state)

    if fpo_name:
        fpos = fpos.filter(name=fpo_name)

    # Filter by promoting agency (using agency name)
    if promoting_agency and FPODetailsSubmission:
        try:
            fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                promoting_agency_name__icontains=promoting_agency
            ).values_list("yearly_submission__fpo_id", flat=True).distinct()

            if fpo_ids_with_agency:
                fpos = fpos.filter(id__in=fpo_ids_with_agency)
            else:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by promoting agency: {e}")

    # Filter by score category
    if score_category:
        try:
            submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)

            if score_category == "achievers":  # ≥70%
                submissions = submissions.filter(calculated_score__gte=70)
            elif score_category == "performers":  # 50-69%
                submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
            elif score_category == "aspirational":  # <50%
                submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
            elif score_category == "blank":
                submissions = submissions.filter(calculated_score__isnull=True)

            fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
            if fpo_ids_with_score:
                fpos = fpos.filter(id__in=fpo_ids_with_score)
            elif score_category:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by score category: {e}")

    # Get score category for each FPO
    def get_score_category(score):
        """
        Categorize FPO scores:
        - Achievers: ≥70%
        - Performers: 50-69%
        - Aspirational: <50%
        - N/A: No Score
        """
        if score is None:
            return 'N/A'
        if score >= 70:
            return 'Achievers'
        elif score >= 50:
            return 'Performers'
        else:
            return 'Aspirational'

    def get_category_color(category):
        """Get color for each category"""
        colors = {
            'Achievers': '#22c55e',        # Green
            'Performers': '#f59e0b',       # Amber/Orange
            'Aspirational': '#ef4444',     # Red
            'N/A': '#94a3b8'               # Gray
        }
        return colors.get(category, '#94a3b8')

    # Prepare FPO data
    fpo_data = []
    for fpo in fpos:
        # Get latest submission with score
        latest_submission = None
        final_score = None

        try:
            submissions = YearlySubmission.objects.reportable().filter(fpo_id=fpo.id).order_by("-financial_year")

            # First try to find a submission with non-zero calculated score
            for sub in submissions:
                if sub.calculated_score is not None and sub.calculated_score > 0:
                    latest_submission = sub
                    break

            # If no submission with non-zero calculated score, use the most recent one
            if not latest_submission and submissions.exists():
                latest_submission = submissions.first()

            if latest_submission and latest_submission.calculated_score is not None:
                final_score = float(latest_submission.calculated_score)
        except Exception as e:
            print(f"Error getting score for FPO {fpo.id}: {e}")
            pass

        score_cat = get_score_category(final_score)

        # Get latitude and longitude
        latitude = None
        longitude = None

        # Try to get coordinates from the FPO model
        if hasattr(fpo, 'latitude') and hasattr(fpo, 'longitude'):
            latitude = fpo.latitude
            longitude = fpo.longitude
        # Or try to get from FPODetailsSubmission
        elif latest_submission:
            try:
                if FPODetailsSubmission:
                    details = FPODetailsSubmission.objects.filter(yearly_submission=latest_submission).first()
                    if details:
                        if hasattr(details, 'latitude') and hasattr(details, 'longitude'):
                            latitude = details.latitude
                            longitude = details.longitude
            except Exception:
                pass

        # If no coordinates found, use city/district from GeoJSON or state center
        if not latitude or not longitude:
            coords = get_coordinates(fpo.city, fpo.district, fpo.state)
            if coords:
                longitude = coords[0]
                latitude = coords[1]

        fpo_data.append({
            'id': fpo.id,
            'name': fpo.name,
            'state': fpo.state,
            'district': fpo.district,
            'city': fpo.city,
            'latitude': float(latitude) if latitude else None,
            'longitude': float(longitude) if longitude else None,
            'final_score': final_score,
            'score_category': score_cat,
            'category_color': get_category_color(score_cat),
        })

    # Calculate statistics
    total_fpos = len(fpo_data)

    # Calculate average score
    avg_score = 0
    scores = [f['final_score'] for f in fpo_data if f['final_score'] is not None]
    if scores:
        avg_score = sum(scores) / len(scores)

    return JsonResponse({
        'fpos': fpo_data,
        'statistics': {
            'total_fpos': total_fpos,
            'avg_score': float(avg_score),
        }
    })


def api_available_years(request):
    """
    API endpoint to return available financial years from YearlySubmission
    """
    try:
        years = (
            YearlySubmission.objects.reportable()
            .values_list('financial_year', flat=True)
            .distinct()
            .order_by('financial_year')
        )
        return JsonResponse({
            'years': list(years)
        })
    except Exception as e:
        return JsonResponse({
            'years': [],
            'error': str(e)
        })


def api_state_stats(request):
    """
    API endpoint to return statistics for a specific state
    """
    from django.db.models import Avg
    from django.db import connection

    state = request.GET.get('state', '')
    year = request.GET.get('year', '')
    promoting_agency = request.GET.get('promoting_agency', '')
    score_category = request.GET.get('score_category', '')
    fpo_name = request.GET.get('fpo_name', '')

    if not state:
        return JsonResponse({'error': 'State parameter is required'}, status=400)

    # Build queryset
    fpos = FPO.objects.publicly_visible().filter(state=state)

    # Apply FPO name filter
    if fpo_name:
        fpos = fpos.filter(name=fpo_name)

    # Filter by promoting agency
    if promoting_agency and FPODetailsSubmission:
        try:
            fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                promoting_agency_name__icontains=promoting_agency
            ).values_list("yearly_submission__fpo_id", flat=True).distinct()

            if fpo_ids_with_agency:
                fpos = fpos.filter(id__in=fpo_ids_with_agency)
            else:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by promoting agency: {e}")

    # Filter by score category
    if score_category:
        try:
            submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)

            if score_category == "achievers":  # ≥70%
                submissions = submissions.filter(calculated_score__gte=70)
            elif score_category == "performers":  # 50-69%
                submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
            elif score_category == "aspirational":  # <50%
                submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
            elif score_category == "blank":
                submissions = submissions.filter(calculated_score__isnull=True)

            fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
            if fpo_ids_with_score:
                fpos = fpos.filter(id__in=fpo_ids_with_score)
            elif score_category:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by score category: {e}")

    # Apply year filter if provided
    if year and year.strip():
        try:
            fpo_ids_with_year = list(YearlySubmission.objects.reportable().filter(
                financial_year=year
            ).values_list('fpo_id', flat=True).distinct())

            if fpo_ids_with_year:
                fpos = fpos.filter(id__in=fpo_ids_with_year)
        except Exception as e:
            print(f"Error filtering by year: {e}")

    # Calculate statistics
    total_fpos = fpos.count()
    districts = fpos.values('district').distinct().count()
    states = 1  # Since we're querying for a single state

    # Get submissions for score calculations
    submissions = YearlySubmission.objects.reportable().filter(fpo__in=fpos)
    if year and year.strip():
        submissions = submissions.filter(financial_year=year)

    # Count by category
    achievers = submissions.filter(calculated_score__gte=70).count()
    performers = submissions.filter(calculated_score__gte=50, calculated_score__lt=70).count()
    aspirational = submissions.filter(calculated_score__lt=50, calculated_score__isnull=False).count()

    # Average scores
    avg_score = submissions.aggregate(avg=Avg('calculated_score'))['avg']
    avg_governance = submissions.aggregate(avg=Avg('governance_score'))['avg']
    avg_operations = submissions.aggregate(avg=Avg('business_score'))['avg']
    avg_systems = submissions.aggregate(avg=Avg('process_score'))['avg']
    avg_financial = submissions.aggregate(avg=Avg('financial_score'))['avg']

    # Total submissions
    total_submissions = submissions.count()

    # Count promoting agencies
    promoting_agencies_count = 0
    if FPODetailsSubmission:
        try:
            agencies = FPODetailsSubmission.objects.filter(
                yearly_submission__fpo__in=fpos
            ).values('promoting_agency_name').distinct().count()
            promoting_agencies_count = agencies
        except Exception as e:
            print(f"Error counting promoting agencies: {e}")

    return JsonResponse({
        'total_fpos': total_fpos,
        'promoting_agencies': promoting_agencies_count,
        'states': states,
        'districts': districts,
        'achievers': achievers,
        'performers': performers,
        'aspirational': aspirational,
        'avg_score': float(avg_score) if avg_score else None,
        'avg_governance': float(avg_governance) if avg_governance else None,
        'avg_operations': float(avg_operations) if avg_operations else None,
        'avg_systems': float(avg_systems) if avg_systems else None,
        'avg_financial': float(avg_financial) if avg_financial else None,
        'total_members': 0,  # Placeholder - implement if member count is needed
        'women_members': 0,  # Placeholder - implement if member count is needed
        'total_submissions': total_submissions
    })


def api_state_agencies(request):
    """
    API endpoint to return agencies for a specific state
    """
    from django.db.models import Count

    state = request.GET.get('state', '')
    year = request.GET.get('year', '')
    promoting_agency = request.GET.get('promoting_agency', '')
    score_category = request.GET.get('score_category', '')
    fpo_name = request.GET.get('fpo_name', '')

    if not state:
        return JsonResponse({'error': 'State parameter is required'}, status=400)

    # Get FPOs in the state
    fpos = FPO.objects.publicly_visible().filter(state=state)

    # Apply FPO name filter
    if fpo_name:
        fpos = fpos.filter(name=fpo_name)

    # Filter by promoting agency
    if promoting_agency and FPODetailsSubmission:
        try:
            fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                promoting_agency_name__icontains=promoting_agency
            ).values_list("yearly_submission__fpo_id", flat=True).distinct()

            if fpo_ids_with_agency:
                fpos = fpos.filter(id__in=fpo_ids_with_agency)
            else:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by promoting agency: {e}")

    # Filter by score category
    if score_category:
        try:
            submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)

            if score_category == "achievers":  # ≥70%
                submissions = submissions.filter(calculated_score__gte=70)
            elif score_category == "performers":  # 50-69%
                submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
            elif score_category == "aspirational":  # <50%
                submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
            elif score_category == "blank":
                submissions = submissions.filter(calculated_score__isnull=True)

            fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
            if fpo_ids_with_score:
                fpos = fpos.filter(id__in=fpo_ids_with_score)
            elif score_category:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by score category: {e}")

    if year and year.strip():
        try:
            fpo_ids_with_year = list(YearlySubmission.objects.reportable().filter(
                financial_year=year
            ).values_list('fpo_id', flat=True).distinct())

            if fpo_ids_with_year:
                fpos = fpos.filter(id__in=fpo_ids_with_year)
        except Exception as e:
            print(f"Error filtering by year: {e}")

    # Get agencies from FPODetailsSubmission
    if FPODetailsSubmission:
        try:
            details = FPODetailsSubmission.objects.filter(
                yearly_submission__fpo__in=fpos
            ).values('promoting_agency_name').annotate(
                fpo_count=Count('yearly_submission__fpo', distinct=True)
            ).order_by('-fpo_count')

            agencies_list = []
            for detail in details:
                if detail['promoting_agency_name']:
                    agencies_list.append({
                        'name': detail['promoting_agency_name'],
                        'fpo_count': detail['fpo_count']
                    })

            return JsonResponse({'agencies': agencies_list})
        except Exception as e:
            print(f"Error fetching agencies: {e}")

    return JsonResponse({'agencies': []})


def api_fpo_state_counts(request):
    """
    API endpoint to return aggregated state-level counts for FPOs or Promoting Agencies
    """
    from django.db.models import Count
    from django.db import connection
    from collections import defaultdict

    # Get parameters (matching reports_v2 filters)
    view = request.GET.get('view', 'fpos')  # 'fpos' or 'agencies'
    year = request.GET.get('year', '')
    state_filter = request.GET.get('state', '')
    promoting_agency = request.GET.get('promoting_agency', '')
    score_category = request.GET.get('score_category', '')
    fpo_name = request.GET.get('fpo_name', '')

    # Build base queryset - start with all active FPOs
    fpos = FPO.objects.publicly_visible()

    # Apply location filters
    if state_filter:
        fpos = fpos.filter(state=state_filter)

    # Apply FPO name filter
    if fpo_name:
        fpos = fpos.filter(name=fpo_name)

    # Apply promoting agency filter (using agency name)
    if promoting_agency and FPODetailsSubmission:
        try:
            # Get FPO IDs that have this promoting agency in any of their submissions
            fpo_ids_with_agency = FPODetailsSubmission.objects.filter(
                promoting_agency_name__icontains=promoting_agency
            ).values_list('yearly_submission__fpo_id', flat=True).distinct()

            if fpo_ids_with_agency:
                fpos = fpos.filter(id__in=fpo_ids_with_agency)
            else:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by promoting agency: {e}")
            # Try alternative table if available
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fpo_basicdetails'")
                    if cursor.fetchone():
                        cursor.execute(
                            "SELECT DISTINCT fpo_id FROM fpo_basicdetails WHERE promoting_agency_name LIKE %s",
                            [f"%{promoting_agency}%"],
                        )
                        fpo_ids = [row[0] for row in cursor.fetchall()]
                        if fpo_ids:
                            fpos = fpos.filter(id__in=fpo_ids)
            except Exception:
                pass

    # Apply score category filter
    if score_category:
        try:
            submissions = YearlySubmission.objects.reportable().filter(calculated_score__isnull=False)

            if score_category == "achievers":  # ≥70%
                submissions = submissions.filter(calculated_score__gte=70)
            elif score_category == "performers":  # 50-69%
                submissions = submissions.filter(calculated_score__gte=50, calculated_score__lt=70)
            elif score_category == "aspirational":  # <50%
                submissions = submissions.filter(calculated_score__isnull=False, calculated_score__lt=50)
            elif score_category == "blank":
                submissions = submissions.filter(calculated_score__isnull=True)

            fpo_ids_with_score = submissions.values_list("fpo_id", flat=True).distinct()
            if fpo_ids_with_score:
                fpos = fpos.filter(id__in=fpo_ids_with_score)
            elif score_category:
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by score category: {e}")

    # Apply year filter if provided (optional)
    # If no year is provided, show all FPOs regardless of submission year
    if year and year.strip():
        try:
            # Get FPO IDs that have submissions for this year
            fpo_ids_with_year = list(YearlySubmission.objects.reportable().filter(
                financial_year=year
            ).values_list('fpo_id', flat=True).distinct())

            if fpo_ids_with_year:
                fpos = fpos.filter(id__in=fpo_ids_with_year)
            else:
                # No FPOs have submissions for this year
                fpos = fpos.none()
        except Exception as e:
            print(f"Error filtering by year: {e}")
            # On error, continue without year filter

    # Calculate total counts for both views
    total_fpos = fpos.count()
    total_agencies = 0

    if FPODetailsSubmission:
        try:
            # Count unique promoting agencies across all FPOs (excluding nulls)
            agencies = FPODetailsSubmission.objects.filter(
                yearly_submission__fpo__in=fpos,
                promoting_agency_name__isnull=False
            ).exclude(
                promoting_agency_name=''
            ).values('promoting_agency_name').distinct().count()
            total_agencies = agencies
        except Exception as e:
            print(f"Error counting agencies: {e}")

    if view == 'agencies':
        # Count unique promoting agencies per state
        state_counts = defaultdict(lambda: {'count': 0, 'agencies': set()})

        if FPODetailsSubmission:
            # Get all agencies for FPOs grouped by state
            agency_submissions = FPODetailsSubmission.objects.filter(
                yearly_submission__fpo__in=fpos
            ).select_related('yearly_submission__fpo').values(
                'yearly_submission__fpo__state',
                'promoting_agency_name'
            ).distinct()

            # Group agencies by state
            for submission in agency_submissions:
                state_name = submission['yearly_submission__fpo__state']
                agency_name = submission['promoting_agency_name']

                if state_name and agency_name:
                    state_counts[state_name]['agencies'].add(agency_name)

        # Convert sets to counts
        final_state_counts = {}
        for state_name, data in state_counts.items():
            final_state_counts[state_name] = {
                'count': len(data['agencies'])
            }

        state_counts = final_state_counts
    else:
        # Count FPOs per state
        state_counts = {}
        state_groups = fpos.values('state').annotate(count=Count('id'))

        for group in state_groups:
            state_name = group['state']
            count = group['count']

            # Include all states that have FPOs, regardless of coordinates
            if state_name:
                state_counts[state_name] = {
                    'count': count
                }

    return JsonResponse({
        'states': state_counts,
        'view': view,
        'year': year,
        'total_fpos': total_fpos,
        'total_agencies': total_agencies
    })

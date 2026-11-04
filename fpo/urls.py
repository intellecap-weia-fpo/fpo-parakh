from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView

from . import views

app_name = "fpo"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="fpo:fpos_list", permanent=False), name="dashboard"),
    path("fpos/", views.fpos_list, name="fpos_list"),
    path("fpos/export/", views.export_yearly_submissions, name="export_yearly_submissions"),
    path("fpos/create/", views.fpo_create, name="fpo_create"),
    path("verifications/", views.fpo_verification_requests, name="verification_requests"),
    path("verifications/<int:pk>/review/", views.review_fpo_verification, name="review_verification"),
    path("fpos/<int:pk>/", views.fpo_detail, name="fpo_detail"),
    path("fpos/<int:pk>/export/", views.export_fpo_details, name="export_fpo_details"),
    path("fpos/<int:pk>/delete/", views.fpo_delete, name="fpo_delete"),
    path("fpos/<int:fpo_pk>/submissions/<int:submission_pk>/", views.submission_detail, name="submission_detail"),
    path("fpos/<int:fpo_pk>/submissions/<int:submission_pk>/edit/", views.submission_edit, name="submission_edit"),
    path("fpos/<int:pk>/upload-document/", views.fpo_document_upload, name="fpo_document_upload"),
    path("fpos/<int:fpo_pk>/add-member/", views.add_member, name="add_member"),
    path("fpos/<int:fpo_pk>/members/<int:member_pk>/remove/", views.remove_member, name="remove_member"),
    path("fpos/<int:fpo_pk>/members/<int:member_pk>/update-role/", views.update_member_role, name="update_member_role"),
    path("fpos/<int:pk>/update-store-link/", views.update_store_link, name="update_store_link"),
    path("fpos/<int:pk>/recalculate-scores/", views.recalculate_scores, name="recalculate_scores"),
    path("search-users/", views.search_users, name="search_users"),
    path("reports/", views.reports, name="reports"),
    path("reports-v2/", views.reports_v2, name="reports_v2"),
    path("quick-guide/", views.quick_guide, name="quick_guide"),
    path("user-management/", views.user_management, name="user_management"),
    path("user-management/<int:user_id>/", views.user_detail, name="user_detail"),
    path("user-management/create/", views.create_user, name="create_user"),
    path("user-management/<int:user_id>/delete/", views.delete_user, name="delete_user"),
    path("api/process-document/", csrf_exempt(views.process_fpo_document), name="process_fpo_document"),
    path("api/chart-data/", views.api_chart_data, name="api_chart_data"),
    path("api/stats-data/", views.api_stats_data, name="api_stats_data"),
    path("api/fpo-table-data/", views.api_fpo_table_data, name="api_fpo_table_data"),
    path("api/fpo-locations/", views.api_fpo_locations, name="api_fpo_locations"),
    path("api/fpo-state-counts/", views.api_fpo_state_counts, name="api_fpo_state_counts"),
    path("api/available-years/", views.api_available_years, name="api_available_years"),
    path("api/state-stats/", views.api_state_stats, name="api_state_stats"),
    path("api/state-agencies/", views.api_state_agencies, name="api_state_agencies"),
    path("api/filter-options/", views.api_filter_options, name="api_filter_options"),
    path("api/fpo-listing/", views.api_fpo_listing, name="api_fpo_listing"),
    path("api/fpo-detail/", views.api_fpo_detail, name="api_fpo_detail"),
    path("fpos/<int:fpo_pk>/submissions/<int:submission_pk>/report-view/", views.submission_report_view, name="submission_report_view"),
    path("fpos/<int:fpo_pk>/submissions/<int:submission_pk>/pdf-report/", views.submission_pdf_report, name="submission_pdf_report"),
    path("fpos/<int:fpo_pk>/submissions/<int:submission_pk>/pdf-link/", views.submission_pdf_link, name="submission_pdf_link"),
    path("reports-map/", views.reports_map, name="reports_map"),
]

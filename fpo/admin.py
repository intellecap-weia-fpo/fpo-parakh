from django.contrib import admin
from django.utils.html import format_html
from .models import FPO, FPOMember, YearlySubmission


class FPOMemberInline(admin.TabularInline):
    model = FPOMember
    extra = 0
    fields = ('user', 'role', 'is_active')
    autocomplete_fields = ['user']


class YearlySubmissionInline(admin.TabularInline):
    model = YearlySubmission
    extra = 0
    fields = ('financial_year', 'status', 'calculated_score', 'submitted_at', 'reviewed_at')
    readonly_fields = ('submitted_at', 'reviewed_at', 'calculated_score')
    can_delete = False


@admin.register(FPO)
class FPOAdmin(admin.ModelAdmin):
    list_display = ('name', 'verification_status', 'email', 'phone', 'city', 'state', 'is_active', 'created_at')
    list_filter = ('verification_status', 'is_active', 'state', 'created_at')
    search_fields = ('name', 'email', 'phone', 'city')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [FPOMemberInline, YearlySubmissionInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'logo')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'alternate_phone')
        }),
        ('Address', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'district', 'state', 'pincode')
        }),
        ('Store', {
            'fields': ('store_link',)
        }),
        ('Status & Metadata', {
            'fields': (
                'is_active', 'verification_status', 'reviewed_by', 'reviewed_at',
                'verification_notes', 'created_by', 'created_at', 'updated_at'
            )
        }),
    )

    actions = ['approve_fpos', 'reject_fpos']

    @admin.action(description="Approve selected FPO profiles")
    def approve_fpos(self, request, queryset):
        count = queryset.count()
        for fpo in queryset:
            fpo.approve_verification(request.user, "Approved via Django admin")
        self.message_user(request, f"Approved {count} FPO profile(s).")

    @admin.action(description="Reject selected FPO profiles")
    def reject_fpos(self, request, queryset):
        count = queryset.count()
        for fpo in queryset:
            fpo.reject_verification(request.user, "Rejected via Django admin")
        self.message_user(request, f"Rejected {count} FPO profile(s).")


@admin.register(FPOMember)
class FPOMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'fpo', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active', 'joined_at', 'fpo')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'fpo__name')
    autocomplete_fields = ['user', 'fpo']


@admin.register(YearlySubmission)
class YearlySubmissionAdmin(admin.ModelAdmin):
    list_display = ('fpo', 'financial_year', 'status_badge', 'calculated_score', 'submitted_by', 'submitted_at', 'reviewed_by')
    list_filter = ('status', 'financial_year', 'submitted_at', 'reviewed_at')
    search_fields = ('fpo__name', 'financial_year', 'submitted_by__username', 'reviewed_by__username')
    autocomplete_fields = ['fpo', 'submitted_by', 'reviewed_by']
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'reviewed_at')
    
    fieldsets = (
        ('Submission Details', {
            'fields': ('fpo', 'financial_year', 'status', 'calculated_score')
        }),
        ('Submission Info', {
            'fields': ('submitted_by', 'submitted_at')
        }),
        ('Review Info', {
            'fields': ('reviewed_by', 'reviewed_at', 'approval_comments')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'draft': 'gray',
            'submitted': 'blue',
            'under_review': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'revision_required': 'yellow'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['approve_submissions', 'reject_submissions', 'request_revisions']
    
    def approve_submissions(self, request, queryset):
        count = 0
        for submission in queryset.filter(status='submitted'):
            submission.approve(request.user, "Bulk approved via admin")
            count += 1
        self.message_user(request, f"Approved {count} submissions.")
    approve_submissions.short_description = "Approve selected submissions"
    
    def reject_submissions(self, request, queryset):
        count = 0
        for submission in queryset.filter(status='submitted'):
            submission.reject(request.user, "Bulk rejected via admin")
            count += 1
        self.message_user(request, f"Rejected {count} submissions.")
    reject_submissions.short_description = "Reject selected submissions"
    
    def request_revisions(self, request, queryset):
        count = 0
        for submission in queryset.filter(status='submitted'):
            submission.request_revision(request.user, "Revision requested via admin")
            count += 1
        self.message_user(request, f"Requested revisions for {count} submissions.")
    request_revisions.short_description = "Request revisions for selected submissions"

    def force_delete_submissions(self, request, queryset):
        """Bypass Django's delete confirmation to avoid decimal conversion errors."""
        count = 0
        for submission in queryset:
            try:
                # Use the custom delete method that handles decimal errors
                submission.delete()
                count += 1
            except Exception as e:
                self.message_user(request, f"Error deleting {submission}: {str(e)}", level='error')
        
        if count == 1:
            message = "1 submission was successfully deleted."
        else:
            message = f"{count} submissions were successfully deleted."
        self.message_user(request, message)
    force_delete_submissions.short_description = "Force delete selected submissions (bypass confirmation)"

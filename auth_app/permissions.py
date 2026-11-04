from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.db import models


def get_user_role(user):
    """Get the primary role of a user"""
    if not user or not user.is_authenticated:
        return None

    # Check for specific groups in order of priority
    if user.groups.filter(name='admin').exists():
        return 'admin'
    elif user.groups.filter(name='cohortmanager').exists():
        return 'cohortmanager'
    elif user.groups.filter(name='mentor').exists():
        return 'mentor'
    elif user.groups.filter(name='startupadmin').exists():
        return 'startupadmin'
    elif user.groups.filter(name='startupuser').exists():
        return 'startupuser'

    return None


def check_startup_profile_completion(user):
    """Startup profile functionality removed - cohort app removed"""
    return {'has_company_profile': False, 'has_business_canvas': False}


def get_sidebar_menu_for_role(role, user=None):
    """Get sidebar menu items based on user role"""

    if role == 'admin':
        return [
            {
                "name": _("Dashboard"),
                "url": "/dashboard/",
                "icon_class": "fa fa-home",
            },
            {
                "name": _("Cohorts"),
                "url": "/cohorts/",
                "icon_class": "fa fa-folder-o",
            },
            {
                "name": _("Courses"),
                "url": "/courses/",
                "icon_class": "fa fa-graduation-cap",
            },
            {
                "name": _("Discussion"),
                "url": "/discussions/",
                "icon_class": "fa fa-comments-o",
            },
            {
                "name": _("My Certificates"),
                "url": "/certificates/",
                "icon_class": "fa fa-certificate",
            },
            {
                "name": _("Administration"),
                "icon_class": "fa fa-cogs",
                "children": [
                    {"name": _("Manage Cohorts"), "url": "/manage/cohorts/", "icon_class": "fa fa-folder-o"},
                    {"name": _("Manage Courses"), "url": "/manage/courses/", "icon_class": "fa fa-graduation-cap"},
                    {"name": _("Manage Startups"), "url": "/manage/startups/", "icon_class": "fa fa-rocket"},
                    {"name": _("BMC Management"), "url": "/manage/business-model-canvas-v2/", "icon_class": "fa fa-clipboard-list"},
                    {"name": _("User Management"), "url": "/manage/users/", "icon_class": "fa fa-id-card-o"},
                    {"name": _("Certificate Templates"), "url": "/manage/certificate-templates/", "icon_class": "fa fa-certificate"},
                    {"name": _("Mentors"), "url": "/manage/mentors/", "icon_class": "fa fa-users"},
                ],
                "default_open": False,
            },
        ]

    elif role == 'cohortmanager':
        return [
            {
                "name": _("Dashboard"),
                "url": "/dashboard/",
                "icon_class": "fa fa-home",
            },
            {
                "name": _("Cohorts"),
                "url": "/cohorts/",
                "icon_class": "fa fa-users",
            },
            {
                "name": _("Courses"),
                "url": "/courses/",
                "icon_class": "fa fa-graduation-cap",
            },
            {
                "name": _("Discussion"),
                "url": "/discussions/",
                "icon_class": "fa fa-comments-o",
            },
            {
                "name": _("My Certificates"),
                "url": "/certificates/",
                "icon_class": "fa fa-certificate",
            },
            {
                "name": _("Administration"),
                "icon_class": "fa fa-cogs",
                "children": [
                    {"name": _("Manage Cohorts"), "url": "/manage/cohorts/", "icon_class": "fa fa-users"},
                    {"name": _("Manage Courses"), "url": "/manage/courses/", "icon_class": "fa fa-graduation-cap"},
                    {"name": _("Manage Startups"), "url": "/manage/startups/", "icon_class": "fa fa-rocket"},
                    {"name": _("BMC Management"), "url": "/manage/business-model-canvas-v2/", "icon_class": "fa fa-clipboard-list"},
                    {"name": _("Certificate Templates"), "url": "/manage/certificate-templates/", "icon_class": "fa fa-certificate"},
                    {"name": _("Mentors"), "url": "/manage/mentors/", "icon_class": "fa fa-users"},
                ],
                "default_open": False,
            },
        ]

    elif role == 'mentor':
        return [
            {
                "name": _("Dashboard"),
                "url": "/dashboard/",
                "icon_class": "fa fa-home",
            },
            {
                "name": _("Cohorts"),
                "url": "/cohorts/",
                "icon_class": "fa fa-users",
            },
            {
                "name": _("Courses"),
                "url": "/courses/",
                "icon_class": "fa fa-graduation-cap",
            },
            {
                "name": _("Discussion"),
                "url": "/discussions/",
                "icon_class": "fa fa-comments-o",
            },
            {
                "name": _("My Certificates"),
                "url": "/certificates/",
                "icon_class": "fa fa-certificate",
            },
            {
                "name": _("Administration"),
                "icon_class": "fa fa-cogs",
                "children": [
                    {"name": _("BMC Management"), "url": "/manage/business-model-canvas-v2/", "icon_class": "fa fa-clipboard-list"},
                ],
                "default_open": False,
            },
        ]

    elif role == 'startupadmin':
        # Check profile completion status
        profile_status = check_startup_profile_completion(user)

        menu_items = [
            {
                "name": _("Dashboard"),
                "url": "/dashboard/",
                "icon_class": "fa fa-home",
            },
            {
                "name": _("Cohorts"),
                "url": "/cohorts/",
                "icon_class": "fa fa-users",
            },
            {
                "name": _("Courses"),
                "url": "/courses/",
                "icon_class": "fa fa-graduation-cap",
            },
            {
                "name": _("Discussion"),
                "url": "/discussions/",
                "icon_class": "fa fa-comments-o",
            },
            {
                "name": _("My Certificates"),
                "url": "/certificates/",
                "icon_class": "fa fa-certificate",
            },
        ]

        # Add Administration section with Company Profile and Business Canvas
        admin_children = []

        # Company Profile with warning badge if not completed
        company_profile_item = {
            "name": _("Company Profile"),
            "url": "/company-profile/",
            "icon_class": "fa fa-building-o",
        }
        if not profile_status['has_company_profile']:
            company_profile_item["badge"] = {"text": "!", "class": "bg-destructive text-destructive-foreground"}
        admin_children.append(company_profile_item)

        # Business Model Canvas with warning badge if not completed
        canvas_item = {
            "name": _("Business Model Canvas"),
            "url": "/business-model-canvas/",
            "icon_class": "fa fa-line-chart",
        }
        if not profile_status['has_business_canvas']:
            canvas_item["badge"] = {"text": "!", "class": "bg-destructive text-destructive-foreground"}
        admin_children.append(canvas_item)

        # Business Model Canvas v2
        canvas_v2_item = {
            "name": _("Business Model Canvas v2"),
            "url": "/business-model-canvas-v2/",
            "icon_class": "fa fa-tasks",
        }
        admin_children.append(canvas_v2_item)

        # Add Administration section
        administration_item = {
            "name": _("Administration"),
            "icon_class": "fa fa-cogs",
            "children": admin_children,
            "default_open": False,
        }
        menu_items.append(administration_item)

        return menu_items

    elif role == 'startupuser':
        menu_items = [
            {
                "name": _("Dashboard"),
                "url": "/dashboard/",
                "icon_class": "fa fa-home",
            },
            {
                "name": _("Cohorts"),
                "url": "/cohorts/",
                "icon_class": "fa fa-users",
            },
            {
                "name": _("Courses"),
                "url": "/courses/",
                "icon_class": "fa fa-graduation-cap",
            },
            {
                "name": _("Discussion"),
                "url": "/discussions/",
                "icon_class": "fa fa-comments-o",
            },
            {
                "name": _("My Certificates"),
                "url": "/certificates/",
                "icon_class": "fa fa-certificate",
            },
            {
                "name": _("Administration"),
                "icon_class": "fa fa-cogs",
                "children": [
                    {
                        "name": _("Company Profile"), 
                        "url": "/company-profile/", 
                        "icon_class": "fa fa-building-o"
                    },
                    {
                        "name": _("Business Model Canvas"), 
                        "url": "/business-model-canvas/", 
                        "icon_class": "fa fa-line-chart"
                    },
                    {
                        "name": _("Business Model Canvas v2"), 
                        "url": "/business-model-canvas-v2/", 
                        "icon_class": "fa fa-tasks"
                    },
                ],
                "default_open": False,
            },
        ]

        return menu_items

    # Default menu for authenticated users without specific role
    return [
        {
            "name": _("Dashboard"),
            "url": "/dashboard/",
            "icon_class": "fa fa-home",
        },
        {
            "name": _("Courses"),
            "url": "/courses/",
            "icon_class": "fa fa-graduation-cap",
        },
        {
            "name": _("My Certificates"),
            "url": "/certificates/",
            "icon_class": "fa fa-certificate",
        },
    ]


def can_edit_startup_profile(user, startup=None):
    """Check if a user can edit startup profile and business model canvas"""
    if not user or not user.is_authenticated:
        return False

    role = get_user_role(user)

    # Admin can edit everything
    if role == 'admin':
        return True

    # Cohort managers can edit startups they manage
    if role == 'cohortmanager':
        return True

    # Startup admins can edit their own startups
    if role == 'startupadmin':
        if startup:
            # Check if user is founder or admin of this startup
            return (startup.founder == user or user in startup.admins.all())
        return True  # General permission

    # Startup users can only view, not edit
    if role == 'startupuser':
        return False

    return False


def get_user_startups(user):
    """Startup functionality removed - cohort app removed"""
    return []


def can_access_url(user, url):
    """Check if a user can access a specific URL based on their role"""
    if not user or not user.is_authenticated:
        return False

    role = get_user_role(user)

    # Admin can access everything
    if role == 'admin':
        return True

    # Define URL access patterns for each role
    access_patterns = {
        'cohortmanager': [
            '/dashboard/',
            '/cohorts/',  # Cohorts page
            '/courses/',  # Courses page
            '/discussions/',
            '/certificates/',  # Certificates page
            '/manage/',  # Full access to management section
            '/mentors/',  # They can view mentors
            '/profile/',  # Profile access
        ],
        'mentor': [
            '/dashboard/',
            '/cohorts/',  # Cohorts page
            '/courses/',  # Courses page
            '/discussions/',
            '/certificates/',  # Certificates page
            '/manage/business-model-canvas-v2/',  # BMC Management
            '/profile/',  # Profile access
        ],
        'startupadmin': [
            '/dashboard/',
            '/cohorts/',  # Cohorts page
            '/courses/',  # Courses page
            '/discussions/',
            '/certificates/',  # Certificates page
            '/company-profile/',
            '/business-model-canvas/',
            '/business-model-canvas-v2/',
            '/profile/',  # Profile access
        ],
        'startupuser': [
            '/dashboard/',
            '/cohorts/',  # Cohorts page
            '/courses/',  # Courses page
            '/discussions/',
            '/certificates/',  # Certificates page
            '/company-profile/',  # They can view profile
            '/business-model-canvas/',  # They can view canvas
            '/business-model-canvas-v2/',
            '/profile/',  # Profile access
        ],
    }

    # Check if user's role has access to the URL
    if role in access_patterns:
        for pattern in access_patterns[role]:
            if url.startswith(pattern):
                return True

    return False


def filter_queryset_by_role(queryset, user, model_name):
    """Filter queryset based on user role and ownership"""
    if not user or not user.is_authenticated:
        return queryset.none()

    role = get_user_role(user)

    if role == 'admin':
        return queryset

    elif role == 'cohortmanager':
        # Filter to show only items created by this cohort manager
        if model_name in ['Cohort', 'Course']:
            return queryset.filter(created_by=user)
        elif model_name == 'Startup':
            # Show startups in cohorts managed by this user
            from management.models import Cohort
            managed_cohorts = Cohort.objects.filter(created_by=user)
            return queryset.filter(cohort__in=managed_cohorts)
        else:
            return queryset.none()

    elif role in ['startupadmin', 'startupuser']:
        # Show only their own startup's data
        if model_name == 'Startup':
            return queryset.filter(members=user)
        elif model_name == 'BusinessModelCanvas':
            return queryset.filter(startup__members=user)
        else:
            return queryset.none()

    return queryset.none()

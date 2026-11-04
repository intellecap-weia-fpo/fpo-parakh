from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from neo.models import SiteConfiguration
from management.models import UserProfile
from auth_app.decorators import admin_required
from auth_app.permissions import get_user_role


# Removed cohort-related functionality
def get_existing_startups_by_domain(email):
    """Startup functionality removed - cohort app removed"""
    return []


def get_email_domain_role(email):
    """Removed - cohort functionality disabled"""
    return None


def assign_user_group(user, role):
    """Assign user to appropriate group based on role"""
    try:
        if role == 'startupadmin':
            group, created = Group.objects.get_or_create(name='startupadmin')
        elif role == 'startupuser':
            group, created = Group.objects.get_or_create(name='startupuser')
        else:
            return False

        user.groups.add(group)
        return True
    except Exception:
        return False


@csrf_protect
def sign_in(request):
    if request.user.is_authenticated:
        return redirect("neo:home")

    if request.method == "POST":
        username_or_email = request.POST.get("username")
        password = request.POST.get("password")

        # Try to authenticate with username first
        user = authenticate(request, username=username_or_email, password=password)

        # If that fails, try to find user by email and authenticate with username
        if user is None:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user is not None:
            # Check if user is admin, staff, superuser, or manager
            is_manager = user.groups.filter(name='Manager').exists()
            is_admin_user = user.is_staff or user.is_superuser or is_manager

            # Only allow admin users to login via web admin interface
            if not is_admin_user:
                messages.error(request, "Wrong credentials.")
            else:
                login(request, user)

                # Check if there's a next parameter
                next_url = request.GET.get("next")
                if next_url:
                    return redirect(next_url)

                # Get landing page URL from site configuration
                site_config = SiteConfiguration.get_solo()
                landing_url = site_config.landing_page_url or "/fpo/reports-map/"

                return redirect(landing_url)
        else:
            messages.error(request, "Wrong credentials.")

    # Get invitation email from session if available
    invitation_email = request.session.get('invitation_email', '')

    context = {
        'invitation_email': invitation_email,
    }
    return render(request, "auth/sign_in.html", context)


@csrf_protect
def sign_up(request):
    """Sign up disabled - cohort functionality removed"""
    messages.error(request, "Sign up is currently disabled.")
    return redirect("auth_app:sign_in")


@csrf_protect
def join_organization_view(request):
    """Join organization disabled - cohort functionality removed"""
    messages.error(request, "This feature is currently disabled.")
    return redirect("auth_app:sign_in")


def logout_view(request):
    logout(request)
    return redirect("auth_app:sign_in")


@login_required
@csrf_protect
def profile_view(request):
    """User profile view with edit functionality and password change"""
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        # Check which form was submitted
        if "update_profile" in request.POST:
            # Update user basic info
            first_name = request.POST.get("first_name", "")
            last_name = request.POST.get("last_name", "")
            email = request.POST.get("email", "")

            # Update profile info
            bio = request.POST.get("bio", "")
            phone = request.POST.get("phone", "")
            location = request.POST.get("location", "")
            website = request.POST.get("website", "")
            preferred_language = request.POST.get("preferred_language", "en")

            # Check if email is already taken by another user
            if email and email != user.email:
                if User.objects.filter(email=email).exclude(id=user.id).exists():
                    messages.error(request, "This email is already in use by another account.")
                    return redirect("/fpo/")

            # Update user fields
            user.first_name = first_name
            user.last_name = last_name
            if email:
                user.email = email
            user.save()

            # Update profile fields
            profile.bio = bio
            profile.phone = phone
            profile.location = location
            profile.website = website
            profile.preferred_language = preferred_language

            # Handle profile image upload
            if "profile_image" in request.FILES:
                profile.profile_image = request.FILES["profile_image"]

            # Handle cover image upload
            if "cover_image" in request.FILES:
                profile.cover_image = request.FILES["cover_image"]

            profile.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("/fpo/")

        elif "change_password" in request.POST:
            # Handle password change
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Keep user logged in
                messages.success(request, "Your password has been changed successfully.")
                return redirect("/fpo/")
            else:
                # Show password form errors
                for field, errors in password_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{error}")

    # For GET request or after POST
    password_form = PasswordChangeForm(user)

    context = {
        "user": user,
        "profile": profile,
        "password_form": password_form,
        "languages": UserProfile._meta.get_field('preferred_language').choices,
    }

    return render(request, "auth/profile.html", context)


def send_verification_email(user, profile):
    """Send email verification link to user"""
    token = profile.generate_verification_token()

    # Create verification URL
    verification_url = f"{settings.SITE_URL}/auth/verify-email/{token}/"

    # Render email template
    html_message = render_to_string('auth/email_verification_email.html', {
        'user': user,
        'verification_url': verification_url,
        'site_name': 'FPO Rating Tool',
    })
    plain_message = strip_tags(html_message)

    # Send email
    send_mail(
        subject='Please verify your email address',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


@login_required
@csrf_protect
def send_verification_email_view(request):
    """Resend email verification"""
    if request.method == "POST":
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        if profile.email_verified:
            messages.info(request, "Your email is already verified.")
        else:
            try:
                send_verification_email(request.user, profile)
                messages.success(request, "Verification email has been sent to your email address.")
            except Exception as e:
                messages.error(request, "Failed to send verification email. Please try again later.")

    return redirect("/fpo/")


def verify_email_view(request, token):
    """Verify email with token"""
    try:
        profile = UserProfile.objects.get(email_verification_token=token)
        user = profile.user

        if profile.email_verified:
            messages.info(request, "Your email is already verified.")
        elif profile.is_verification_token_expired():
            messages.error(request, "Verification link has expired. Please request a new one.")
        else:
            profile.verify_email()
            messages.success(request, "Your email has been verified successfully!")

        # Redirect to profile if logged in, otherwise to sign in
        if request.user.is_authenticated:
            return redirect("/fpo/")
        else:
            return redirect("auth_app:sign_in")

    except UserProfile.DoesNotExist:
        messages.error(request, "Invalid verification link.")
        return redirect("auth_app:sign_in")


# User Management Views for Admin

@admin_required
def user_list_view(request):
    """List all users with search, filters, and pagination"""
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    role_filter = request.GET.get('role', '')
    sort_by = request.GET.get('sort', 'date_joined')
    order = request.GET.get('order', 'desc')

    users_query = User.objects.all()

    # Apply search filter
    if search_query:
        users_query = users_query.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # Apply status filter
    if status_filter:
        if status_filter == 'active':
            users_query = users_query.filter(is_active=True)
        elif status_filter == 'inactive':
            users_query = users_query.filter(is_active=False)

    # Apply role filter
    if role_filter:
        if role_filter == 'superuser':
            users_query = users_query.filter(is_superuser=True)
        elif role_filter == 'staff':
            users_query = users_query.filter(is_staff=True, is_superuser=False)
        elif role_filter == 'user':
            users_query = users_query.filter(is_staff=False, is_superuser=False)

    # Apply sorting
    sort_field = sort_by
    if sort_by == 'name':
        sort_field = 'first_name'
    elif sort_by == 'email':
        sort_field = 'email'
    elif sort_by == 'status':
        sort_field = 'is_active'
    elif sort_by == 'date':
        sort_field = 'date_joined'

    if order == 'desc':
        sort_field = f'-{sort_field}'

    users_query = users_query.order_by(sort_field)

    # Pagination
    paginator = Paginator(users_query, 20)  # Show 20 users per page (same as management)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get user roles for display
    for user in page_obj:
        user.user_role = get_user_role(user)

    # Calculate stats
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    admin_users = User.objects.filter(is_superuser=True).count()

    from django.urls import reverse
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'total_users': total_users,
        'active_users': active_users,
        'admin_users': admin_users,
        'page_title': _('User Management'),
        'page_subtitle': _('Manage all users in the system'),
        'page_actions': [
            {
                'text': _('Add User'),
                'url': reverse('auth_app:user_add'),
                'icon': 'fa fa-plus',
                'class': 'text-primary-foreground bg-primary hover:bg-primary/80'
            }
        ],
    }

    return render(request, 'auth/user_list.html', context)


@admin_required
def user_detail_view(request, user_id):
    """View user details and profile information"""
    user = get_object_or_404(User, id=user_id)
    profile, created = UserProfile.objects.get_or_create(user=user)
    user_role = get_user_role(user)
    groups = user.groups.all()

    context = {
        'viewed_user': user,
        'profile': profile,
        'user_role': user_role,
        'groups': groups,
        'page_title': f'User Details - {user.username}',
        'page_subtitle': f'View information for {user.get_full_name() or user.username}',
        'back_url': '/manage/users/',
        'back_text': 'Back to Users',
        'page_actions': [
            {'url': f'/manage/users/{user.id}/edit/', 'text': 'Edit User', 'icon': 'fa fa-edit', 'class': 'text-primary-foreground bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 border border-transparent'}
        ]
    }

    return render(request, 'auth/user_detail.html', context)


@admin_required
@csrf_protect
def user_add_view(request):
    """Add new user"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active', 'on') == 'on'
        selected_groups = request.POST.getlist('groups')

        # Validation
        errors = []
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('Username already exists.')

        if not email:
            errors.append('Email is required.')
        elif User.objects.filter(email=email).exists():
            errors.append('Email already exists.')

        if not password:
            errors.append('Password is required.')
        elif password != password_confirm:
            errors.append('Passwords do not match.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters long.')

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=is_staff,
                is_active=is_active
            )

            # Add user to groups
            if selected_groups:
                groups = Group.objects.filter(id__in=selected_groups)
                user.groups.set(groups)

            messages.success(request, f'User "{username}" has been created successfully.')
            return redirect('auth_app:user_detail', user_id=user.id)

    # Get all available groups
    all_groups = Group.objects.all().order_by('name')

    context = {
        'all_groups': all_groups,
        'page_title': 'Add New User',
        'page_subtitle': 'Create a new user account',
        'back_url': '/manage/users/',
        'back_text': 'Back to Users'
    }

    return render(request, 'auth/user_add.html', context)


@admin_required
@csrf_protect
def user_edit_view(request, user_id):
    """Edit existing user"""
    user = get_object_or_404(User, id=user_id)
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active', 'on') == 'on'
        selected_groups = request.POST.getlist('groups')

        # Handle password change if provided
        new_password = request.POST.get('new_password', '')
        new_password_confirm = request.POST.get('new_password_confirm', '')

        # Validation
        errors = []
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exclude(id=user.id).exists():
            errors.append('Username already exists.')

        if not email:
            errors.append('Email is required.')
        elif User.objects.filter(email=email).exclude(id=user.id).exists():
            errors.append('Email already exists.')

        if new_password:
            if new_password != new_password_confirm:
                errors.append('New passwords do not match.')
            elif len(new_password) < 8:
                errors.append('Password must be at least 8 characters long.')

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Update user
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = is_staff
            user.is_active = is_active

            if new_password:
                user.set_password(new_password)

            user.save()

            # Update user groups
            if selected_groups:
                groups = Group.objects.filter(id__in=selected_groups)
                user.groups.set(groups)
            else:
                user.groups.clear()

            messages.success(request, f'User "{username}" has been updated successfully.')
            return redirect('auth_app:user_detail', user_id=user.id)

    # Get all available groups and user's current groups
    all_groups = Group.objects.all().order_by('name')
    user_group_ids = list(user.groups.values_list('id', flat=True))

    context = {
        'edited_user': user,
        'profile': profile,
        'all_groups': all_groups,
        'user_group_ids': user_group_ids,
        'page_title': f'Edit User - {user.username}',
        'page_subtitle': f'Modify information for {user.get_full_name() or user.username}',
        'back_url': f'/manage/users/{user.id}/',
        'back_text': 'Back to User Details'
    }

    return render(request, 'auth/user_edit.html', context)


def profile_redirect_view(request):
    """Redirect old auth profile URL to cohort profile URL"""
    return redirect('/fpo/')


def cohort_profile_view(request):
    """Profile view that uses cohort sidebar - wrapper around the original profile view"""
    # This is essentially the same as profile_view but ensures it renders with cohort app context
    # so the cohort sidebar is displayed
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        # Check which form was submitted
        if "update_profile" in request.POST:
            # Update user basic info
            first_name = request.POST.get("first_name", "")
            last_name = request.POST.get("last_name", "")
            email = request.POST.get("email", "")

            # Update profile info
            bio = request.POST.get("bio", "")
            phone = request.POST.get("phone", "")
            location = request.POST.get("location", "")
            website = request.POST.get("website", "")
            preferred_language = request.POST.get("preferred_language", "en")

            # Check if email is already taken by another user
            if email and email != user.email:
                if User.objects.filter(email=email).exclude(id=user.id).exists():
                    messages.error(request, "This email is already in use by another account.")
                    return redirect("/fpo/")

            # Update user fields
            user.first_name = first_name
            user.last_name = last_name
            if email:
                user.email = email
            user.save()

            # Update profile fields
            profile.bio = bio
            profile.phone = phone
            profile.location = location
            profile.website = website
            profile.preferred_language = preferred_language

            # Handle profile image upload
            if "profile_image" in request.FILES:
                profile.profile_image = request.FILES["profile_image"]

            # Handle cover image upload
            if "cover_image" in request.FILES:
                profile.cover_image = request.FILES["cover_image"]

            profile.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("/fpo/")

        elif "change_password" in request.POST:
            # Handle password change
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Keep user logged in
                messages.success(request, "Your password has been changed successfully.")
                return redirect("/fpo/")
            else:
                # Show password form errors
                for field, errors in password_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{error}")

    # For GET request or after POST
    password_form = PasswordChangeForm(user)

    context = {
        "user": user,
        "profile": profile,
        "password_form": password_form,
        "languages": UserProfile._meta.get_field('preferred_language').choices,
        "page_title": "Profile",
        "page_subtitle": "Manage your account settings and preferences",
    }

    return render(request, "auth/profile.html", context)

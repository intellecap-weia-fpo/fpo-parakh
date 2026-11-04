from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse
from django import forms
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from functools import wraps
from .models import UserProfile


def superuser_required(view):
    """User administration here can grant the admin role (superuser), so only superusers may use it."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only a superuser can manage users.")
        return view(request, *args, **kwargs)
    return wrapper


def self_or_superuser_required(view):
    @wraps(view)
    def wrapper(request, user_id, *args, **kwargs):
        if not (request.user.is_superuser or request.user.pk == user_id):
            raise PermissionDenied("You can only change your own images.")
        return view(request, user_id, *args, **kwargs)
    return wrapper


@login_required
@superuser_required
def dashboard(request):
    """Management dashboard view"""
    user_count = User.objects.count()
    active_user_count = User.objects.filter(is_active=True).count()

    context = {
        "user_count": user_count,
        "active_user_count": active_user_count,
        "page_title": "Management Dashboard",
        "page_subtitle": "User management and system administration"
    }
    return render(request, "management/dashboard.html", context)


def get_user_role_display(user):
    """Get display name for user's role based on their groups"""
    if user.is_superuser:
        return "Admin"

    # Check user's groups
    user_groups = user.groups.values_list('name', flat=True)

    if 'admin' in user_groups:
        return "Admin"
    elif 'cohortmanager' in user_groups:
        return "Cohort Manager"
    elif 'mentor' in user_groups:
        return "Mentor"
    elif 'startupadmin' in user_groups:
        return "Startup Admin"
    elif 'startupuser' in user_groups:
        return "Startup User"
    elif user.is_staff:
        return "Staff"
    else:
        return "User"


class UserForm(forms.ModelForm):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('cohortmanager', 'Cohort Manager'),
        ('startupadmin', 'Startup Admin'),
        ('startupuser', 'Startup User'),
        ('mentor', 'Mentor'),
    ]
    
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Select Role",
        required=True
    )
    
    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active", "role"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial role value based on user's current groups
        if self.instance and self.instance.pk:
            user_groups = self.instance.groups.all()
            if user_groups:
                # Set role based on the first group (assuming one role per user)
                self.initial['role'] = user_groups.first().name


class UserCreateForm(UserCreationForm):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('cohortmanager', 'Cohort Manager'),
        ('startupadmin', 'Startup Admin'),
        ('startupuser', 'Startup User'),
        ('mentor', 'Mentor'),
    ]
    
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={"class": "form-control"}))
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Select Role",
        required=True
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2", "role")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})


@login_required
@superuser_required
def user_list(request):
    search_query = request.GET.get("search", "")
    users = User.objects.all()

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    users = users.order_by("-date_joined")

    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Add role information for each user
    for user in page_obj:
        user.user_role = get_user_role_display(user)

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "total_users": User.objects.count(),
        "page_title": _("User Management"),
        "page_subtitle": _("Manage system users and their permissions"),
        "page_actions": [
            {
                "text": _("Add User"),
                "url": reverse("management:user_create"),
                "icon": "fa fa-plus",
                "class": "text-primary-foreground bg-primary hover:bg-primary/80",
            }
        ],
    }

    return render(request, "management/user_list.html", context)


@login_required
@superuser_required
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Handle role assignment
            selected_role = form.cleaned_data.get('role')
            if selected_role:
                # Remove user from all groups first
                user.groups.clear()
                
                # Create the group if it doesn't exist and add user to it
                group, created = Group.objects.get_or_create(name=selected_role)
                user.groups.add(group)
                
                # Set is_staff based on role
                if selected_role == 'admin':
                    user.is_staff = True
                    user.is_superuser = True
                elif selected_role in ['cohortmanager', 'mentor']:
                    user.is_staff = True
                    user.is_superuser = False
                else:
                    user.is_staff = False
                    user.is_superuser = False
                
                user.save()
            
            messages.success(request, f'User "{user.username}" created successfully with role "{selected_role}".')
            return redirect("management:user_detail", user_id=user.id)
        else:
            messages.error(request, "Please correct the errors below and try again.")
    else:
        form = UserCreateForm()

    context = {
        "form": form,
        "page_title": _("Create New User"),
        "page_subtitle": _("Add a new user to the system"),
        "back_url": reverse("management:user_list"),
    }
    return render(request, "management/user_create.html", context)


@login_required
@superuser_required
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)

    # Handle DELETE request
    if request.method == "POST" and request.POST.get('action') == 'delete':
        username = user.username
        user.delete()
        messages.success(request, f'User "{username}" deleted successfully.')
        return JsonResponse({'success': True, 'message': f'User "{username}" deleted successfully.', 'redirect': reverse('management:user_list')})

    # Ensure user has a profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Check if user is a mentor
    is_mentor = user.groups.filter(name='mentor').exists()

    context = {
        "user_obj": user,
        "is_mentor": is_mentor,
        "page_title": user.get_full_name() or user.username,
        "page_subtitle": _(f"User details for @{user.username}"),
        "page_actions": [],
    }

    return render(request, "management/user_detail.html", context)


@login_required
@superuser_required
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            
            # Handle role assignment
            selected_role = form.cleaned_data.get('role')
            if selected_role:
                # Remove user from all groups first
                user.groups.clear()
                
                # Create the group if it doesn't exist and add user to it
                group, created = Group.objects.get_or_create(name=selected_role)
                user.groups.add(group)
                
                # Set is_staff based on role
                if selected_role == 'admin':
                    user.is_staff = True
                    user.is_superuser = True
                elif selected_role in ['cohortmanager', 'mentor']:
                    user.is_staff = True
                    user.is_superuser = False
                else:
                    user.is_staff = False
                    user.is_superuser = False
                
                user.save()
            
            messages.success(request, f'User "{user.username}" updated successfully with role "{selected_role}".')
            return redirect("management:user_detail", user_id=user.id)
        else:
            messages.error(request, "Please correct the errors below and try again.")
    else:
        form = UserForm(instance=user)

    context = {
        "form": form,
        "user_obj": user,
        "page_title": _(f"Edit {user.get_full_name() or user.username}"),
        "page_subtitle": _(f"Update user information for @{user.username}"),
    }
    return render(request, "management/user_edit.html", context)




@login_required
@require_POST
@self_or_superuser_required
def upload_profile_image(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if "profile_image" not in request.FILES:
        return JsonResponse({"error": "No image file provided"}, status=400)

    image_file = request.FILES["profile_image"]

    # Validate file type
    if not image_file.content_type.startswith("image/"):
        return JsonResponse({"error": "File must be an image"}, status=400)

    # Validate file size (5MB limit)
    if image_file.size > 5 * 1024 * 1024:
        return JsonResponse({"error": "Image file too large (max 5MB)"}, status=400)

    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Delete old profile image if it exists
    if profile.profile_image:
        profile.profile_image.delete(save=False)

    # Save new profile image
    profile.profile_image = image_file
    profile.save()

    messages.success(request, "Profile image updated successfully.")
    return JsonResponse({"success": True, "image_url": profile.profile_image.url if profile.profile_image else None})


@login_required
@require_POST
@self_or_superuser_required
def upload_cover_image(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if "cover_image" not in request.FILES:
        return JsonResponse({"error": "No image file provided"}, status=400)

    image_file = request.FILES["cover_image"]

    # Validate file type
    if not image_file.content_type.startswith("image/"):
        return JsonResponse({"error": "File must be an image"}, status=400)

    # Validate file size (10MB limit for cover images)
    if image_file.size > 10 * 1024 * 1024:
        return JsonResponse({"error": "Image file too large (max 10MB)"}, status=400)

    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Delete old cover image if it exists
    if profile.cover_image:
        profile.cover_image.delete(save=False)

    # Save new cover image
    profile.cover_image = image_file
    profile.save()

    messages.success(request, "Cover image updated successfully.")
    return JsonResponse({"success": True, "image_url": profile.cover_image.url if profile.cover_image else None})


@login_required
def settings_view(request):
    """Simple settings view that returns a basic response"""
    return render(request, "management/settings.html", {
        "page_title": _("Settings"),
        "page_subtitle": _("System settings and configuration")
    })

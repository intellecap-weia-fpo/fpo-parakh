from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from auth_app.permissions import get_user_role


def role_required(*allowed_roles):
    """Decorator to check if user has one of the allowed roles"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, 'Please login to access this page.')
                return redirect('auth_app:sign_in')
            
            user_role = get_user_role(request.user)

            if user_role not in allowed_roles:
                # messages.error(request, 'You do not have permission to access this page.')
                return redirect('/fpo/')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    """Decorator to check if user is an admin"""
    return role_required('admin')(view_func)


def cohortmanager_or_admin_required(view_func):
    """Decorator to check if user is a cohort manager or admin"""
    return role_required('admin', 'cohortmanager')(view_func)


def startup_admin_required(view_func):
    """Decorator to check if user is a startup admin or admin"""
    return role_required('admin', 'startupadmin')(view_func)


def management_required(view_func):
    """Decorator for management URLs - requires admin or cohortmanager"""
    return role_required('admin', 'cohortmanager')(view_func)

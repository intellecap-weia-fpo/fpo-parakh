from django.core import signing
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.shortcuts import get_user_by_token

PDF_LINK_SALT = "fpo.submission_pdf_report"
PDF_LINK_MAX_AGE = 10 * 60


def user_from_request(request):
    """Session user for the web app, or the user of a `Bearer` JWT for the mobile app."""
    header = request.headers.get("Authorization", "").split()
    if header:
        if len(header) != 2 or header[0].lower() != "bearer":
            return None
        try:
            return get_user_by_token(header[1], request)
        except JSONWebTokenError:
            return None
    return request.user if request.user.is_authenticated else None


def can_view_fpo(user, fpo):
    return bool(
        user
        and user.is_active
        and (
            user.is_staff
            or user.is_superuser
            or user.groups.filter(name="admin").exists()
            or user.has_perm("fpo.verify_fpo")
            or fpo.created_by_id == user.pk
            or fpo.members.filter(user=user, is_active=True).exists()
        )
    )


def can_manage_fpo(user, fpo):
    """Platform admins, or an active admin member of this FPO."""
    return bool(
        user
        and user.is_active
        and (
            user.is_staff
            or user.is_superuser
            or user.groups.filter(name="admin").exists()
            or fpo.members.filter(user=user, is_active=True, role="admin").exists()
        )
    )


def sign_pdf_link(fpo_pk, submission_pk):
    return signing.dumps([fpo_pk, submission_pk], salt=PDF_LINK_SALT)


def pdf_link_is_valid(sig, fpo_pk, submission_pk):
    try:
        return signing.loads(sig, salt=PDF_LINK_SALT, max_age=PDF_LINK_MAX_AGE) == [fpo_pk, submission_pk]
    except signing.BadSignature:
        return False

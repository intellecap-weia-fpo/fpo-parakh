from functools import wraps

from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.shortcuts import get_user_by_token

from fpo.models import FPO


def document_access(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "").split()
        if header:
            try:
                user = (
                    get_user_by_token(header[1], request)
                    if len(header) == 2 and header[0].lower() == "bearer"
                    else None
                )
            except JSONWebTokenError:
                user = None
        else:
            user = request.user if request.user.is_authenticated else None
            if user is not None:
                # Existing web uploader uses a session and must still pass CSRF.
                rejected = CsrfViewMiddleware(lambda r: None).process_view(request, lambda r: None, (), {})
                if rejected is not None:
                    return rejected
        if user is None:
            return JsonResponse({"error": "Please sign in before uploading a document."}, status=401)
        try:
            fpo_id = int(request.POST.get("fpo_id", ""))
        except (ValueError, TypeError):
            return JsonResponse({"error": "A valid FPO ID is required."}, status=400)
        fpo = FPO.objects.filter(pk=fpo_id).first()
        if fpo is None or not (
            user.is_staff
            or user.is_superuser
            or fpo.created_by_id == user.pk
            or fpo.members.filter(user=user, is_active=True, role="admin").exists()
        ):
            return JsonResponse({"error": "You do not have permission to upload for this FPO."}, status=403)
        upload = request.FILES.get("document")
        if upload is not None and upload.size > 10 * 1024 * 1024:
            return JsonResponse({"error": "Choose a document no larger than 10 MB."}, status=400)
        request.user = user
        return view(request, *args, **kwargs)

    return wrapper

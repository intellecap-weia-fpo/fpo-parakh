from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
from graphene_django.views import GraphQLView
from django.conf.urls.i18n import i18n_patterns
from django.shortcuts import render, redirect

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/", admin.site.urls),
    path("auth/", include("auth_app.urls")),
    path("manage/", include("management.urls")),
    path("fpo/", include("fpo.urls")),
    path("graphql/", csrf_exempt(GraphQLView.as_view(graphiql=settings.DEBUG))),
    path("neo/", include("neo.urls")),
    path("settings/", lambda request: root_settings_view(request), name="root_settings"),
    path("", lambda request: redirect("/fpo/"), name="home"),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


def root_settings_view(request):
    """Root level settings view that renders the settings template"""
    return render(request, "management/settings.html", {
        "page_title": "Settings",
        "page_subtitle": "System settings and configuration"
    })

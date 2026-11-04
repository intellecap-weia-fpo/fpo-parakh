from django_components import Component, register
from django.utils.translation import gettext_lazy as _


@register("breadcrumb")
class Breadcrumb(Component):
    template = """
    {% if breadcrumbs %}
    <nav class="flex mb-3" aria-label="Breadcrumb">
      <ol class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm max-w-full overflow-hidden">
        {% for crumb in breadcrumbs %}
          <li class="flex items-center max-w-full">
            {% if not forloop.first %}
              <i class="fa fa-chevron-right text-xs text-muted-foreground mx-2"></i>
            {% endif %}
            {% if crumb.url and not forloop.last %}
              <a href="{{ crumb.url }}" class="text-muted-foreground hover:text-foreground transition-colors inline-block truncate max-w-[10rem] sm:max-w-[16rem] md:max-w-none">
                {{ crumb.title }}
              </a>
            {% else %}
              <span class="text-foreground font-medium inline-block truncate max-w-[12rem] sm:max-w-[20rem] md:max-w-none">{{ crumb.title }}</span>
            {% endif %}
          </li>
        {% endfor %}
      </ol>
    </nav>
    {% endif %}
    """

    def get_template_data(self, args, kwargs, slots, context):
        current_path = kwargs.get("path") or context.get("request").path
        breadcrumbs = self.generate_breadcrumbs(current_path, context)

        return {
            "breadcrumbs": breadcrumbs,
            "current_path": current_path,
        }

    def generate_breadcrumbs(self, current_path, context):
        """Generate breadcrumbs dynamically based on current path and app configuration"""

        # For single-level URLs like /cohorts/, /courses/, /users/, only show the title
        path_parts = [part for part in current_path.strip("/").split("/") if part]
        if len(path_parts) == 1:
            part = path_parts[0]
            
            # Handle specific path part translations
            translation_map = {
                "manage": _("Manage"),
                "certificate-templates": _("Certificate Templates"),
                "certificates": _("Certificates"),
                "users": _("Users"),
                "user-management": _("User Management"),
                "settings": _("Settings"),
                "cohorts": _("Cohorts"),
                "courses": _("Courses"),
                "discussions": _("Discussions"),
                "startups": _("Startups"),
                "mentors": _("Mentor Management"),
                "create": _("Create"),
                "edit": _("Edit"),
                "delete": _("Delete"),
                "preview": _("Preview"),
                "duplicate": _("Duplicate"),
            }
            
            title = translation_map.get(part, _(part.replace("-", " ").replace("_", " ").title()))
            return [{"title": title, "url": None}]

        # Import app configuration from Django settings
        from django.conf import settings

        # Get apps configuration
        apps_config = getattr(settings, "APPS", [])

        # Find matching app by URL
        for app in apps_config:
            app_url = app.get("url", "")
            if current_path.startswith(app_url) and app_url != "/":  # Don't match root for everything
                # For FPO app, skip adding the app name breadcrumb
                if current_path.startswith("/fpo/"):
                    breadcrumbs = []
                else:
                    # Start breadcrumbs with app root
                    breadcrumbs = [{"title": app["name"], "url": app_url if current_path != app_url else None}]

                # Generate dynamic breadcrumbs for routes within the app
                dynamic_breadcrumbs = self.generate_dynamic_breadcrumbs(current_path, app_url, context)
                breadcrumbs.extend(dynamic_breadcrumbs)

                return breadcrumbs

        # Fallback to path-based breadcrumbs if no app match
        return self.generate_fallback_breadcrumbs(current_path, context)

    def generate_fallback_breadcrumbs(self, current_path, context):
        """Generate basic breadcrumbs when no app match is found"""
        path_parts = [part for part in current_path.strip("/").split("/") if part]

        if not path_parts:
            return []

        # For FPO pages, skip the "fpo" part from breadcrumbs
        if current_path.startswith("/fpo/") and path_parts[0] == "fpo":
            path_parts = path_parts[1:]
            if not path_parts:
                return []

        # For single-level URLs like /cohorts/, only show the title without parent links
        if len(path_parts) == 1:
            part = path_parts[0]
            
            # Handle specific path part translations
            translation_map = {
                "manage": _("Manage"),
                "certificate-templates": _("Certificate Templates"),
                "certificates": _("Certificates"),
                "users": _("Users"),
                "user-management": _("User Management"),
                "settings": _("Settings"),
                "cohorts": _("Cohorts"),
                "courses": _("Courses"),
                "discussions": _("Discussions"),
                "startups": _("Startups"),
                "mentors": _("Mentor Management"),
                "create": _("Create"),
                "edit": _("Edit"),
                "delete": _("Delete"),
                "preview": _("Preview"),
                "duplicate": _("Duplicate"),
            }
            
            title = translation_map.get(part, _(part.replace("-", " ").replace("_", " ").title()))
            return [{"title": title, "url": None}]

        # For multi-level URLs, generate full breadcrumb trail
        breadcrumbs = []
        # If we removed "fpo" from path, start URL from /fpo/ instead of /
        if current_path.startswith("/fpo/"):
            current_url = "/fpo/"
        else:
            current_url = "/"

        for i, part in enumerate(path_parts):
            current_url += part + "/"
            is_last = i == len(path_parts) - 1

            # Handle specific path part translations
            translation_map = {
                "manage": _("Manage"),
                "certificate-templates": _("Certificate Templates"),
                "certificates": _("Certificates"),
                "users": _("Users"),
                "user-management": _("User Management"),
                "settings": _("Settings"),
                "cohorts": _("Cohorts"),
                "courses": _("Courses"),
                "discussions": _("Discussions"),
                "startups": _("Startups"),
                "mentors": _("Mentor Management"),
                "create": _("Create"),
                "edit": _("Edit"),
                "delete": _("Delete"),
                "preview": _("Preview"),
                "duplicate": _("Duplicate"),
            }

            title = translation_map.get(part, _(part.replace("-", " ").replace("_", " ").title()))
            breadcrumbs.append({"title": title, "url": current_url if not is_last else None})

        return breadcrumbs

    def generate_dynamic_breadcrumbs(self, current_path, app_prefix, context):
        """Generate breadcrumbs for dynamic routes not explicitly in the menu"""
        breadcrumbs = []

        # Remove app prefix to get relative path
        relative_path = current_path[len(app_prefix) :].strip("/")
        path_parts = [part for part in relative_path.split("/") if part]

        if not path_parts:
            return breadcrumbs

        # Special handling for FPO routes to produce:
        # Manage FPO -> <FPO Name> -> Submission YYYY - YY
        if current_path.startswith("/fpo/fpos/"):
            # Handle FPO list page: /fpo/fpos/ -> Manage FPO
            if current_path == "/fpo/fpos/" or current_path == "/fpo/fpos":
                breadcrumbs.append({"title": _("Manage FPO"), "url": None})
                return breadcrumbs
            from fpo.models import FPO, YearlySubmission

            def format_fin_year(fy):
                try:
                    first, second = fy.split("-")
                    # Use last two digits of the second year
                    return f"{first} - {second[-2:]}"
                except Exception:
                    return fy

            # Add "Manage FPO" as the first breadcrumb for all FPO detail pages
            breadcrumbs.append({
                "title": _("Manage FPO"),
                "url": "/fpo/fpos/",
            })

            # Try get FPO object from context to avoid extra DB hits
            fpo_obj = context.get("fpo")
            fpo_id = None
            if len(path_parts) >= 1 and path_parts[0].isdigit():
                fpo_id = int(path_parts[0])
                if fpo_obj is None or getattr(fpo_obj, "id", None) != fpo_id:
                    try:
                        fpo_obj = FPO.objects.only("id", "name").get(pk=fpo_id)
                    except FPO.DoesNotExist:
                        fpo_obj = None

            # If we have an FPO, add it as the next crumb
            if fpo_obj is not None:
                breadcrumbs.append({
                    "title": fpo_obj.name,
                    "url": f"/fpo/fpos/{fpo_obj.id}/",
                })

            # Handle submission detail: /fpo/fpos/<id>/submissions/<submission_id>/
            if len(path_parts) >= 3 and path_parts[1] == "submissions" and path_parts[2].isdigit():
                submission = context.get("submission")
                if submission is None or getattr(submission, "id", None) != int(path_parts[2]):
                    # Fetch minimal fields if not present
                    try:
                        submission = YearlySubmission.objects.only("id", "financial_year").get(
                            pk=int(path_parts[2]), fpo_id=fpo_id
                        )
                    except YearlySubmission.DoesNotExist:
                        submission = None

                if submission is not None:
                    # If there's a sub-action, make submission clickable
                    submission_url = f"/fpo/fpos/{fpo_id}/submissions/{submission.id}/" if len(path_parts) >= 4 else None
                    breadcrumbs.append({
                        "title": f"{_('Submission')} {format_fin_year(submission.financial_year)}",
                        "url": submission_url,
                    })
                else:
                    # Fallback: generic title
                    breadcrumbs.append({"title": "Submission", "url": None})

                # Optional sub-actions like edit/delete
                if len(path_parts) >= 4:
                    action = path_parts[3]
                    if action in ("edit", "delete"):
                        breadcrumbs.append({"title": action.title(), "url": None})

                return breadcrumbs

            # FPO detail page: /fpo/fpos/<id>/
            if len(path_parts) == 1 and fpo_obj is not None:
                # Current page is the FPO itself
                breadcrumbs[-1]["url"] = None  # Make current crumb non-clickable
                return breadcrumbs

            # Submissions list: /fpo/fpos/<id>/submissions/
            if len(path_parts) >= 2 and path_parts[1] == "submissions":
                breadcrumbs.append({"title": "Submissions", "url": None})
                return breadcrumbs

            # Handle other FPO sub-pages like upload-document, add-member, etc.
            if len(path_parts) >= 2 and fpo_obj is not None:
                action = path_parts[1]
                action_title_map = {
                    "upload-document": _("Upload Document"),
                    "add-member": _("Add Member"),
                    "recalculate-scores": _("Recalculate Scores"),
                }
                title = action_title_map.get(action, _(action.replace("-", " ").replace("_", " ").title()))
                breadcrumbs.append({"title": title, "url": None})
                return breadcrumbs

        # Handle common patterns dynamically
        if len(path_parts) >= 1:
            # Resource-based routes (e.g., users, settings)
            resource = path_parts[0]
            resource_title = resource.replace("_", " ").title()

            # Default behavior for all apps/resources
            if len(path_parts) == 1:
                # Handle specific resource translations
                resource_translation_map = {
                    "certificate-templates": _("Certificate Templates"),
                    "users": _("Users"),
                    "user-management": _("User Management"),
                    "settings": _("Settings"),
                    "cohorts": _("Cohorts"),
                    "courses": _("Courses"),
                    "startups": _("Startups"),
                    "mentors": _("Mentor Management"),
                }
                
                translated_title = resource_translation_map.get(resource, _(resource_title))
                # /manage/users/ -> Users (single title, no parent breadcrumb)
                breadcrumbs.append({"title": translated_title, "url": None})
            elif len(path_parts) >= 2:
                # Handle specific resource translations for multi-level breadcrumbs too
                resource_translation_map = {
                    "certificate-templates": _("Certificate Templates"),
                    "users": _("Users"),
                    "settings": _("Settings"),
                    "cohorts": _("Cohorts"),
                    "courses": _("Courses"),
                    "startups": _("Startups"),
                    "mentors": _("Mentor Management"),
                }
                
                translated_title = resource_translation_map.get(resource, _(resource_title))
                # Add the resource as a clickable breadcrumb
                breadcrumbs.append({"title": translated_title, "url": f"{app_prefix}{resource}/"})

                action_or_id = path_parts[1]

                if action_or_id == "create":
                    # /manage/users/create/ -> Create User
                    # Handle special cases for create actions
                    if resource == "certificate-templates":
                        breadcrumbs.append({"title": _("Create Certificate Template"), "url": None})
                    else:
                        breadcrumbs.append({"title": _("Create %(resource)s") % {"resource": resource_title.rstrip('s')}, "url": None})
                elif action_or_id.isdigit():
                    # /manage/users/123/ -> User Details
                    # Get more context from the view if available
                    page_title = context.get("page_title")
                    if page_title:
                        detail_title = page_title
                    else:
                        detail_title = _("%(resource)s Details") % {"resource": resource_title.rstrip('s')}

                    if len(path_parts) == 2:
                        breadcrumbs.append({"title": detail_title, "url": None})
                    elif len(path_parts) >= 3:
                        # Add detail page as clickable
                        breadcrumbs.append({"title": detail_title, "url": f"{app_prefix}{resource}/{action_or_id}/"})

                        # Handle sub-actions like edit, delete
                        sub_action = path_parts[2]
                        if sub_action == "edit":
                            if resource == "certificate-templates":
                                breadcrumbs.append({"title": _("Edit Certificate Template"), "url": None})
                            else:
                                breadcrumbs.append({"title": _("Edit %(resource)s") % {"resource": resource_title.rstrip('s')}, "url": None})
                        elif sub_action == "delete":
                            if resource == "certificate-templates":
                                breadcrumbs.append({"title": _("Delete Certificate Template"), "url": None})
                            else:
                                breadcrumbs.append({"title": _("Delete %(resource)s") % {"resource": resource_title.rstrip('s')}, "url": None})
                        else:
                            breadcrumbs.append({"title": _(sub_action.replace("_", " ").title()), "url": None})
                else:
                    # Other actions
                    breadcrumbs.append({"title": _(action_or_id.replace("_", " ").title()), "url": None})

        return breadcrumbs

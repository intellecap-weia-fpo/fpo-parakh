from django.db import migrations, models


GENERIC_SITE_NAME = "Neo ERP"
GENERIC_PRIMARY_COLOR = "oklch(0.5770 0.2450 27.3250)"
FPO_SITE_NAME = "FPO Admin App"
FPO_PRIMARY_COLOR = "#004687"


def restore_fpo_branding(apps, schema_editor):
    site_configuration = apps.get_model("neo", "SiteConfiguration")
    site_configuration.objects.filter(
        site_name=GENERIC_SITE_NAME,
        primary_color=GENERIC_PRIMARY_COLOR,
    ).update(
        site_name=FPO_SITE_NAME,
        primary_color=FPO_PRIMARY_COLOR,
    )


def restore_generic_branding(apps, schema_editor):
    site_configuration = apps.get_model("neo", "SiteConfiguration")
    site_configuration.objects.filter(
        site_name=FPO_SITE_NAME,
        primary_color=FPO_PRIMARY_COLOR,
    ).update(
        site_name=GENERIC_SITE_NAME,
        primary_color=GENERIC_PRIMARY_COLOR,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("neo", "0007_siteconfiguration_enabled_apps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="site_name",
            field=models.CharField(default=FPO_SITE_NAME, max_length=255),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="primary_color",
            field=models.CharField(
                default=FPO_PRIMARY_COLOR,
                help_text="Primary theme color (hex)",
                max_length=50,
            ),
        ),
        migrations.RunPython(restore_fpo_branding, restore_generic_branding),
    ]

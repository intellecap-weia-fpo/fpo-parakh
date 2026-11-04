from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def approve_existing_fpos(apps, schema_editor):
    FPO = apps.get_model("fpo", "FPO")
    FPO.objects.all().update(verification_status="approved")


class Migration(migrations.Migration):
    dependencies = [
        ("fpo", "0017_delete_financialdetailssubmission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="fpo",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending verification"),
                    ("approved", "Approved"),
                    ("rejected", "Changes requested"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="fpo",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fpo",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fpo_verification_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="fpo",
            name="verification_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AlterModelOptions(
            name="fpo",
            options={
                "ordering": ["name"],
                "permissions": [("verify_fpo", "Can approve or reject FPO verification")],
                "verbose_name": "FPO",
                "verbose_name_plural": "FPOs",
            },
        ),
        migrations.RunPython(approve_existing_fpos, migrations.RunPython.noop),
    ]

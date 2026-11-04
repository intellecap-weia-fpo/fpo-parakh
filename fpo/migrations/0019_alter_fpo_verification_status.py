from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fpo", "0018_fpo_verification_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fpo",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending verification"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]

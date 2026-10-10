from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("streaming", "0002_sensorlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="producer_connection_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
    ]

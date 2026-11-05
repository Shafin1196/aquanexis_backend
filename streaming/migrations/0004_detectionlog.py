from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("streaming", "0003_device_producer_connection_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="DetectionLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("class_id", models.IntegerField()),
                ("class_name", models.CharField(max_length=100)),
                ("confidence", models.FloatField()),
                ("track_id", models.IntegerField(blank=True, null=True)),
                ("x1", models.FloatField()),
                ("y1", models.FloatField()),
                ("x2", models.FloatField()),
                ("y2", models.FloatField()),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="detections",
                        to="streaming.device",
                    ),
                ),
            ],
        ),
    ]

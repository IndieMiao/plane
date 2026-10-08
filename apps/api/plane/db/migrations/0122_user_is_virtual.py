from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("db", "0121_alter_estimate_type")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_virtual",
            field=models.BooleanField(default=False),
        ),
    ]

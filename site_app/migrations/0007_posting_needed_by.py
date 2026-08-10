from django.db import migrations, models


class Migration(migrations.Migration):
    """Give a posting a sense of when it stops being useful.

    Nullable on purpose. Plenty of help has no deadline, and forcing a date
    would make people invent one — which would be worse than no signal at all,
    because an invented deadline outranks a real one on the board.
    """

    dependencies = [("site_app", "0006_posting")]

    operations = [
        migrations.AddField(
            model_name="posting",
            name="needed_by",
            field=models.DateField(blank=True, null=True),
        ),
    ]

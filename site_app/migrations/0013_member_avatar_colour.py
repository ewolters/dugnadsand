from django.db import migrations, models


class Migration(migrations.Migration):
    """A colour preference for a member's generated mark.

    No choices= on the field on purpose: a choices edit requires a migration,
    and which six colours are offered is a design decision that should not.
    """

    dependencies = [("site_app", "0012_manifest_receipt_token")]

    operations = [
        migrations.AddField(
            model_name="member",
            name="avatar_colour",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]

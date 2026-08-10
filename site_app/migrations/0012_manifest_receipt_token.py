from django.db import migrations, models


class Migration(migrations.Migration):
    """Keep the receipt capability on the manifest instead of minting per view.

    The QR is printed and travels with the goods, so it must be stable. The
    previous version issued a token every time the document was rendered,
    leaving one live receipt link behind per page view.
    """

    dependencies = [("site_app", "0011_social")]

    operations = [
        migrations.AddField(
            model_name="manifest",
            name="receipt_token",
            field=models.CharField(blank=True, editable=False, max_length=128),
        ),
    ]

"""Offering becomes Posting, and gains a direction.

Half the things on the board are not offerings — somebody asking for a ride is
posting a need, and a model called Offering could only ever hold one direction.
Written by hand because the autodetector reads a renamed model plus renamed
foreign keys as a set of new NOT NULL columns, and would have dropped the data
had there been any.

Postgres carries row-level security policies through a table rename, so the
tenant isolation from 0003 follows `site_app_offering` to `site_app_posting`
untouched. There is a test asserting it survived.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("site_app", "0005_setuplink"),
    ]

    operations = [
        migrations.RenameModel(old_name="Offering", new_name="Posting"),
        migrations.RenameField(
            model_name="claim", old_name="offering", new_name="posting"),
        migrations.RenameField(
            model_name="contribution", old_name="offering", new_name="posting"),
        migrations.AddField(
            model_name="posting",
            name="kind",
            # Everything that existed before this migration was an offering.
            field=models.CharField(
                choices=[("offer", "Offering"), ("need", "Need")],
                default="offer", max_length=8),
        ),
        migrations.AlterField(
            model_name="posting",
            name="member",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="postings", to="site_app.member"),
        ),
        migrations.AlterField(
            model_name="claim",
            name="posting",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="claims", to="site_app.posting"),
        ),
        migrations.AlterField(
            model_name="contribution",
            name="posting",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contributions", to="site_app.posting"),
        ),
    ]

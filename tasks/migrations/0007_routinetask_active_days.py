from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_task_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='routinetask',
            name='active_days',
            field=models.PositiveSmallIntegerField(default=127),
        ),
    ]
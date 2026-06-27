from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_routinetask_active_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='position',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name='task',
            options={'ordering': ['position', 'created_at']},
        ),
    ]
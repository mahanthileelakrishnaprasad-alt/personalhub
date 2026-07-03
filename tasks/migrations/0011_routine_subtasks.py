from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0010_upgrades'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RoutineSubtask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=300)),
                ('position', models.PositiveIntegerField(default=0)),
                ('routine_task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subtasks', to='tasks.routinetask')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routine_subtasks', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['position']},
        ),
        migrations.CreateModel(
            name='RoutineSubtaskLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('completed', models.BooleanField(default=False)),
                ('subtask', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='tasks.routinesubtask')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routine_subtask_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-date'], 'unique_together': {('subtask', 'date')}},
        ),
    ]
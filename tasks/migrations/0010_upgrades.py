from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0009_folders_softdelete_positions'),
    ]

    operations = [
        # UserProfile upgrades
        migrations.AddField(model_name='userprofile', name='avatar_url', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='userprofile', name='bio', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='userprofile', name='theme', field=models.CharField(default='dark', max_length=10)),

        # Task upgrades
        migrations.AddField(model_name='task', name='due_date', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='task', name='parent', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subtasks', to='tasks.task')),
        migrations.AddField(model_name='task', name='is_recurring', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='task', name='recur_days', field=models.PositiveSmallIntegerField(default=0)),

        # TransactionCategory budget
        migrations.AddField(model_name='transactioncategory', name='monthly_budget', field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
    ]
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('player', '0004_coachtournamentteamparticipation'),
    ]

    operations = [
        migrations.CreateModel(
            name='GpsMetric',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=100)),
                ('total_distance', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('metres_per_minute', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('high_speed_running', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('accelerations', models.IntegerField(blank=True, null=True)),
                ('decelerations', models.IntegerField(blank=True, null=True)),
                ('hml_distance', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('sprints', models.IntegerField(blank=True, null=True)),
                ('sprint_distance', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gps_metrics', to='player.match')),
            ],
            options={
                'verbose_name': 'Métrica GPS',
                'verbose_name_plural': 'Métricas GPS',
                'ordering': ['name'],
            },
        ),
    ]

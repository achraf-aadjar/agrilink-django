import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agrilink', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('buyer_name',   models.CharField(max_length=100)),
                ('buyer_phone',  models.CharField(blank=True, max_length=20)),
                ('buyer_region', models.CharField(default='Dakar', max_length=100)),
                ('quantity',     models.IntegerField()),
                ('price_per_kg', models.IntegerField()),
                ('total',        models.IntegerField()),
                ('status',       models.CharField(
                    choices=[('pending', 'En attente'), ('accepted', 'Acceptée'), ('rejected', 'Refusée')],
                    default='pending', max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('listing', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='offers',
                    to='agrilink.listing',
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]

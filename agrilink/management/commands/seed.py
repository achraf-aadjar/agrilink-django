from django.core.management.base import BaseCommand
from agrilink.models import Farmer, Listing, CreditApplication, InsurancePolicy
from datetime import date


class Command(BaseCommand):
    help = 'Seed database with demo data'

    def handle(self, *args, **kwargs):
        if Farmer.objects.exists():
            self.stdout.write('Already seeded.')
            return

        farmer = Farmer.objects.create(
            name='Mamadou Diallo',
            phone='+221 77 000 00 01',
            region='Kaolack',
            crops=['Arachide', 'Mil'],
            surface=3.5,
            is_verified=True,
            agri_score=78,
            total_revenue=3947000,
            total_transactions=47,
            saved_vs_intermediaries=892000,
        )

        farmers_data = [
            ('Fatou Sow', '+221 77 111 22 33', 'Thiès', 2.0, True),
            ('Ibrahim Ndiaye', '+221 77 222 33 44', 'Ziguinchor', 5.0, True),
            ('Aissatou Ba', '+221 77 333 44 55', 'Saint-Louis', 1.5, False),
            ('Moussa Diop', '+221 77 444 55 66', 'Tambacounda', 4.0, True),
        ]
        other_farmers = []
        for name, phone, region, surface, verified in farmers_data:
            f = Farmer.objects.create(
                name=name, phone=phone, region=region,
                surface=surface, is_verified=verified, agri_score=65
            )
            other_farmers.append(f)

        listings_data = [
            (farmer, 'Arachide', '🥜', 2500, 'Grade A', 370, 385, 'Kaolack',
             'https://images.unsplash.com/photo-1590779033100-9f60a05a013d?w=600&q=80'),
            (other_farmers[0], 'Mangue', '🥭', 800, 'Grade A', 140, 150, 'Thiès',
             'https://images.unsplash.com/photo-1553279768-865429fa0078?w=600&q=80'),
            (other_farmers[1], 'Tomate', '🍅', 1200, 'Grade B', 260, 280, 'Ziguinchor',
             'https://images.unsplash.com/photo-1546094096-0df4bcaaa337?w=600&q=80'),
            (other_farmers[2], 'Oignon', '🧅', 3000, 'Standard', 290, 320, 'Saint-Louis',
             'https://images.unsplash.com/photo-1518977956812-cd3dbadaaf31?w=600&q=80'),
            (other_farmers[3], 'Mil', '🌾', 5000, 'Grade A', 180, 195, 'Tambacounda',
             'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=600&q=80'),
        ]

        for f, crop, emoji, qty, quality, price, mkt, region, photo in listings_data:
            Listing.objects.create(
                farmer=f, crop=crop, emoji=emoji, quantity=qty,
                quality=quality, price_per_kg=price, market_price=mkt,
                region=region, available=date(2026, 6, 1),
                photo_url=photo, views=int(qty * 0.3),
            )

        CreditApplication.objects.create(
            farmer=farmer, amount=150000, duration=6,
            purpose='Semences & engrais', purpose_emoji='🌱',
            imf_name='CNCAS', rate=6.0, status='active',
        )
        CreditApplication.objects.create(
            farmer=farmer, amount=75000, duration=3,
            purpose='Main d\'œuvre récolte', purpose_emoji='👷',
            imf_name='PAMECAS', rate=8.0, status='repaid',
        )

        InsurancePolicy.objects.create(
            farmer=farmer, crop='Arachide', crop_emoji='🥜',
            surface=3.5, season='Hivernage 2026',
            premium=42000, coverage=336000,
            risk_index=34, rainfall_30d=45.2,
        )

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))

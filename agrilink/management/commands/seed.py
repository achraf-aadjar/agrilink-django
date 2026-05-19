from django.core.management.base import BaseCommand
from agrilink.models import Farmer, Listing, CreditApplication, InsurancePolicy, Offer
from datetime import date


FARMERS = [
    dict(name='Mamadou Diallo',   phone='+221 77 000 00 01', region='Kaolack',
         crops=['Arachide', 'Mil'], surface=4.5, is_verified=True,  agri_score=87,
         total_revenue=3947000, total_transactions=47, saved_vs_intermediaries=892000),
    dict(name='Fatou Sow',        phone='+221 77 111 22 33', region='Thiès',
         crops=['Tomate', 'Oignon'], surface=2.0, is_verified=True, agri_score=74,
         total_revenue=1820000, total_transactions=31, saved_vs_intermediaries=340000),
    dict(name='Ibrahima Ba',      phone='+221 77 222 33 44', region='Saint-Louis',
         crops=['Riz', 'Tomate'], surface=6.0, is_verified=True,  agri_score=82,
         total_revenue=5230000, total_transactions=58, saved_vs_intermediaries=1100000),
    dict(name='Aminata Diop',     phone='+221 77 333 44 55', region='Ziguinchor',
         crops=['Mangue', 'Anacarde'], surface=3.0, is_verified=True, agri_score=78,
         total_revenue=2640000, total_transactions=29, saved_vs_intermediaries=520000),
    dict(name='Moussa Traoré',    phone='+221 77 444 55 66', region='Tambacounda',
         crops=['Maïs', 'Sorgho'], surface=5.5, is_verified=False, agri_score=65,
         total_revenue=1450000, total_transactions=18, saved_vs_intermediaries=210000),
    dict(name='Aïssatou Fall',    phone='+221 77 555 66 77', region='Fatick',
         crops=['Arachide', 'Niébé'], surface=2.8, is_verified=True, agri_score=71,
         total_revenue=2180000, total_transactions=24, saved_vs_intermediaries=390000),
    dict(name='Omar Seck',        phone='+221 77 666 77 88', region='Louga',
         crops=['Oignon', 'Mil'], surface=3.2, is_verified=True,  agri_score=76,
         total_revenue=2750000, total_transactions=33, saved_vs_intermediaries=480000),
    dict(name='Mariama Baldé',    phone='+221 77 777 88 99', region='Dakar',
         crops=['Maraîchage'], surface=1.0, is_verified=False, agri_score=61,
         total_revenue=980000,  total_transactions=15, saved_vs_intermediaries=150000),
]

LISTINGS = [
    # farmer_idx, crop, emoji, qty, quality, price, market, region, description, photo
    (0, 'Arachide',  '🥜', 2500, 'Grade A', 370, 385, 'Kaolack',
     'Arachide huilerie, séchée naturellement. Certification OCA disponible.',
     'https://images.unsplash.com/photo-1590779033100-9f60a05a013d?w=600&q=80'),
    (0, 'Mil',       '🌾', 1800, 'Grade A', 182, 195, 'Kaolack',
     'Mil local, variété souna. Idéal pour la fabrication de couscous et bouillie.',
     'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=600&q=80'),
    (1, 'Tomate',    '🍅', 900,  'Grade A', 265, 280, 'Thiès',
     'Tomate ronde, culture sous abri. Très peu de pertes post-récolte.',
     'https://images.unsplash.com/photo-1546094096-0df4bcabd337?w=600&q=80'),
    (1, 'Oignon',    '🧅', 2200, 'Grade B', 295, 320, 'Thiès',
     'Oignon violet de Thiès, conservation longue durée jusqu\'à 4 mois.',
     'https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=600&q=80'),
    (2, 'Tomate',    '🍅', 1400, 'Grade B', 250, 280, 'Saint-Louis',
     'Tomate cerise, production irriguée. Disponible en vrac ou en caisses.',
     'https://images.unsplash.com/photo-1592924357228-3b9b5b5b5b5b?w=600&q=80'),
    (2, 'Oignon',    '🧅', 3500, 'Grade A', 305, 320, 'Saint-Louis',
     'Oignon blanc de Saint-Louis, récolte hivernage 2026. Qualité export.',
     'https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=600&q=80'),
    (3, 'Mangue',    '🥭', 1200, 'Grade A', 138, 150, 'Ziguinchor',
     'Mangue Kent et Keitt, arboriculture traditionnelle. Saveur authentique.',
     'https://images.unsplash.com/photo-1553279768-865429fa0078?w=600&q=80'),
    (3, 'Anacarde',  '🌰', 800,  'Grade A', 420, 450, 'Ziguinchor',
     'Noix de cajou brutes, poids spécifique 50+ lbs. Prêtes pour transformation.',
     'https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?w=600&q=80'),
    (4, 'Maïs',      '🌽', 4000, 'Standard', 155, 165, 'Tambacounda',
     'Maïs jaune, variété améliorée. Humidité 14%, prêt pour stockage.',
     'https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=600&q=80'),
    (4, 'Sorgho',    '🌾', 2800, 'Grade B',  145, 160, 'Tambacounda',
     'Sorgho rouge, récolte octobre 2026. Excellent pour alimentation animale.',
     'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=600&q=80'),
    (5, 'Arachide',  '🥜', 1600, 'Grade B',  355, 385, 'Fatick',
     'Arachide de bouche, triée manuellement. Graines uniformes calibre 40/50.',
     'https://images.unsplash.com/photo-1590779033100-9f60a05a013d?w=600&q=80'),
    (5, 'Niébé',     '🫘', 700,  'Grade A',  310, 330, 'Fatick',
     'Niébé blanc local, excellent pour la fabrication de thiéboudienne et soupes.',
     'https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=600&q=80'),
    (6, 'Oignon',    '🧅', 4500, 'Grade A',  300, 320, 'Louga',
     'Oignon de Louga, incontournable du marché sénégalais. Stock important.',
     'https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=600&q=80'),
    (6, 'Mil',       '🌾', 3200, 'Grade B',  178, 195, 'Louga',
     'Mil sanio, variété locale très appréciée dans le Sahel. Récolte fraîche.',
     'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=600&q=80'),
    (7, 'Tomate',    '🍅', 500,  'Grade A',  272, 280, 'Dakar',
     'Maraîchage péri-urbain, production sous filets anti-insectes. Très frais.',
     'https://images.unsplash.com/photo-1546094096-0df4bcabd337?w=600&q=80'),
]

OFFERS_SEED = [
    # listing_idx, buyer_name, buyer_phone, buyer_region, qty, price_per_kg
    (0,  'Alioune Sarr',      '+221 76 412 33 01', 'Dakar',        800,  372),
    (0,  'Rokhaya Guèye',     '+221 77 891 22 14', 'Thiès',        1200, 368),
    (2,  'Cheikh Mbacké',     '+221 77 234 56 78', 'Dakar',        400,  270),
    (6,  'Coumba Diallo',     '+221 76 543 21 98', 'Ziguinchor',   600,  140),
    (8,  'Malick Faye',       '+221 78 765 43 21', 'Tambacounda',  2000, 158),
    (12, 'Binta Kouyaté',     '+221 77 321 87 65', 'Saint-Louis',  1500, 302),
]


class Command(BaseCommand):
    help = 'Seed database with rich demo data (wipes existing data)'

    def handle(self, *args, **kwargs):
        # Wipe everything for a clean reseed
        Offer.objects.all().delete()
        CreditApplication.objects.all().delete()
        InsurancePolicy.objects.all().delete()
        Listing.objects.all().delete()
        Farmer.objects.all().delete()
        self.stdout.write('Cleared existing data.')

        # Create farmers
        farmers = []
        for fd in FARMERS:
            f = Farmer.objects.create(**fd)
            farmers.append(f)
        self.stdout.write(f'Created {len(farmers)} farmers.')

        # Create listings
        listings = []
        for (fi, crop, emoji, qty, quality, price, mkt, region, desc, photo) in LISTINGS:
            l = Listing.objects.create(
                farmer=farmers[fi], crop=crop, emoji=emoji,
                quantity=qty, quality=quality,
                price_per_kg=price, market_price=mkt,
                region=region, description=desc,
                available=date(2026, 6, 15),
                photo_url=photo,
                views=max(12, qty // 8),
            )
            listings.append(l)
        self.stdout.write(f'Created {len(listings)} listings.')

        # Seed offers (activity on the platform)
        for (li, bname, bphone, bregion, qty, price) in OFFERS_SEED:
            Offer.objects.create(
                listing=listings[li],
                buyer_name=bname, buyer_phone=bphone, buyer_region=bregion,
                quantity=qty, price_per_kg=price, total=qty * price,
                status='pending',
            )
        self.stdout.write(f'Created {len(OFFERS_SEED)} offers.')

        # Credit history for demo farmer
        CreditApplication.objects.create(
            farmer=farmers[0], amount=150000, duration=6,
            purpose='Semences & engrais', purpose_emoji='🌱',
            imf_name='CNCAS', rate=6.0, status='active',
        )
        CreditApplication.objects.create(
            farmer=farmers[0], amount=75000, duration=3,
            purpose="Main d'œuvre récolte", purpose_emoji='👷',
            imf_name='PAMECAS', rate=8.0, status='repaid',
        )

        # Insurance for demo farmer
        InsurancePolicy.objects.create(
            farmer=farmers[0], crop='Arachide', crop_emoji='🥜',
            surface=4.5, season='Hivernage 2026',
            premium=54000, coverage=432000,
            risk_index=34, rainfall_30d=45.2,
        )

        self.stdout.write(self.style.SUCCESS(
            f'Seeded: {len(farmers)} farmers · {len(listings)} listings · '
            f'{len(OFFERS_SEED)} offers · 2 credits · 1 insurance'
        ))

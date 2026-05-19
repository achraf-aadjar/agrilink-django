from django.db import models


class Farmer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, unique=True)
    region = models.CharField(max_length=100)
    crops = models.JSONField(default=list)
    surface = models.FloatField(default=1.0)
    is_verified = models.BooleanField(default=False)
    agri_score = models.IntegerField(default=70)
    total_revenue = models.IntegerField(default=0)
    total_transactions = models.IntegerField(default=0)
    saved_vs_intermediaries = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Listing(models.Model):
    QUALITY_CHOICES = [('Grade A', 'Grade A'), ('Grade B', 'Grade B'), ('Standard', 'Standard')]

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='listings')
    crop = models.CharField(max_length=100)
    emoji = models.CharField(max_length=10, default='🌾')
    quantity = models.IntegerField()
    unit = models.CharField(max_length=20, default='kg')
    quality = models.CharField(max_length=20, choices=QUALITY_CHOICES, default='Grade A')
    price_per_kg = models.IntegerField()
    market_price = models.IntegerField()
    description = models.TextField(blank=True)
    region = models.CharField(max_length=100)
    available = models.DateField()
    photo_url = models.URLField(blank=True)
    views = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def savings_pct(self):
        if self.market_price > 0:
            return round(((self.market_price - self.price_per_kg) / self.market_price) * 100)
        return 0

    def __str__(self):
        return f"{self.crop} - {self.farmer.name}"


class CreditApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('active', 'En cours'),
        ('repaid', 'Remboursé'),
        ('rejected', 'Rejeté'),
    ]
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='credits')
    amount = models.IntegerField()
    duration = models.IntegerField(help_text='Durée en mois')
    purpose = models.CharField(max_length=200)
    purpose_emoji = models.CharField(max_length=10, default='🌱')
    imf_name = models.CharField(max_length=100)
    rate = models.FloatField(default=8.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def monthly_payment(self):
        r = self.rate / 100 / 12
        if r == 0:
            return self.amount // self.duration
        return round(self.amount * r / (1 - (1 + r) ** (-self.duration)))

    def __str__(self):
        return f"Crédit {self.amount} FCFA - {self.farmer.name}"


class InsurancePolicy(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='insurances')
    crop = models.CharField(max_length=100)
    crop_emoji = models.CharField(max_length=10, default='🌾')
    surface = models.FloatField()
    season = models.CharField(max_length=50)
    premium = models.IntegerField()
    coverage = models.IntegerField()
    risk_index = models.IntegerField(default=30)
    rainfall_30d = models.FloatField(default=45)
    imf = models.CharField(max_length=100, default='AXA Assurances Sénégal')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Assurance {self.crop} - {self.farmer.name}"


class Offer(models.Model):
    STATUS_CHOICES = [
        ('pending',  'En attente'),
        ('accepted', 'Acceptée'),
        ('rejected', 'Refusée'),
    ]
    listing      = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='offers')
    buyer_name   = models.CharField(max_length=100)
    buyer_phone  = models.CharField(max_length=20, blank=True)
    buyer_region = models.CharField(max_length=100, default='Dakar')
    quantity     = models.IntegerField()
    price_per_kg = models.IntegerField()
    total        = models.IntegerField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Offre {self.total} FCFA — {self.listing.crop}"


class ChatMessage(models.Model):
    session_key = models.CharField(max_length=100)
    role = models.CharField(max_length=20)
    content = models.TextField()
    language = models.CharField(max_length=5, default='fr')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
